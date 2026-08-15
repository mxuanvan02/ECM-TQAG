#!/usr/bin/env python3
"""Round-2 exploratory census under the repaired evidence contract (D1).

Distinct prospective instrument (prospective/v3103_round2/ROUND2_PROTOCOL.md).
Round-1 records are never re-labeled. Owner authorization: chat 2026-08-15
("ngân sách thoải mái"); hard cap USD 10.0, call cap 147 (3 qual + 144 census),
zero retry/fallback/replacement, stop-first-failure in qualification, ITT
denominator 16 per arm in census.

Phases:
  --phase qualification : 3 calls (qwen generation route under round-2 contract;
                          claude + terra judge probes). STOP on first failure.
  --phase census        : Frame A, 48 generation attempts; judge attempts only
                          for generation-passing candidates. Resumable; orphans
                          sealed as terminal failures (no retry).

Offline import performs no credential or network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.judge_output_contract import append_judge_output_contract
from ecm_tqag.official_credentials import runtime_key_file
from ecm_tqag.official_outcomes import authoritative_frame
from ecm_tqag.run.ledger import RunLedger
from ecm_tqag.run.transport import OpenAITransport, load_response_sidecar
from ecm_tqag.stats.intervals import clopper_pearson
from ecm_tqag.v310_contracts import GENERATOR_MODEL, canonical_bytes
from ecm_tqag.v310_execution import build_call_plan
from ecm_tqag.v310_runner import (
    build_generation_request,
    build_judge_request,
    build_packages,
    blind_candidate_code,
    extract_reported_cost_usd,
)
from ecm_tqag.v310_validation import decode_one_json_object, validate_judgement
from ecm_tqag.v3102_endpoint_contract import build_request

from round2.round2_validation import classify_quote, validate_generation_round2
from round2.round2d_prompt import PROMPT_CLARIFICATION_V2, amend_generation_payload
from round2.round2c_routes import (
    JUDGE_MODELS_R2C as JUDGE_MODELS,
    SUPERSEDED_JUDGE_MODELS,
    build_judge_request_r2c,
    build_transport_configs_r2c as build_transport_configs,
)

RUN_DIR = ROOT / "runs" / "round2d_exploratory_census_20260815T044500Z"
USD_HARD_CAP = 10.0
QUAL_CAP = 3
CENSUS_CAP = 144
ARMS = ("ecm_full", "direct", "structured_no_contract")


class ConcurrentRunBlocked(RuntimeError):
    """Raised when another process already owns this run directory."""


def acquire_run_lock(run_dir: Path):
    """Exclusive cross-process run lock.

    The round-2 contamination (2026-08-15) was caused by two concurrent census
    processes: the transport ledger de-duplicates by idempotency key using an
    IN-PROCESS cache only, so neither writer could see the other's terminals and
    each issued its own paid call for the same 68 tasks. An O_EXCL lock file plus
    flock makes a second writer fail closed instead of double-billing.
    """
    import fcntl

    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / ".RUN_LOCK"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise ConcurrentRunBlocked(
            "BLOCKED_ROUND2:CONCURRENT_RUN another process holds " + str(path)
        ) from exc
    os.ftruncate(fd, 0)
    os.write(fd, (json.dumps({"pid": os.getpid(), "acquired_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n").encode())
    os.fsync(fd)
    return fd


def claim_task(state: Path, task_id: str) -> bool:
    """Atomically claim a task before any paid call.

    Second line of defence independent of the run lock: the claim file is created
    with O_EXCL, so a task can never be attempted twice even if two writers ever
    coexist again. Claims are only removed by an explicit unclaim after the task
    record is durably written.
    """
    claims = state / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    path = claims / (sha256_bytes(task_id.encode()) + ".claim")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    try:
        os.write(fd, (task_id + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def private_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def private_json(path: Path, value: Any) -> None:
    private_write(path, canonical_bytes(value))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def task_path(state: Path, task_id: str) -> Path:
    return state / "tasks" / (sha256_bytes(task_id.encode()) + ".json")


def known_cost(state: Path) -> tuple[float, int]:
    ledger = state / "transport" / "CALL_LEDGER.jsonl"
    known = 0.0
    unknown = 0
    if not ledger.exists():
        return known, unknown
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("record_type") != "CALL_TERMINAL":
            continue
        usage = row.get("usage")
        cost = extract_reported_cost_usd(usage) if isinstance(usage, Mapping) else None
        if cost is None:
            unknown += 1
        else:
            known += float(cost)
    return known, unknown


def seal_orphan_attempts(state: Path, tasks: list[Mapping[str, Any]]) -> list[str]:
    ledger = state / "transport" / "CALL_LEDGER.jsonl"
    if not ledger.exists():
        return []
    started: set[str] = set()
    terminal: set[str] = set()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        task_id = row.get("task_id")
        if not isinstance(task_id, str):
            continue
        if row.get("record_type") == "CALL_STARTED":
            started.add(task_id)
        elif row.get("record_type") == "CALL_TERMINAL":
            terminal.add(task_id)
    sealed = []
    valid_ids = {t["task_id"] for t in tasks}
    for task_id in started - terminal:
        if task_id not in valid_ids:
            continue
        path = task_path(state, task_id)
        if path.exists():
            continue
        private_json(path, {
            "task_id": task_id,
            "status": "TERMINAL_FAILURE",
            "reason": "orphan_process_death:call_started_without_terminal",
        })
        sealed.append(task_id)
        print(f"[orphan sealed] {task_id}", flush=True)
    return sealed


def r2_id(task_id: str) -> str:
    return task_id.replace("::full::", "::r2d::", 1)


def remap_judge_task(task: Mapping[str, Any]) -> dict[str, Any]:
    """Rewrite a frozen judge task onto the substituted judge families.

    ``build_call_plan`` is audit-bound and emits the ORIGINAL judge names in both
    ``model`` and ``task_id``. Round 2c substitutes the judge families, so each
    judge task is remapped positionally (superseded[i] -> substituted[i]); the
    chunk, arm, and source generation task are untouched.
    """
    old_model = task["model"]
    try:
        index = SUPERSEDED_JUDGE_MODELS.index(old_model)
    except ValueError as exc:
        raise ValueError("BLOCKED_ROUND2C:UNKNOWN_FROZEN_JUDGE:" + str(old_model)) from exc
    new_model = JUDGE_MODELS[index]
    task_id = r2_id(task["task_id"])
    if not task_id.endswith("::" + old_model):
        raise ValueError("BLOCKED_ROUND2C:JUDGE_TASK_ID_SHAPE:" + task_id)
    task_id = task_id[: -len("::" + old_model)] + "::" + new_model
    return {
        **task,
        "model": new_model,
        "task_id": task_id,
        "source_task_id": r2_id(task["source_task_id"]),
        "superseded_model": old_model,
    }


def load_frame():
    frame = authoritative_frame()
    ids = frame["full_chunk_ids"]
    assignments = frame["assignments"]
    manifest = read_json(ROOT / "dataset" / "dataset_manifest.json")
    packages = build_packages(manifest, ids, assignments=assignments, root=ROOT)
    return ids, assignments, packages


def make_caller(state: Path, plan_hash: str, cap: int):
    """Context-managed sealed transport caller for round 2."""
    import contextlib

    @contextlib.contextmanager
    def ctx():
        with runtime_key_file("OPENROUTER_API_KEY") as op, runtime_key_file("OMNIPROXY_API_KEY") as omni:
            configs = build_transport_configs(openrouter_key_file=op, omniproxy_key_file=omni)
            ledger = RunLedger(
                state / "transport" / "CALL_LEDGER.jsonl",
                freeze_sha256=plan_hash,
                cap=cap,
                retry_reserve=0,
            )
            transport = OpenAITransport(ledger)

            def caller(*, model: str, payload: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
                config = configs[model]
                if config.max_retries != 0 or config.allow_fallbacks is not False:
                    raise ValueError("ROUTE_POLICY")
                terminal = transport.call(config, payload, metadata=metadata)
                if terminal.get("outcome") != "OK" or terminal.get("http_status") != 200:
                    raise ValueError("TRANSPORT:" + str(terminal.get("reason"))[:200])
                if terminal.get("returned_model") != model:
                    raise ValueError("MODEL_IDENTITY:" + str(terminal.get("returned_model")))
                body = load_response_sidecar(transport.ledger.path.parent, terminal)
                if body.get("model") != model:
                    raise ValueError("MODEL_IDENTITY_BODY")
                return body

            yield caller

    return ctx


def _recover_qualification_candidate(state: Path) -> dict[str, Any] | None:
    """Recover the Qwen qualification candidate from its sealed sidecar.

    The judge route probe needs a REAL candidate to judge (see deviation 2 in
    ``qualification``). The Qwen qualification call has already been paid for and
    its raw envelope is retained in the transport ledger, so the candidate is
    recovered from that evidence rather than by issuing another generation call.

    Returns None when no successful Qwen qualification response is retained, in
    which case the judge probes are skipped rather than sent contentless.
    """
    ledger = state / "transport" / "CALL_LEDGER.jsonl"
    if not ledger.exists():
        return None
    terminal: dict[str, Any] | None = None
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            row.get("record_type") == "CALL_TERMINAL"
            and row.get("model") == GENERATOR_MODEL
            and row.get("outcome") == "OK"
        ):
            terminal = row
    if terminal is None:
        return None
    try:
        body = load_response_sidecar(ledger.parent, terminal)
        obj = decode_one_json_object(body["choices"][0]["message"]["content"])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def qualification(plan_hash: str) -> int:
    """Round-2c route qualification: transport + model identity + native schema.

    Ordering is load-bearing. The judge route probe must send a REAL judge
    request, and its candidate comes from the Qwen qualification response, so
    the Qwen case executes FIRST, the candidate is recovered from its sealed
    sidecar, and only then are the judge cases built and executed. An
    unrecoverable candidate fails closed rather than silently skipping the
    judge probes and still reporting a pass.

    Deviations sealed for this run (see DEVIATION_SEAL.json files):
      1. the first round-2 qualification attempt wrongly gated on full census
         contract pass (quote verbatimness is a census gate, not a route gate);
      2. the contentless judge probe inherited from round 2b drew a correct
         refusal from claude-opus-5, because the output contract forbids
         inventing scores when no evidence is supplied.
    """
    state = RUN_DIR / "qualification_probe"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    ids, assignments, packages = load_frame()
    chunk_id = ids[0]
    qtype = assignments[chunk_id]

    built = build_generation_request(packages[chunk_id], arm="ecm_full", question_type=qtype)
    amend_generation_payload(built["payload"])

    judge_case_names = [
        (judge.replace("/", "_").replace(".", "_")) + "_judge_probe" for judge in JUDGE_MODELS
    ]
    private_json(RUN_DIR / "ROUND2_QUALIFICATION_PLAN.json", {
        "schema": "ecm-tqag.round2d.qualification-plan.v1",
        "cases": ["qwen_generation_round2", *judge_case_names],
        "judges": list(JUDGE_MODELS),
        "superseded_judges": list(SUPERSEDED_JUDGE_MODELS),
        "judge_probe": "real_judge_request_over_qualification_chunk",
        "plan_sha256": plan_hash,
    })

    def record(name: str, model: str, outcome: str, **extra: Any) -> None:
        private_json(state / (name + ".json"),
                     {"case": name, "model": model, "outcome": outcome, **extra})

    def prior_record(name: str) -> dict[str, Any] | None:
        path = state / (name + ".json")
        return read_json(path) if path.exists() else None

    passed = 0
    total = 1 + len(JUDGE_MODELS)

    with make_caller(state, plan_hash, QUAL_CAP)() as caller:
        # ---- case 1: generator route (must run before the judge probes) ----
        name = "qwen_generation_round2"
        prior = prior_record(name)
        if prior is not None:
            if prior.get("outcome") != "PASS":
                print(f"[qual STOP] {name} previously failed; stop-first-failure", flush=True)
                return 1
            print(f"[qual skip] {name} (already PASS)", flush=True)
            passed += 1
        else:
            try:
                body = caller(model=GENERATOR_MODEL, payload=built["payload"], metadata={
                    "phase": "qualification", "case": name,
                    "chunk_id": chunk_id, "question_type": qtype,
                })
                obj = decode_one_json_object(body["choices"][0]["message"]["content"])
                expected_keys = (
                    {"question", "answer", "question_type", "text_evidence_quote", "visual_evidence"}
                    | ({"options", "correct_option"} if qtype == "multiple_choice" else set())
                )
                if set(obj) != expected_keys or obj.get("question_type") != qtype:
                    raise ValueError("R2C:QUAL:SCHEMA")
                cost = extract_reported_cost_usd(body.get("usage"))
                record(name, GENERATOR_MODEL, "PASS", reported_cost_usd=cost,
                       route_conformance="schema_exact",
                       round2_quote_class_observed=classify_quote(
                           obj.get("text_evidence_quote"), built["source_text"]))
                print(f"[qual PASS] {name} cost={cost}", flush=True)
                passed += 1
            except Exception as exc:
                record(name, GENERATOR_MODEL, "FAIL", reason=str(exc)[:300])
                print(f"[qual FAIL] {name} reason={str(exc)[:160]}; STOP (first failure)", flush=True)
                return 1

        # ---- candidate for the judge probes, from already-paid evidence ----
        probe_candidate = _recover_qualification_candidate(state)
        if probe_candidate is None:
            record("judge_probe_candidate", "n/a", "FAIL",
                   reason="candidate_unrecoverable_from_sealed_sidecar")
            print("[qual FAIL] judge probe candidate unrecoverable; STOP (fail closed)", flush=True)
            return 1

        # ---- cases 2..n: judge routes, real judge request over real evidence ----
        for judge, name in zip(JUDGE_MODELS, judge_case_names):
            prior = prior_record(name)
            if prior is not None:
                if prior.get("outcome") != "PASS":
                    print(f"[qual STOP] {name} previously failed; stop-first-failure", flush=True)
                    return 1
                print(f"[qual skip] {name} (already PASS)", flush=True)
                passed += 1
                continue
            try:
                judge_built = build_judge_request_r2c(
                    packages[chunk_id], candidate=probe_candidate,
                    candidate_code=blind_candidate_code("qualification::r2d::" + chunk_id),
                    judge_model=judge, question_type=qtype,
                )
                body = caller(model=judge, payload=judge_built["payload"], metadata={
                    "phase": "qualification", "case": judge, "chunk_id": chunk_id,
                    "question_type": qtype, "candidate_code": judge_built["candidate_code"],
                })
                obj = decode_one_json_object(body["choices"][0]["message"]["content"])
                validate_judgement(obj, question_type=qtype)
                cost = extract_reported_cost_usd(body.get("usage"))
                record(name, judge, "PASS", reported_cost_usd=cost)
                print(f"[qual PASS] {name} cost={cost}", flush=True)
                passed += 1
            except Exception as exc:
                record(name, judge, "FAIL", reason=str(exc)[:300])
                print(f"[qual FAIL] {name} reason={str(exc)[:160]}; STOP (first failure)", flush=True)
                return 1

    print(f"[qual] {passed}/{total} PASS under round-2c contract", flush=True)
    return 0 if passed == total else 1


def census(plan_hash: str) -> int:
    started = time.time()
    state = RUN_DIR / "state"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    ids, assignments, packages = load_frame()
    plan = build_call_plan(mode="full", chunk_ids=ids)
    generation_tasks = [{**t, "task_id": r2_id(t["task_id"])} for t in plan["generation_tasks"]]
    judge_tasks = [remap_judge_task(t) for t in plan["judge_tasks"]]
    # Fail closed if any frozen judge name survived the substitution.
    for t in judge_tasks:
        if t["model"] not in JUDGE_MODELS or not t["task_id"].endswith("::" + t["model"]):
            raise ValueError("BLOCKED_ROUND2C:JUDGE_TASK_REMAP:" + t["task_id"])
    if len({t["task_id"] for t in judge_tasks}) != len(judge_tasks):
        raise ValueError("BLOCKED_ROUND2C:JUDGE_TASK_COLLISION")
    private_json(RUN_DIR / "ROUND2_PLAN.json", {
        "schema": "ecm-tqag.round2d.census-plan.v1",
        "frame": "A_same_16_chunks",
        "generation_tasks": len(generation_tasks),
        "judge_tasks": len(judge_tasks),
        "plan_sha256": plan_hash,
    })
    seal_orphan_attempts(state, [*generation_tasks, *judge_tasks])

    budget_exceeded = False

    def check_budget() -> bool:
        nonlocal budget_exceeded
        if not budget_exceeded:
            cost_now, _ = known_cost(state)
            if cost_now > USD_HARD_CAP:
                budget_exceeded = True
        return budget_exceeded

    with make_caller(state, plan_hash, CENSUS_CAP)() as caller:
        for task in generation_tasks:
            task_id = task["task_id"]
            path = task_path(state, task_id)
            if path.exists():
                continue
            if not claim_task(state, task_id):
                print(f"[gen SKIP] {task_id} already claimed; refusing duplicate paid call", flush=True)
                continue
            if check_budget():
                private_json(path, {"task_id": task_id, "status": "NOT_ATTEMPTED", "reason": "budget_cap"})
                continue
            chunk_id, arm = task["chunk_id"], task["arm"]
            qtype = assignments[chunk_id]
            try:
                built = build_generation_request(packages[chunk_id], arm=arm, question_type=qtype)
                amend_generation_payload(built["payload"])
                metadata = {"phase": "generation", "run": "round2d_exploratory_census",
                            "task_id": task_id, "chunk_id": chunk_id, "arm": arm,
                            "question_type": qtype, "evidence_sha256": built["evidence_sha256"]}
                body = caller(model=task["model"], payload=dict(built["payload"]), metadata=metadata)
                raw = canonical_bytes(body)
                private_write(state / "responses" / (sha256_bytes(raw) + ".json"), raw)
                obj = decode_one_json_object(body["choices"][0]["message"]["content"])
                validated = validate_generation_round2(
                    obj, question_type=qtype,
                    source_text=built["source_text"],
                    image_hashes=set(built["image_hashes"]),
                )
                private_json(path, {"task_id": task_id, "status": "COMPLETE", "gates_passed": True,
                                    "candidate_code": blind_candidate_code(task_id),
                                    "object": validated,
                                    "round2_quote_class": validated["round2_quote_class"],
                                    "reported_cost_usd": extract_reported_cost_usd(body.get("usage"))})
                print(f"[gen PASS] {task_id} quote={validated['round2_quote_class']}", flush=True)
            except Exception as exc:
                private_json(path, {"task_id": task_id, "status": "TERMINAL_FAILURE", "reason": str(exc)[:500]})
                print(f"[gen FAIL] {task_id} reason={str(exc)[:160]}", flush=True)

        for task in judge_tasks:
            task_id = task["task_id"]
            path = task_path(state, task_id)
            if path.exists():
                continue
            source_path = task_path(state, task["source_task_id"])
            source_result = read_json(source_path) if source_path.exists() else {}
            if source_result.get("status") != "COMPLETE":
                private_json(path, {"task_id": task_id, "status": "NOT_ATTEMPTED", "reason": "generation_not_complete"})
                continue
            if not claim_task(state, task_id):
                print(f"[judge SKIP] {task_id} already claimed; refusing duplicate paid call", flush=True)
                continue
            if check_budget():
                private_json(path, {"task_id": task_id, "status": "NOT_ATTEMPTED", "reason": "budget_cap"})
                continue
            chunk_id = task["chunk_id"]
            qtype = assignments[chunk_id]
            try:
                built = build_judge_request_r2c(
                    packages[chunk_id], candidate=source_result["object"],
                    candidate_code=source_result["candidate_code"],
                    judge_model=task["model"], question_type=qtype,
                )
                metadata = {"phase": "judging", "run": "round2d_exploratory_census",
                            "task_id": task_id, "chunk_id": chunk_id,
                            "candidate_code": built["candidate_code"],
                            "question_type": qtype, "evidence_sha256": built["evidence_sha256"]}
                body = caller(model=task["model"], payload=dict(built["payload"]), metadata=metadata)
                raw = canonical_bytes(body)
                private_write(state / "responses" / (sha256_bytes(raw) + ".json"), raw)
                obj = decode_one_json_object(body["choices"][0]["message"]["content"])
                validated = validate_judgement(obj, question_type=qtype)
                private_json(path, {"task_id": task_id, "status": "COMPLETE", "gates_passed": True,
                                    "object": validated,
                                    "reported_cost_usd": extract_reported_cost_usd(body.get("usage"))})
                print(f"[judge PASS] {task_id}", flush=True)
            except Exception as exc:
                private_json(path, {"task_id": task_id, "status": "TERMINAL_FAILURE", "reason": str(exc)[:500]})
                print(f"[judge FAIL] {task_id} reason={str(exc)[:160]}", flush=True)

    # ---- aggregate ----
    gen_records = {}
    for t in generation_tasks:
        p = task_path(state, t["task_id"])
        gen_records[t["task_id"]] = read_json(p) if p.exists() else None
    judge_records = {}
    for t in judge_tasks:
        p = task_path(state, t["task_id"])
        judge_records[t["task_id"]] = read_json(p) if p.exists() else None

    hard_valid: dict[str, dict[str, bool]] = {arm: {cid: False for cid in ids} for arm in ARMS}
    gen_pass: dict[str, dict[str, bool]] = {arm: {cid: False for cid in ids} for arm in ARMS}
    for t in generation_tasks:
        rec = gen_records[t["task_id"]]
        if rec and rec.get("status") == "COMPLETE":
            gen_pass[t["arm"]][t["chunk_id"]] = True
    for t in generation_tasks:
        chunk_id, arm = t["chunk_id"], t["arm"]
        if not gen_pass[arm][chunk_id]:
            continue
        judges_ok = True
        for judge in JUDGE_MODELS:
            jtid = f"judge::r2d::{chunk_id}::{arm}::{judge}"
            jrec = judge_records.get(jtid)
            if not (jrec and jrec.get("status") == "COMPLETE"):
                judges_ok = False
                break
            o = jrec["object"]
            if o.get("critical_provenance_violation") is True:
                judges_ok = False
                break
            if min(o.get("evidence_correctness", 0), o.get("visual_necessity", 0),
                   o.get("answerability", 0)) < 3:
                judges_ok = False
                break
        hard_valid[arm][chunk_id] = judges_ok

    def exact_mcnemar(b: int, c: int) -> float:
        if b + c == 0:
            return 1.0
        from math import comb
        n = b + c
        k = min(b, c)
        p_two_tail = sum(comb(n, i) for i in range(0, k + 1)) * (0.5 ** (n - 1))
        return min(1.0, p_two_tail)

    contrasts = {}
    pairs = [("ecm_full", "direct"), ("ecm_full", "structured_no_contract")]
    for left, right in pairs:
        disc_l = disc_r = 0
        for cid in ids:
            l, r = hard_valid[left][cid], hard_valid[right][cid]
            if l and not r:
                disc_l += 1
            elif r and not l:
                disc_r += 1
        contrasts[f"{left}_vs_{right}"] = {
            "discordant_left_only": disc_l, "discordant_right_only": disc_r,
            "p_two_sided_exact": exact_mcnemar(disc_l, disc_r),
        }

    status_counts: dict[str, dict[str, int]] = {"generation": {}, "judge": {}}
    for name, records in (("generation", gen_records), ("judge", judge_records)):
        for rec in records.values():
            key = rec.get("status") if rec else "MISSING"
            status_counts[name][key] = status_counts[name].get(key, 0) + 1

    known_total, unknown_count = known_cost(state)
    report = {
        "schema": "ecm-tqag.round2d.census-report.v1",
        "run": RUN_DIR.name,
        "mode": "exploratory_round2d_prompt_convention_repair",
        "usd_hard_cap": USD_HARD_CAP,
        "budget_exceeded": budget_exceeded,
        "known_reported_cost_usd": round(known_total, 9),
        "unknown_cost_call_count": unknown_count,
        "status_counts": status_counts,
        "generation_pass_per_arm": {arm: sum(gen_pass[arm].values()) for arm in ARMS},
        "hard_valid_per_arm": {arm: sum(hard_valid[arm].values()) for arm in ARMS},
        "hard_valid_ci_per_arm": {
            arm: clopper_pearson(sum(hard_valid[arm].values()), 16)["interval"] for arm in ARMS
        },
        "contrasts": contrasts,
        "quote_classes": _quote_classes(gen_records),
        "elapsed_sec": round(time.time() - started, 1),
    }
    private_json(RUN_DIR / "ROUND2_REPORT.json", report)
    print(json.dumps(report, indent=1, ensure_ascii=False), flush=True)
    return 0


def _quote_classes(gen_records: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in gen_records.values():
        if not rec:
            continue
        if rec.get("status") == "COMPLETE":
            key = "pass:" + str(rec.get("round2_quote_class"))
        else:
            key = "fail:" + str(rec.get("reason", ""))[:60]
        counts[key] = counts.get(key, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["qualification", "census"], required=True)
    args = parser.parse_args()
    binding = canonical_bytes({
        "instrument": "round2d_prompt_convention_repair_v1",
        "judges": list(JUDGE_MODELS),
        "superseded_judges": list(SUPERSEDED_JUDGE_MODELS),
        "validator": sha256_bytes((ROOT / "round2" / "round2_validation.py").read_bytes()),
        "prompt": sha256_bytes((ROOT / "round2" / "round2d_prompt.py").read_bytes()),
    })
    plan_hash = sha256_bytes(binding)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    try:
        lock_fd = acquire_run_lock(RUN_DIR)
    except ConcurrentRunBlocked as exc:
        print(str(exc), flush=True)
        return 2
    try:
        if args.phase == "qualification":
            return qualification(plan_hash)
        return census(plan_hash)
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
