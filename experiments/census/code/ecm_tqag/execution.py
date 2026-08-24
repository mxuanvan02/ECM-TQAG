"""Offline execution primitives for ECM-TQAG v3.10.

Provider calls remain injected by a later authorized runner.  This module only
builds plans and enforces attempt, cost, binding, and checkpoint semantics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import ARMS, GENERATOR_MODEL, canonical_bytes, canonical_sha256
from .outcomes import (
    authoritative_frame,
    require_official_membership,
)


def __getattr__(name: str):
    """Legacy 16-chunk frame ids, resolved on demand (see outcomes.__getattr__)."""
    if name in {"FULL_CHUNK_IDS", "PILOT_CHUNK_IDS"}:
        from . import outcomes
        return getattr(outcomes, "FULL_IDS" if name == "FULL_CHUNK_IDS" else "PILOT_IDS")
    raise AttributeError(name)

# LEGACY replay raters, audit-bound to the round-1 16-chunk records: those
# records were produced by these two routes, so the replay path must keep them.
# The census raters are routes.JUDGE_MODELS_R2C = ("claude-opus-5",
# "gpt-5.6-sol"); run_census.py imports that tuple and rejects these two.
JUDGE_MODELS = ("claude-sonnet-5", "gpt-5.6-terra")


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_V310:" + reason)


def build_call_plan(*, mode: str, chunk_ids: Sequence[str] | None = None) -> dict[str, Any]:
    frame = authoritative_frame()
    frozen = frame["pilot_chunk_ids" if mode == "pilot" else "full_chunk_ids"] if mode in {"pilot", "full"} else ()
    chosen = tuple(frozen if chunk_ids is None else chunk_ids)
    try:
        require_official_membership(mode, chosen)
    except ValueError as exc:
        raise _blocked("CALL_PLAN_MEMBERSHIP") from exc
    chunk_ids = chosen
    expected_chunks = 4 if mode == "pilot" else 16 if mode == "full" else None
    if (
        expected_chunks is None
        or len(chunk_ids) != expected_chunks
        or len(set(chunk_ids)) != expected_chunks
        or any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids)
    ):
        raise _blocked("CALL_PLAN")
    generation_tasks: list[dict[str, Any]] = []
    judge_tasks: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        for arm in ARMS:
            source_task_id = f"generation::{mode}::{chunk_id}::{arm}"
            generation_tasks.append(
                {
                    "task_id": source_task_id,
                    "phase": "generation",
                    "mode": mode,
                    "chunk_id": chunk_id,
                    "arm": arm,
                    "model": GENERATOR_MODEL,
                    "calls": 1,
                    "retry": 0,
                    "fallback": False,
                }
            )
            for judge in JUDGE_MODELS:
                judge_tasks.append(
                    {
                        "task_id": f"judge::{mode}::{chunk_id}::{arm}::{judge}",
                        "source_task_id": source_task_id,
                        "phase": "judging",
                        "mode": mode,
                        "chunk_id": chunk_id,
                        "model": judge,
                        "calls": 1,
                        "retry": 0,
                        "fallback": False,
                        "arm_masked": True,
                    }
                )
    tasks = generation_tasks + judge_tasks
    return {
        "schema": "ecm-tqag.v3.10.call-plan.v1",
        "mode": mode,
        "arms": list(ARMS),
        "generator_model": GENERATOR_MODEL,
        "judge_models": list(JUDGE_MODELS),
        "chunk_ids": list(chunk_ids),
        "generation_tasks": generation_tasks,
        "judge_tasks": judge_tasks,
        "max_http_calls": len(tasks),
        "retry": 0,
        "fallback": False,
        "replacement": False,
    }


class AttemptLedger:
    """Append-only attempt ledger; each start irrevocably consumes capacity."""

    def __init__(self, *, cap: int):
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise _blocked("ATTEMPT_CAP")
        self.cap = cap
        self.records: list[dict[str, Any]] = []
        self._attempts_started = 0
        self._open_attempts: dict[int, str] = {}

    @property
    def attempts_started(self) -> int:
        return self._attempts_started

    def start(self, task_id: str) -> int:
        if self.attempts_started >= self.cap:
            raise _blocked("ATTEMPT_CAP")
        if not isinstance(task_id, str) or not task_id:
            raise _blocked("ATTEMPT")
        self._attempts_started += 1
        token = self._attempts_started
        self._open_attempts[token] = task_id
        self.records.append(
            {
                "event": "CALL_STARTED",
                "attempt": token,
                "task_id": task_id,
                "status": "STARTED",
                "reported_cost_usd": None,
            }
        )
        return token

    def finish(
        self,
        token: int,
        *,
        status: str,
        reported_cost_usd: float | int | None,
    ) -> None:
        if isinstance(token, bool) or not isinstance(token, int) or token not in self._open_attempts:
            raise _blocked("ATTEMPT")
        if status not in {"COMPLETE", "TERMINAL_FAILURE"}:
            raise _blocked("ATTEMPT")
        _validate_cost(reported_cost_usd)
        task_id = self._open_attempts.pop(token)
        self.records.append(
            {
                "event": status,
                "attempt": token,
                "task_id": task_id,
                "status": status,
                "reported_cost_usd": reported_cost_usd,
            }
        )


def _validate_cost(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise _blocked("COST")


def summarize_reported_cost(values: Iterable[float | int | None]) -> float | None:
    total = 0.0
    known = True
    for value in values:
        _validate_cost(value)
        if value is None:
            known = False
        else:
            total += float(value)
    return total if known else None


def compute_run_binding(
    *,
    plan_sha256: str,
    dataset_sha256: str,
    type_assignment_sha256: str,
    prompt_contract_sha256: str,
    source_hashes: Mapping[str, str],
) -> str:
    values = {
        "plan_sha256": plan_sha256,
        "dataset_sha256": dataset_sha256,
        "type_assignment_sha256": type_assignment_sha256,
        "prompt_contract_sha256": prompt_contract_sha256,
        "source_hashes": dict(source_hashes),
    }
    if any(
        not isinstance(value, str) or len(value) != 64
        for key, value in values.items()
        if key != "source_hashes"
    ) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or len(value) != 64
        for key, value in source_hashes.items()
    ):
        raise _blocked("RUN_BINDING")
    return canonical_sha256(values)


def _write_private_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        payload = canonical_bytes(value)
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, path)
    os.chmod(path, 0o600)
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def write_checkpoint(
    path: Path | str,
    *,
    task_id: str,
    run_binding_sha256: str,
    result: Mapping[str, Any],
) -> None:
    target = Path(path)
    if not isinstance(result, Mapping):
        raise _blocked("CHECKPOINT_GATES")
    if result.get("status") not in {"COMPLETE", "TERMINAL_FAILURE"}:
        raise _blocked("CHECKPOINT_GATES")
    if result.get("gates_passed") is False:
        raise _blocked("CHECKPOINT_GATES")
    if not isinstance(task_id, str) or not task_id or len(run_binding_sha256) != 64:
        raise _blocked("CHECKPOINT_GATES")
    result_copy = dict(result)
    record = {
        "schema": "ecm-tqag.v3.10.checkpoint.v1",
        "task_id": task_id,
        "run_binding_sha256": run_binding_sha256,
        "result": result_copy,
        "result_sha256": canonical_sha256(result_copy),
    }
    _write_private_atomic(target, record)


def load_checkpoint(
    path: Path | str,
    *,
    task_id: str,
    run_binding_sha256: str,
) -> dict[str, Any]:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise _blocked("CHECKPOINT_INTEGRITY") from exc
    if record.get("task_id") != task_id:
        raise _blocked("CHECKPOINT_INTEGRITY")
    if record.get("run_binding_sha256") != run_binding_sha256:
        raise _blocked("RESUME_BINDING")
    result = record.get("result")
    if not isinstance(result, dict) or record.get("result_sha256") != canonical_sha256(result):
        raise _blocked("CHECKPOINT_INTEGRITY")
    return result


__all__ = [
    "AttemptLedger",
    "JUDGE_MODELS",
    "FULL_CHUNK_IDS",
    "PILOT_CHUNK_IDS",
    "build_call_plan",
    "compute_run_binding",
    "load_checkpoint",
    "summarize_reported_cost",
    "write_checkpoint",
]
