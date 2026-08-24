"""Fail-closed, offline-testable execution runner for ECM-TQAG v3.10.

The caller is injected.  This module performs no network I/O and reads no
credentials.  Every injected call is recorded before invocation, consumes the
frozen attempt cap, and has no retry or fallback path.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import mimetypes
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    ARMS,
    GENERATOR_MODEL,
    canonical_bytes,
    canonical_sha256,
    file_sha256,
)
from .execution import JUDGE_MODELS, load_checkpoint, write_checkpoint
from .outcomes import authoritative_frame, derive_outcomes, require_official_membership
from .validation import (
    decode_one_json_object,
    generation_response_format,
    judge_response_format,
    render_generation_messages,
    render_judge_messages,
    validate_generation,
    validate_judgement,
)


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_V310:" + reason)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _private_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        written = 0
        while written < len(raw):
            written += os.write(fd, raw[written:])
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def _private_json(path: Path, value: Any) -> None:
    _private_write(path, canonical_bytes(value))


def build_packages(
    manifest: Any,
    chunk_ids: Sequence[str],
    *,
    assignments: Mapping[str, str],
    root: Path | str,
) -> dict[str, dict[str, Any]]:
    """Select exactly one TLV package per requested chunk and resolve image paths."""
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != "ecm-tqag.multimodal-inputs.v4-work24"
        or not isinstance(manifest.get("packages"), list)
        or not chunk_ids
        or len(set(chunk_ids)) != len(chunk_ids)
        or set(assignments) != set(chunk_ids)
        or any(value not in {"multiple_choice", "short_answer"} for value in assignments.values())
    ):
        raise _blocked("PACKAGES")
    wanted = set(chunk_ids)
    selected: dict[str, dict[str, Any]] = {}
    base = Path(root)
    for raw in manifest["packages"]:
        if not isinstance(raw, Mapping):
            raise _blocked("PACKAGES")
        chunk_id = raw.get("chunk_id")
        if chunk_id not in wanted or raw.get("condition") != "TLV":
            continue
        if chunk_id in selected:
            raise _blocked("PACKAGES")
        row = deepcopy(dict(raw))
        evidence = row.get("evidence")
        if not isinstance(evidence, dict) or not isinstance(evidence.get("images"), list):
            raise _blocked("EVIDENCE_SCHEMA")
        for image in evidence["images"]:
            if not isinstance(image, dict) or not isinstance(image.get("path"), str):
                raise _blocked("EVIDENCE_SCHEMA")
            path = Path(image["path"])
            if not path.is_absolute():
                path = base / path
            image["path"] = str(path)
        row["question_type"] = assignments[chunk_id]
        selected[chunk_id] = row
    if set(selected) != wanted:
        raise _blocked("PACKAGES")
    return selected


def _verified_evidence(package: Mapping[str, Any]) -> dict[str, Any]:
    if package.get("condition") != "TLV":
        raise _blocked("PACKAGE_CONDITION")
    evidence = package.get("evidence")
    if not isinstance(evidence, Mapping):
        raise _blocked("EVIDENCE_SCHEMA")
    text = evidence.get("text")
    structure = evidence.get("document_structure")
    images = evidence.get("images")
    if not isinstance(text, str) or not text.strip() or not isinstance(images, list) or not images:
        raise _blocked("EVIDENCE_SCHEMA")

    image_parts: list[dict[str, Any]] = []
    image_audit: list[dict[str, Any]] = []
    for image in images:
        if not isinstance(image, Mapping):
            raise _blocked("IMAGE_INTEGRITY")
        path_value = image.get("path")
        claimed_bytes = image.get("bytes")
        claimed_sha = image.get("sha256")
        if (
            not isinstance(path_value, str)
            or isinstance(claimed_bytes, bool)
            or not isinstance(claimed_bytes, int)
            or not isinstance(claimed_sha, str)
        ):
            raise _blocked("IMAGE_INTEGRITY")
        path = Path(path_value)
        if not path.is_file():
            raise _blocked("IMAGE_INTEGRITY")
        raw = path.read_bytes()
        actual_sha = _sha256(raw)
        if len(raw) != claimed_bytes or actual_sha != claimed_sha:
            raise _blocked("IMAGE_INTEGRITY")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        image_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                },
            }
        )
        image_audit.append(
            {
                "sha256": actual_sha,
                "bytes": len(raw),
                "declared_order": image.get("declared_order"),
            }
        )
    public = {"text": text, "document_structure": structure, "images": image_audit}
    return {
        "text": text,
        "structure": structure,
        "image_parts": image_parts,
        "image_hashes": [row["sha256"] for row in image_audit],
        "evidence_sha256": canonical_sha256(public),
    }


def build_generation_request(
    package: Mapping[str, Any], *, arm: str, question_type: str
) -> dict[str, Any]:
    if arm not in ARMS:
        raise _blocked("ARM")
    if package.get("question_type") != question_type:
        raise _blocked("QUESTION_TYPE")
    evidence = _verified_evidence(package)
    rendered = render_generation_messages(
        arm,
        question_type=question_type,
        source_text=evidence["text"],
        document_structure=evidence["structure"],
        image_hashes=evidence["image_hashes"],
    )
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": rendered[1]["content"]},
        *evidence["image_parts"],
    ]
    payload = {
        "messages": [rendered[0], {"role": "user", "content": user_content}],
        "temperature": 0,
        "max_tokens": 1024,
        "response_format": generation_response_format(question_type),
    }
    return {
        "model": GENERATOR_MODEL,
        "payload": payload,
        "evidence_sha256": evidence["evidence_sha256"],
        "method_prompt_sha256": _sha256(rendered[0]["content"].encode("utf-8")),
        "image_hashes": evidence["image_hashes"],
        "source_text": evidence["text"],
        "question_type": question_type,
    }


def blind_candidate_code(task_id: str) -> str:
    if not isinstance(task_id, str) or not task_id:
        raise _blocked("TASK_ID")
    digest = _sha256(("ecm-tqag.v3.10.blind.v1|" + task_id).encode("utf-8"))
    return "C-" + digest[:12].upper()


def build_judge_request(
    package: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    candidate_code: str,
    judge_model: str,
    question_type: str,
) -> dict[str, Any]:
    if judge_model not in JUDGE_MODELS:
        raise _blocked("JUDGE_MODEL")
    if not isinstance(candidate_code, str) or not candidate_code.startswith("C-"):
        raise _blocked("CANDIDATE_CODE")
    if package.get("question_type") != question_type:
        raise _blocked("QUESTION_TYPE")
    evidence = _verified_evidence(package)
    rendered = render_judge_messages(
        candidate_code=candidate_code,
        question_type=question_type,
        source_text=evidence["text"],
        image_hashes=evidence["image_hashes"],
        candidate=candidate,
    )
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": rendered[1]["content"]},
        *evidence["image_parts"],
    ]
    return {
        "model": judge_model,
        "candidate_code": candidate_code,
        "evidence_sha256": evidence["evidence_sha256"],
        "payload": {
            "messages": [rendered[0], {"role": "user", "content": user_content}],
            "temperature": 0,
            "max_tokens": 768,
            "response_format": judge_response_format(question_type),
        },
    }


def extract_reported_cost_usd(usage: Any) -> float | None:
    if not isinstance(usage, Mapping) or "cost" not in usage:
        return None
    value = usage.get("cost")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise _blocked("COST")
    return float(value)


def _decode_envelope(envelope: Any, *, expected_model: str) -> tuple[dict[str, Any], float | None]:
    if not isinstance(envelope, Mapping) or envelope.get("model") != expected_model:
        raise _blocked("MODEL_IDENTITY")
    cost = extract_reported_cost_usd(envelope.get("usage"))
    choices = envelope.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
        raise _blocked("JSON_OBJECT")
    message = choices[0].get("message")
    if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
        raise _blocked("JSON_OBJECT")
    return decode_one_json_object(message["content"]), cost


def _validate_plan(
    plan: Any,
    packages: Mapping[str, Mapping[str, Any]],
    assignments: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(plan, Mapping) or plan.get("schema") != "ecm-tqag.v3.10.call-plan.v1":
        raise _blocked("CALL_PLAN")
    generation = plan.get("generation_tasks")
    judging = plan.get("judge_tasks")
    chunk_ids = plan.get("chunk_ids")
    mode = plan.get("mode")
    expected_chunks = 4 if mode == "pilot" else 16 if mode == "full" else None
    expected_call_cap = 36 if mode == "pilot" else 144 if mode == "full" else None
    if isinstance(chunk_ids, list):
        require_official_membership(str(mode), chunk_ids)
    if (
        expected_chunks is None
        or not isinstance(generation, list)
        or not isinstance(judging, list)
        or not isinstance(chunk_ids, list)
        or len(chunk_ids) != expected_chunks
        or len(set(chunk_ids)) != expected_chunks
        or set(chunk_ids) != set(packages)
        or set(assignments) != set(packages)
        or dict(assignments) != {chunk_id: authoritative_frame()["assignments"][chunk_id] for chunk_id in chunk_ids}
        or len(generation) != expected_chunks * len(ARMS)
        or len(judging) != expected_chunks * len(ARMS) * len(JUDGE_MODELS)
        or plan.get("max_http_calls") != expected_call_cap
        or plan.get("max_http_calls") != len(generation) + len(judging)
        or plan.get("arms") != list(ARMS)
        or plan.get("generator_model") != GENERATOR_MODEL
        or plan.get("judge_models") != list(JUDGE_MODELS)
        or plan.get("retry") != 0
        or plan.get("fallback") is not False
        or plan.get("replacement") is not False
    ):
        raise _blocked("CALL_PLAN")

    expected_generation = {
        (chunk_id, arm): f"generation::{mode}::{chunk_id}::{arm}"
        for chunk_id in chunk_ids
        for arm in ARMS
    }
    seen_generation: dict[tuple[str, str], str] = {}
    for task in generation:
        if not isinstance(task, Mapping):
            raise _blocked("CALL_PLAN")
        key = (task.get("chunk_id"), task.get("arm"))
        if (
            key not in expected_generation
            or key in seen_generation
            or task.get("task_id") != expected_generation[key]
            or task.get("phase") != "generation"
            or task.get("mode") != mode
            or task.get("model") != GENERATOR_MODEL
            or task.get("calls") != 1
            or task.get("retry") != 0
            or task.get("fallback") is not False
        ):
            raise _blocked("CALL_PLAN")
        seen_generation[key] = str(task["task_id"])
    if set(seen_generation) != set(expected_generation):
        raise _blocked("CALL_PLAN")

    expected_judging = {
        (chunk_id, arm, judge): (
            f"judge::{mode}::{chunk_id}::{arm}::{judge}",
            expected_generation[(chunk_id, arm)],
        )
        for chunk_id in chunk_ids
        for arm in ARMS
        for judge in JUDGE_MODELS
    }
    seen_judging: set[tuple[str, str, str]] = set()
    for task in judging:
        if not isinstance(task, Mapping):
            raise _blocked("CALL_PLAN")
        source_task_id = task.get("source_task_id")
        source_key = next(
            (key for key, value in expected_generation.items() if value == source_task_id),
            None,
        )
        key = (
            task.get("chunk_id"),
            source_key[1] if source_key is not None else "",
            task.get("model"),
        )
        expected = expected_judging.get(key)
        if (
            expected is None
            or key in seen_judging
            or task.get("task_id") != expected[0]
            or source_task_id != expected[1]
            or task.get("phase") != "judging"
            or task.get("mode") != mode
            or task.get("calls") != 1
            or task.get("arm_masked") is not True
            or task.get("retry") != 0
            or task.get("fallback") is not False
        ):
            raise _blocked("CALL_PLAN")
        seen_judging.add(key)
    if seen_judging != set(expected_judging):
        raise _blocked("CALL_PLAN")

    for chunk_id, package in packages.items():
        if assignments.get(chunk_id) not in {"multiple_choice", "short_answer"}:
            raise _blocked("QUESTION_TYPE")
        if package.get("question_type") != assignments[chunk_id]:
            raise _blocked("QUESTION_TYPE")
    return [dict(task) for task in generation], [dict(task) for task in judging]


def _checkpoint_path(state_dir: Path, task_id: str) -> Path:
    return state_dir / "tasks" / (_sha256(task_id.encode("utf-8")) + ".json")


def _ledger_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError
            rows.append(value)
    except Exception as exc:
        raise _blocked("LEDGER_INTEGRITY") from exc
    return rows


def _append_ledger(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(dict(event)) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def _record_cost_observation(
    state: Path, *, attempt: int, task_id: str, model: str, cost: float | None
) -> None:
    """Durably account for an executed response before scientific validation."""
    path = state / "COST_OBSERVATIONS.jsonl"
    _append_ledger(path, {
        "attempt": attempt,
        "task_id": task_id,
        "model": model,
        "reported_cost_usd": cost,
    })
    rows = _ledger_rows(path)
    costs = [row.get("reported_cost_usd") for row in rows]
    known = sum(float(value) for value in costs if value is not None)
    unknown = sum(value is None for value in costs)
    _private_json(state / "COST_ACCOUNTING.json", {
        "schema": "ecm-tqag.official.cost-accounting.v1",
        "executed_response_count": len(rows),
        "known_reported_cost_usd": known,
        "unknown_cost_call_count": unknown,
        "actual_cost_usd": known if unknown == 0 else None,
        "reported_costs": costs,
    })


def _started_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(row.get("event") == "CALL_STARTED" for row in rows)


def _validate_ledger_state(
    rows: Sequence[Mapping[str, Any]],
    *,
    tasks: Sequence[Mapping[str, Any]],
    state_dir: Path,
) -> tuple[int, set[str]]:
    """Validate append-only event pairs and checkpoint correspondence."""
    expected = {str(task["task_id"]): str(task["model"]) for task in tasks}
    started_tasks: set[str] = set()
    complete_tasks: set[str] = set()
    blocked_retry_tasks: set[str] = set()
    index = 0
    expected_attempt = 1
    event_keys = {"event", "attempt", "task_id", "model", "reported_cost_usd"}

    while index < len(rows):
        start = rows[index]
        if (
            set(start) != event_keys
            or start.get("event") != "CALL_STARTED"
            or start.get("attempt") != expected_attempt
            or start.get("task_id") not in expected
            or start.get("model") != expected[start["task_id"]]
            or start.get("reported_cost_usd") is not None
            or start["task_id"] in started_tasks
        ):
            raise _blocked("LEDGER_INTEGRITY")
        task_id = str(start["task_id"])
        started_tasks.add(task_id)
        index += 1

        # A process may stop after durably recording CALL_STARTED. The attempt is
        # still consumed and the task may not be called again.
        if index == len(rows):
            blocked_retry_tasks.add(task_id)
            break

        terminal = rows[index]
        if (
            set(terminal) != event_keys
            or terminal.get("event") not in {"COMPLETE", "TERMINAL_FAILURE"}
            or terminal.get("attempt") != expected_attempt
            or terminal.get("task_id") != task_id
            or terminal.get("model") != expected[task_id]
        ):
            raise _blocked("LEDGER_INTEGRITY")
        extract_reported_cost_usd({"cost": terminal.get("reported_cost_usd")}) if terminal.get(
            "reported_cost_usd"
        ) is not None else None
        if terminal["event"] == "COMPLETE":
            complete_tasks.add(task_id)
        else:
            blocked_retry_tasks.add(task_id)
        expected_attempt += 1
        index += 1

    for task_id in expected:
        checkpoint_exists = _checkpoint_path(state_dir, task_id).exists()
        if checkpoint_exists != (task_id in complete_tasks):
            raise _blocked("LEDGER_INTEGRITY")
    return len(started_tasks), blocked_retry_tasks


def run_execution_plan(
    plan: Mapping[str, Any],
    *,
    packages: Mapping[str, Mapping[str, Any]],
    assignments: Mapping[str, str],
    call: Callable[..., dict[str, Any]],
    state_dir: Path | str,
) -> dict[str, Any]:
    """Execute generation then blind judging through an exactly-once injected caller."""
    generation_tasks, judge_tasks = _validate_plan(plan, packages, assignments)
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)

    evidence_bindings = {
        chunk_id: _verified_evidence(package)["evidence_sha256"]
        for chunk_id, package in sorted(packages.items())
    }
    project_root = Path(__file__).resolve().parents[1]
    official_root = project_root / "official"
    prompt_contract_sha256 = file_sha256(
        official_root / "PROMPT_SCHEMA_CONTRACT.json"
    )
    experiment_contract_sha256 = file_sha256(
        official_root / "EXPERIMENT_CONTRACT.json"
    )
    dataset_manifest_sha256 = file_sha256(project_root / "dataset/dataset_manifest.json")
    type_assignment_sha256 = file_sha256(project_root / "prospective/v310/TYPE_ASSIGNMENT.json")
    binding_material = {
        "plan": plan,
        "assignments": dict(assignments),
        "evidence": evidence_bindings,
        "experiment_contract_sha256": experiment_contract_sha256,
        "prompt_contract_sha256": prompt_contract_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "type_assignment_sha256": type_assignment_sha256,
    }
    run_binding = canonical_sha256(binding_material)
    binding_record = {
        "schema": "ecm-tqag.official.run-binding.v1",
        "run_binding_sha256": run_binding,
        "plan_sha256": canonical_sha256(plan),
        "assignment_sha256": canonical_sha256(dict(assignments)),
        "evidence_bindings": evidence_bindings,
        "experiment_contract_sha256": experiment_contract_sha256,
        "prompt_contract_sha256": prompt_contract_sha256,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "type_assignment_sha256": type_assignment_sha256,
    }
    binding_path = state / "RUN_BINDING.json"
    binding_preexisted = binding_path.exists()
    if binding_preexisted:
        try:
            existing = json.loads(binding_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise _blocked("RESUME_BINDING") from exc
        if existing != binding_record:
            raise _blocked("RESUME_BINDING")
    else:
        _private_json(binding_path, binding_record)

    ledger_path = state / "CALL_LEDGER.jsonl"
    if binding_preexisted and not ledger_path.exists() and (
        (state / "SUMMARY.json").exists() or (state / "tasks").exists()
    ):
        raise _blocked("LEDGER_INTEGRITY")
    existing_ledger = _ledger_rows(ledger_path)
    lifetime_started, blocked_retry_tasks = _validate_ledger_state(
        existing_ledger,
        tasks=[*generation_tasks, *judge_tasks],
        state_dir=state,
    )
    cap = int(plan["max_http_calls"])
    attempts_this_run = 0
    resumed = 0
    results: dict[str, dict[str, Any]] = {}

    def execute_task(
        task: Mapping[str, Any],
        *,
        built: Mapping[str, Any],
        metadata: dict[str, Any],
        validator: Callable[[dict[str, Any]], dict[str, Any]],
        candidate_code: str,
    ) -> dict[str, Any]:
        nonlocal lifetime_started, attempts_this_run
        task_id = str(task["task_id"])
        if task_id in blocked_retry_tasks:
            raise _blocked("RETRY_DISABLED")
        if lifetime_started >= cap:
            raise _blocked("ATTEMPT_CAP")
        lifetime_started += 1
        attempts_this_run += 1
        attempt = lifetime_started
        _append_ledger(
            ledger_path,
            {
                "event": "CALL_STARTED",
                "attempt": attempt,
                "task_id": task_id,
                "model": task["model"],
                "reported_cost_usd": None,
            },
        )
        envelope: Any = None
        cost: float | None = None
        try:
            envelope = call(model=task["model"], payload=dict(built["payload"]), metadata=metadata)
            # Persist the received envelope before identity/schema/scientific checks.
            envelope_raw = canonical_bytes(envelope)
            _private_write(state / "responses" / (_sha256(envelope_raw) + ".json"), envelope_raw)
            if isinstance(envelope, Mapping):
                cost = extract_reported_cost_usd(envelope.get("usage"))
            _record_cost_observation(
                state, attempt=attempt, task_id=task_id, model=str(task["model"]), cost=cost
            )
            obj, _ = _decode_envelope(envelope, expected_model=str(task["model"]))
            validated = validator(obj)
            result = {
                "status": "COMPLETE",
                "gates_passed": True,
                "object": validated,
                "candidate_code": candidate_code,
                "reported_cost_usd": cost,
            }
            write_checkpoint(
                _checkpoint_path(state, task_id),
                task_id=task_id,
                run_binding_sha256=run_binding,
                result=result,
            )
            _append_ledger(
                ledger_path,
                {
                    "event": "COMPLETE",
                    "attempt": attempt,
                    "task_id": task_id,
                    "model": task["model"],
                    "reported_cost_usd": cost,
                },
            )
            return result
        except Exception:
            _append_ledger(
                ledger_path,
                {
                    "event": "TERMINAL_FAILURE",
                    "attempt": attempt,
                    "task_id": task_id,
                    "model": task["model"],
                    "reported_cost_usd": cost,
                },
            )
            raise

    # Phase barrier: every generation must be present and locally valid before judging.
    for task in generation_tasks:
        task_id = task["task_id"]
        path = _checkpoint_path(state, task_id)
        if path.exists():
            result = load_checkpoint(path, task_id=task_id, run_binding_sha256=run_binding)
            results[task_id] = result
            resumed += 1
            continue
        chunk_id = task["chunk_id"]
        question_type = assignments[chunk_id]
        built = build_generation_request(
            packages[chunk_id], arm=task["arm"], question_type=question_type
        )
        code = blind_candidate_code(task_id)
        results[task_id] = execute_task(
            task,
            built=built,
            metadata={
                "phase": "generation",
                "task_id": task_id,
                "mode": task["mode"],
                "chunk_id": chunk_id,
                "question_type": question_type,
                "evidence_sha256": built["evidence_sha256"],
            },
            validator=lambda obj, qt=question_type, source=built["source_text"], hashes=set(
                built["image_hashes"]
            ): validate_generation(obj, question_type=qt, source_text=source, image_hashes=hashes),
            candidate_code=code,
        )

    for task in judge_tasks:
        task_id = task["task_id"]
        path = _checkpoint_path(state, task_id)
        if path.exists():
            result = load_checkpoint(path, task_id=task_id, run_binding_sha256=run_binding)
            results[task_id] = result
            resumed += 1
            continue
        chunk_id = task["chunk_id"]
        question_type = assignments[chunk_id]
        source = results[task["source_task_id"]]
        built = build_judge_request(
            packages[chunk_id],
            candidate=source["object"],
            candidate_code=source["candidate_code"],
            judge_model=task["model"],
            question_type=question_type,
        )
        results[task_id] = execute_task(
            task,
            built=built,
            metadata={
                "phase": "judging",
                "task_id": task_id,
                "mode": task["mode"],
                "chunk_id": chunk_id,
                "question_type": question_type,
                "candidate_code": built["candidate_code"],
                "evidence_sha256": built["evidence_sha256"],
            },
            validator=lambda obj, qt=question_type: validate_judgement(obj, question_type=qt),
            candidate_code=source["candidate_code"],
        )

    costs = [result.get("reported_cost_usd") for result in results.values()]
    known_cost = sum(float(cost) for cost in costs if cost is not None)
    unknown_cost_call_count = sum(cost is None for cost in costs)
    all_known = unknown_cost_call_count == 0
    derived = derive_outcomes(
        plan=plan,
        generation_records={task_id: results.get(task_id) for task_id in [t["task_id"] for t in generation_tasks]},
        judge_records={task_id: results.get(task_id) for task_id in [t["task_id"] for t in judge_tasks]},
    )
    _private_json(state / "DERIVED_OUTCOMES.json", derived)
    summary = {
        "schema": "ecm-tqag.official.execution-summary.v1",
        "status": "COMPLETE",
        "run_binding_sha256": run_binding,
        "attempts_started": attempts_this_run,
        "generation_complete": len(generation_tasks),
        "judging_complete": len(judge_tasks),
        "resumed_tasks": resumed,
        "known_reported_cost_usd": known_cost,
        "unknown_cost_call_count": unknown_cost_call_count,
        "actual_cost_usd": known_cost if all_known else None,
        "reported_cost_usd": known_cost if all_known else None,
        "derived_outcomes_sha256": canonical_sha256(derived),
    }
    _private_json(state / "SUMMARY.json", summary)
    return summary


__all__ = [
    "blind_candidate_code",
    "build_generation_request",
    "build_judge_request",
    "build_packages",
    "extract_reported_cost_usd",
    "run_execution_plan",
]
