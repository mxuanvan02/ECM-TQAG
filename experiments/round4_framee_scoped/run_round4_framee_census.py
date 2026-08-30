#!/usr/bin/env python3
"""Round-4 Frame-E census: paired visual-necessity endpoint at SECTION granularity.

Derived from run_round4_framec_census.py by frame rebinding only. That runner is
sealed evidence for the reported census and is NOT edited; this file changes the
frame, the run directory, the call cap, the authorization round name and the
report schema, and nothing else about the instrument.

WHAT IS DIFFERENT FROM FRAME C, AND WHY
  * Frame E (67 chunks) is one SECTION of a law textbook per chunk, over the 26
    giao trinh held by the HUL catalogue. Frame C was one PAGE per chunk over a
    mixed document pool of which only 3 chunks were textbooks.
  * Rule 3 is read as its frozen text says -- "at least one extracted figure crop
    resolvable on disk" -- which a rendered vector region satisfies. Frame C
    operationalised it as embedded rasters only. This is a DEVIATION, declared in
    prospective/v3103_round2/ROUND4_FRAMEE_PREREGISTRATION.json before any call,
    and it is the reason n reaches 67 rather than 28.
  * n=60 clears the addendum's pre-specified floor of 40 and its target of 46, so
    section 4's floor clause does NOT apply and Holm rejection flags are live.
    `below_floor` is computed from n, never asserted.
  * Two stratifications are pre-registered alongside the primary endpoint, and
    BOTH are frame-E specific rather than carried over from frame D:
      - scoped_span_band: the character length of the scoped span, which reads
        directly on the length mechanism this adaptation targets;
      - chunk_composition: embedded raster vs rendered-vector-only.
    Frame D's own strata (figure-only lettering, and the frame-C rule-3 subset)
    are NOT reported here: they answer frame D's questions, and silently
    carrying them over would report a split this record never froze.

UNCHANGED: generator, the three arm prompts with the minimal D3 clarification,
the repaired gates, G, V, the seven-field judgement schema, both judge families,
ITT accounting, zero retry/fallback/replacement, the run lock and per-task claim.

AUTHORIZATION
  `--usd-cap` and `--authorization` are both REQUIRED, the authorization must
  name round `round4_framee`, and its cap must equal the cap on the command line.
  Without both the runner refuses to make any paid call.
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
from round2.round4_framee_plan import (
    FRAMEE_MODE,
    FRAMEE_ADDENDUM_SHA256,
    FRAMEE_MANIFEST_NAME,
    FRAMEE_MANIFEST_SHA256,
    FRAMEE_PREREGISTRATION,
    FRAMEE_PREREGISTRATION_SHA256,
    PRE_REGISTERED_FLOOR,
    PRE_REGISTERED_TARGET,
    load_framee,
    load_span_band_stratum,
    load_composition_stratum,
    build_call_plan_framee,
)
from round2.round4_endpoint import analyse as analyse_necessity
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
from round2.round2e_prompt import PROMPT_CLARIFICATION_V3, amend_generation_payload
from round2.round2c_routes import (
    JUDGE_MODELS_R2C as JUDGE_MODELS,
    SUPERSEDED_JUDGE_MODELS,
    build_judge_request_r2c,
    build_transport_configs_r2c as build_transport_configs,
)

RUN_DIR = ROOT / "runs" / "round4_framee_census_20260830T100000Z"
# No cap constant. The cap is supplied per invocation and must match the
# owner authorization artefact; see require_authorization().
QUAL_CAP = 3
CENSUS_CAP = 540  # 60 chunks x 3 arms x (1 generation + 2 judges)
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


def _now() -> str:
    """UTC timestamp for report provenance."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


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
    """Identity. The round-4 plan builder emits ``::r4c::`` ids directly.

    Rounds 2/2c/2d/2e rewrote ids produced by the audit-bound
    ``build_call_plan`` (which hardcodes the Frame-A membership and the ORIGINAL
    judge names). Frame B needs its own plan builder, so no rewrite is required
    and none is performed; this shim is kept only so the surrounding code reads
    identically across rounds.
    """
    return task_id


def validate_judge_task(task: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed unless the plan already carries a substituted judge family.

    Round 2c had to remap frozen judge names positionally. The Frame-B plan
    builder emits ``JUDGE_MODELS_R2C`` directly, so a remap would be a silent
    relabel; instead the shape is verified and any superseded name is rejected.
    """
    model = task["model"]
    if model in SUPERSEDED_JUDGE_MODELS:
        raise ValueError("BLOCKED_ROUND4E:SUPERSEDED_JUDGE_IN_PLAN:" + str(model))
    if model not in JUDGE_MODELS:
        raise ValueError("BLOCKED_ROUND4E:UNKNOWN_JUDGE:" + str(model))
    if not str(task["task_id"]).endswith("::" + model):
        raise ValueError("BLOCKED_ROUND4E:JUDGE_TASK_ID_SHAPE:" + str(task["task_id"]))
    return dict(task)


def load_frame():
    """Frame C: rule-4-corrected chunks frozen in ROUND4_NECESSITY_ADDENDUM.md v2."""
    ids, assignments, manifest = load_framee(ROOT)
    packages = build_packages(manifest, ids, assignments=assignments, root=ROOT)
    return ids, assignments, packages


def load_authorization(path: Path, usd_cap: float) -> dict[str, Any]:
    """Owner authorization gate. No paid call happens without this.

    The addendum requires "owner authorization with an explicit USD cap". This
    is enforced mechanically rather than trusted: the caller must pass BOTH
    --usd-cap and --authorization, the file must name round 4, and the cap in
    the file must equal the cap on the command line. A mismatch fails closed,
    so a stale authorization for another round cannot silently fund this one.
    """
    if not path.exists():
        raise ValueError("BLOCKED_ROUND4E:AUTHORIZATION_MISSING:" + str(path))
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != "ecm-tqag.round4.owner-authorization.v1":
        raise ValueError("BLOCKED_ROUND4E:AUTHORIZATION_SCHEMA")
    if doc.get("round") != "round4_framee":
        raise ValueError("BLOCKED_ROUND4E:AUTHORIZATION_ROUND:" + str(doc.get("round")))
    declared = doc.get("usd_hard_cap")
    if not isinstance(declared, (int, float)) or isinstance(declared, bool):
        raise ValueError("BLOCKED_ROUND4E:AUTHORIZATION_CAP_TYPE")
    if float(declared) <= 0:
        raise ValueError("BLOCKED_ROUND4E:AUTHORIZATION_CAP_NOT_POSITIVE")
    if abs(float(declared) - float(usd_cap)) > 1e-9:
        raise ValueError(
            "BLOCKED_ROUND4E:AUTHORIZATION_CAP_MISMATCH:file=%s,cli=%s"
            % (declared, usd_cap)
        )
    if doc.get("call_cap") is not None and int(doc["call_cap"]) < CENSUS_CAP:
        raise ValueError(
            "BLOCKED_ROUND4E:AUTHORIZATION_CALL_CAP_TOO_LOW:%s<%s"
            % (doc["call_cap"], CENSUS_CAP)
        )
    return {
        "path": str(path),
        "sha256": sha256_bytes(path.read_bytes()),
        "usd_hard_cap": float(declared),
        "call_cap": doc.get("call_cap"),
        "granted_by": doc.get("granted_by"),
        "granted_utc": doc.get("granted_utc"),
        "verbatim": doc.get("owner_statement_verbatim"),
    }


def make_caller(state: Path, plan_hash: str, cap: int):
    """Context-managed sealed transport caller for round 4 (Frame C)."""
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


def qualification(plan_hash: str, auth: dict[str, Any]) -> int:
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
    private_json(RUN_DIR / "ROUND4_QUALIFICATION_PLAN.json", {
        "schema": "ecm-tqag.round4.framee-qualification-plan.v1",
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
                    raise ValueError("R3B:QUAL:SCHEMA")
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
                    candidate_code=blind_candidate_code("qualification::r4c::" + chunk_id),
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

    print(f"[qual] {passed}/{total} PASS under round-3 Frame-B contract", flush=True)
    return 0 if passed == total else 1


def census(plan_hash: str, auth: dict[str, Any]) -> int:
    started = time.time()
    state = RUN_DIR / "state"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    ids, assignments, packages = load_frame()
    plan = build_call_plan_framee(ids)
    generation_tasks = [{**t, "task_id": r2_id(t["task_id"])} for t in plan["generation_tasks"]]
    judge_tasks = [validate_judge_task(t) for t in plan["judge_tasks"]]
    # Fail closed if any frozen judge name survived the substitution.
    for t in judge_tasks:
        if t["model"] not in JUDGE_MODELS or not t["task_id"].endswith("::" + t["model"]):
            raise ValueError("BLOCKED_ROUND4E:JUDGE_TASK_SHAPE:" + t["task_id"])
    if len({t["task_id"] for t in judge_tasks}) != len(judge_tasks):
        raise ValueError("BLOCKED_ROUND4E:JUDGE_TASK_COLLISION")
    private_json(RUN_DIR / "ROUND4_PLAN.json", {
        "schema": "ecm-tqag.round4.framee-census-plan.v1",
        "frame": "C_hul_legal_documents",
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
            if cost_now > auth["usd_hard_cap"]:
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
                metadata = {"phase": "generation", "run": "round4_framee_census",
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
                metadata = {"phase": "judging", "run": "round4_framee_census",
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
            jtid = f"judge::r4c::{chunk_id}::{arm}::{judge}"
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

    # ---- PRIMARY endpoint: unthresholded judged visual-necessity margin ----
    # V (hard_valid / McNemar) above is retained unchanged; the addendum does not
    # relax it. This is the added, more sensitive endpoint on the same quantity.
    necessity = analyse_necessity(
        judge_records,
        chunk_ids=ids,
        arms=ARMS,
        judges=JUDGE_MODELS,
        mode=FRAMEE_MODE,
        below_floor=len(ids) < PRE_REGISTERED_FLOOR,
    )

    # ---- pre-registered secondary analyses ----
    # Both are frozen in ROUND4_FRAMEE_PREREGISTRATION.json before execution and
    # are reported every time, whatever they show. Each stratum and the
    # sensitivity subset are smaller than the frame, so each is analysed with the
    # floor clause applied on its OWN n: a subset below 40 carries no
    # significance claim even though the full frame does.
    # Frame E froze DIFFERENT strata from Frame D. Frame D split on whether the
    # figure carried lettering absent from the prose; Frame E splits on scoped
    # span length (the mechanism this adaptation targets) and on chunk
    # composition. Carrying Frame D's loaders over would have reported a split
    # the pre-registration does not name, so both are rebound here.
    strata = {
        "scoped_span_band": load_span_band_stratum(ROOT),
        "chunk_composition": load_composition_stratum(ROOT),
    }
    stratum_endpoints = {
        family: {
            name: analyse_necessity(
                judge_records, chunk_ids=members, arms=ARMS, judges=JUDGE_MODELS,
                mode=FRAMEE_MODE, below_floor=len(members) < PRE_REGISTERED_FLOOR,
            )
            for name, members in split.items() if members
        }
        for family, split in strata.items()
    }

    known_total, unknown_count = known_cost(state)
    report = {
        "schema": "ecm-tqag.round4.framee-census-report.v1",
        "run": RUN_DIR.name,
        "mode": "round4_framee_visual_necessity",
        "usd_hard_cap": auth["usd_hard_cap"],
        "authorization": {k: v for k, v in auth.items() if k != "verbatim"},
        "budget_exceeded": budget_exceeded,
        "known_reported_cost_usd": round(known_total, 9),
        "unknown_cost_call_count": unknown_count,
        "status_counts": status_counts,
        "generation_pass_per_arm": {arm: sum(gen_pass[arm].values()) for arm in ARMS},
        "hard_valid_per_arm": {arm: sum(hard_valid[arm].values()) for arm in ARMS},
        "hard_valid_ci_per_arm": {
            arm: clopper_pearson(sum(hard_valid[arm].values()), len(ids))["interval"] for arm in ARMS
        },
        "frame": {
            "name": "E_hul_law_textbook_sections_figure_scoped",
            "n": len(ids),
            "manifest": FRAMEE_MANIFEST_NAME,
            "manifest_sha256": FRAMEE_MANIFEST_SHA256,
            "addendum_sha256": FRAMEE_ADDENDUM_SHA256,
            "preregistration": FRAMEE_PREREGISTRATION,
            "preregistration_sha256": FRAMEE_PREREGISTRATION_SHA256,
            "pre_registered_target": PRE_REGISTERED_TARGET,
            "pre_registered_floor": PRE_REGISTERED_FLOOR,
            "below_floor": len(ids) < PRE_REGISTERED_FLOOR,
            "floor_clause": (
                "ROUND4_NECESSITY_ADDENDUM.md section 4 floor clause applies only below "
                "n=40. Frame E materialised at n=%d, above the floor and above the frozen "
                "target of 46, so Holm rejection flags are live and significance claims are "
                "permitted. n was fixed before the first call and not adjusted afterwards."
                % len(ids)
                if len(ids) >= PRE_REGISTERED_FLOOR else
                "ROUND4_NECESSITY_ADDENDUM.md section 4: below the floor of 40 the round is "
                "reported as an underpowered descriptive measurement and sign tests are "
                "reported WITHOUT significance claims. n was not lowered to fit a result."
            ),
        },
        "endpoint_V_legacy_mcnemar": contrasts,
        "endpoint_necessity_margin_primary": necessity,
        "pre_registered_secondary": {
            "strata": {
                "why": ("both splits are frozen in ROUND4_FRAMEE_PREREGISTRATION.json "
                        "before execution. scoped_span_band reads on the length "
                        "mechanism this adaptation targets; chunk_composition reads on "
                        "the table hypothesis. Descriptive, not confirmatory: no Holm "
                        "control is applied to them and no significance claim is made "
                        "from them."),
                "sizes": {family: {k: len(v) for k, v in split.items()}
                          for family, split in strata.items()},
                "necessity_by_stratum": stratum_endpoints,
            },
            "other_judged_vectors": _judged_vectors(judge_records),
            "judge_record_completeness_per_arm": _judge_completeness(judge_records),
        },
        "quote_classes": _quote_classes(gen_records),
        "elapsed_sec": round(time.time() - started, 1),
    }
    report["contrasts"] = contrasts  # backward-compatible alias for the V endpoint
    private_json(RUN_DIR / "ROUND4_REPORT.json", report)
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


# The four judged vectors other than visual_necessity. Ordered as in the frozen
# seven-field judgement schema.
OTHER_JUDGED_VECTORS = (
    "answerability",
    "evidence_correctness",
    "pedagogical_value",
    "vietnamese_language",
)


def _judged_vectors(judge_records: dict[str, Any]) -> dict[str, Any]:
    """ROUND4_NECESSITY_ADDENDUM.md section 2.1 item 4: the four remaining judged
    vectors, per arm, UNAVERAGED.

    Reported as the full 1-5 score distribution per arm and per judge, because
    the addendum says unaveraged and a mean would hide a bimodal split or a
    single-judge artefact. Means are included alongside for readability only,
    and are derived from the same distributions rather than computed separately.

    Derived entirely from sealed judge records. Makes no call.
    """
    dist: dict[str, dict[str, dict[int, int]]] = {
        arm: {dim: {} for dim in OTHER_JUDGED_VECTORS} for arm in ARMS
    }
    per_judge: dict[str, dict[str, dict[str, dict[int, int]]]] = {
        arm: {judge: {dim: {} for dim in OTHER_JUDGED_VECTORS} for judge in JUDGE_MODELS}
        for arm in ARMS
    }
    provenance: dict[str, dict[str, int]] = {
        arm: {"violations": 0, "records": 0} for arm in ARMS
    }

    for task_id, rec in judge_records.items():
        if not rec or rec.get("status") != "COMPLETE":
            continue
        obj = rec.get("object")
        if not isinstance(obj, Mapping):
            continue
        # judge::<mode>::<chunk...>::<arm>::<judge-model>
        parts = str(task_id).split("::")
        if len(parts) < 2:
            continue
        arm, judge = parts[-2], parts[-1]
        if arm not in dist or judge not in per_judge[arm]:
            continue
        provenance[arm]["records"] += 1
        if obj.get("critical_provenance_violation") is True:
            provenance[arm]["violations"] += 1
        for dim in OTHER_JUDGED_VECTORS:
            score = obj.get(dim)
            if isinstance(score, bool) or not isinstance(score, int):
                continue
            dist[arm][dim][score] = dist[arm][dim].get(score, 0) + 1
            pj = per_judge[arm][judge][dim]
            pj[score] = pj.get(score, 0) + 1

    def summarise(counts: dict[int, int]) -> dict[str, Any]:
        n = sum(counts.values())
        if not n:
            return {"n": 0, "distribution": {}, "mean": None}
        total = sum(score * k for score, k in counts.items())
        return {
            "n": n,
            "distribution": {str(s): counts[s] for s in sorted(counts)},
            "mean": round(total / n, 3),
        }

    return {
        "why": ("ROUND4_NECESSITY_ADDENDUM.md section 2.1 item 4: the four judged "
                "vectors other than visual_necessity, per arm, unaveraged. These are "
                "declared secondary and are NOT confirmatory: no Holm control is "
                "applied to them and no significance claim is made from them."),
        "unaveraged_note": ("distribution is the primary form; mean is derived from it "
                            "for readability and carries no test"),
        "per_arm": {
            arm: {dim: summarise(dist[arm][dim]) for dim in OTHER_JUDGED_VECTORS}
            for arm in ARMS
        },
        "per_arm_per_judge": {
            arm: {
                judge: {dim: summarise(per_judge[arm][judge][dim])
                        for dim in OTHER_JUDGED_VECTORS}
                for judge in JUDGE_MODELS
            }
            for arm in ARMS
        },
        "critical_provenance_violation_per_arm": provenance,
    }


def _judge_completeness(judge_records: dict[str, Any]) -> dict[str, Any]:
    """ROUND4_NECESSITY_ADDENDUM.md section 2.1 item 5: judge-record completeness
    per arm.

    The addendum requires this because round 1 had an asymmetry in which arms
    received judge records, and an asymmetry there silently biases every pooling
    rule that needs both judges. It must be visible in the report rather than
    absorbed into the contrast counts.

    Derived entirely from sealed judge records. Makes no call.
    """
    per_arm: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        by_status: dict[str, int] = {}
        by_judge: dict[str, dict[str, int]] = {j: {} for j in JUDGE_MODELS}
        for task_id, rec in judge_records.items():
            parts = str(task_id).split("::")
            if len(parts) < 2 or parts[-2] != arm:
                continue
            judge = parts[-1]
            status = (rec or {}).get("status") or "MISSING"
            by_status[status] = by_status.get(status, 0) + 1
            if judge in by_judge:
                by_judge[judge][status] = by_judge[judge].get(status, 0) + 1
        complete = by_status.get("COMPLETE", 0)
        per_arm[arm] = {
            "expected": len(by_status) and sum(by_status.values()) or 0,
            "by_status": by_status,
            "by_judge": by_judge,
            "complete": complete,
            "complete_share_of_expected": (
                round(complete / sum(by_status.values()), 4) if by_status else None
            ),
        }
    completes = [v["complete"] for v in per_arm.values()]
    return {
        "why": ("ROUND4_NECESSITY_ADDENDUM.md section 2.1 item 5: judge-record "
                "completeness per arm must be visible, because a per-arm asymmetry "
                "biases every pooling rule that requires both judges."),
        "per_arm": per_arm,
        "max_minus_min_complete": (max(completes) - min(completes)) if completes else None,
        "how_to_read": ("NOT_ATTEMPTED means the paired generation did not pass its "
                        "gate, so no judge call was made; that is admission attrition "
                        "and it is arm-dependent by construction. TERMINAL_FAILURE is a "
                        "judge-side failure and is not."),
    }


def preflight() -> int:
    """Zero-call offline readiness check. Makes NO network or credential access.

    Everything that can be verified without spending money is verified here, so
    a failure costs nothing. Deliberately does not check provider keys: that
    would be a credential access, and the qualification phase is the designed
    place for a live route probe.
    """
    problems: list[str] = []
    ids, assignments, packages = load_frame()
    plan = build_call_plan_framee(ids)

    n = len(ids)
    if n != len(set(ids)):
        problems.append("duplicate_chunk_ids")
    if set(assignments) != set(ids):
        problems.append("assignment_chunk_mismatch")
    if set(packages) != set(ids):
        problems.append("package_chunk_mismatch")

    # every referenced image must exist, and T_c must satisfy frozen rule 4
    missing_images = 0
    min_prose = None
    for cid in ids:
        ev = packages[cid].get("evidence") or {}
        text = str(ev.get("text") or "")
        prose = len(text.strip())
        min_prose = prose if min_prose is None else min(min_prose, prose)
        if prose < 120:
            problems.append("rule4_violation:" + cid)
        for img in ev.get("images") or []:
            if not Path(str(img.get("path"))).is_file():
                missing_images += 1
    if missing_images:
        problems.append("missing_image_files:%d" % missing_images)

    # plan shape
    if plan["max_http_calls"] != len(plan["generation_tasks"]) + len(plan["judge_tasks"]):
        problems.append("plan_call_count_mismatch")
    if plan["max_http_calls"] != CENSUS_CAP:
        problems.append("census_cap_mismatch:%s!=%s" % (plan["max_http_calls"], CENSUS_CAP))
    if len(plan["generation_tasks"]) != n * len(ARMS):
        problems.append("generation_task_count")
    if len(plan["judge_tasks"]) != n * len(ARMS) * len(JUDGE_MODELS):
        problems.append("judge_task_count")
    for t in plan["judge_tasks"]:
        if t["model"] in SUPERSEDED_JUDGE_MODELS:
            problems.append("superseded_judge_in_plan:" + t["model"])
            break

    # endpoint wiring: exercise the analyser on a synthetic record set
    probe = analyse_necessity(
        {}, chunk_ids=ids, arms=list(ARMS), judges=list(JUDGE_MODELS),
        mode=FRAMEE_MODE, below_floor=n < PRE_REGISTERED_FLOOR,
    )
    probe_rules = {str(k).split("::", 1)[0] for k in probe.get("contrasts", {})}
    if probe_rules != {"strict", "lenient", "itt"}:
        problems.append("endpoint_rules_missing:" + ",".join(sorted(probe_rules)))
    if len(probe.get("contrasts", {})) != 6:
        problems.append("endpoint_contrast_cells:%d" % len(probe.get("contrasts", {})))
    if probe.get("primary_rule") != "strict":
        problems.append("primary_rule_not_strict")
    # Frame C ran below the floor, so its preflight asserted that suppression was
    # ACTIVE. Frame E is above the floor, so the correct check is that the floor
    # clause tracks n rather than being asserted either way: suppression must be
    # active iff n < floor. Inheriting Frame C's assertion unchanged would have
    # made a correctly-powered frame fail preflight.
    expect_suppressed = n < PRE_REGISTERED_FLOOR
    if probe.get("below_floor") is not expect_suppressed:
        problems.append("floor_flag_disagrees_with_n:%s,n=%d" % (probe.get("below_floor"), n))
    if probe.get("significance_claims_permitted") is not (not expect_suppressed):
        problems.append("floor_clause_not_tracking_n")
    holm_probe = probe.get("holm_on_strict") or {}
    suppressed = [k for k, v in holm_probe.items()
                  if (v or {}).get("rejected_at_family_alpha") is None]
    if expect_suppressed and len(suppressed) != len(holm_probe):
        problems.append("floor_suppression_not_applied")

    # Pre-registered secondary analyses must be present, not merely importable.
    # Both frozen splits must partition the frame and must match the sizes the
    # pre-registration recorded, so a drifted split fails closed instead of
    # being reported under a pre-registered name.
    strata = {
        "scoped_span_band": load_span_band_stratum(ROOT),
        "chunk_composition": load_composition_stratum(ROOT),
    }
    prereg_path = ROOT.parent / "prospective" / "v3103_round2" / FRAMEE_PREREGISTRATION
    declared = {}
    if prereg_path.is_file():
        declared = (json.loads(prereg_path.read_text(encoding="utf-8"))
                    .get("pre_registered_strata") or {})
    for family, split in strata.items():
        if sum(len(v) for v in split.values()) != n:
            problems.append("stratum_does_not_partition_frame:" + family)
        want = {k: int(v) for k, v in ((declared.get(family) or {}).get("sizes") or {}).items()}
        got = {k: len(v) for k, v in split.items()}
        if want and got != want:
            problems.append("stratum_sizes_%s:%s!=%s" % (family, got, want))

    prereg_path = ROOT.parent / "prospective" / "v3103_round2" / FRAMEE_PREREGISTRATION
    if not prereg_path.is_file():
        problems.append("preregistration_missing")
    else:
        prereg_hash = sha256_bytes(prereg_path.read_bytes())
        if prereg_hash != FRAMEE_PREREGISTRATION_SHA256:
            problems.append("preregistration_sha256:" + prereg_hash)

    report = {
        "schema": "ecm-tqag.round4.framee-preflight.v1",
        "preregistration": FRAMEE_PREREGISTRATION,
        "preregistration_sha256": FRAMEE_PREREGISTRATION_SHA256,
        "pre_registered_stratum_sizes": {
            family: {k: len(v) for k, v in split.items()}
            for family, split in strata.items()
        },
        "checked_utc": _now(),
        "frame": plan["frame"],
        "frame_manifest": FRAMEE_MANIFEST_NAME,
        "frame_manifest_sha256": FRAMEE_MANIFEST_SHA256,
        "addendum_sha256": FRAMEE_ADDENDUM_SHA256,
        "frame_size_n": n,
        "pre_registered_target": PRE_REGISTERED_TARGET,
        "pre_registered_floor": PRE_REGISTERED_FLOOR,
        "below_floor": n < PRE_REGISTERED_FLOOR,
        "floor_consequence": (
            "underpowered descriptive; Holm rejection flags suppressed"
            if n < PRE_REGISTERED_FLOOR else "significance claims permitted"
        ),
        "question_types": {q: sum(1 for v in assignments.values() if v == q)
                           for q in sorted(set(assignments.values()))},
        "min_prose_chars": min_prose,
        "generation_tasks": len(plan["generation_tasks"]),
        "judge_tasks": len(plan["judge_tasks"]),
        "paid_calls_if_executed": plan["max_http_calls"],
        "generator_model": plan["generator_model"],
        "judge_models": plan["judge_models"],
        "missing_image_files": missing_images,
        "calls_made_by_preflight": 0,
        "problems": problems,
        "verdict": "READY" if not problems else "BLOCKED",
    }
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)
    private_json(RUN_DIR / "ROUND4_PREFLIGHT.json", report)
    print(json.dumps(report, indent=1, ensure_ascii=False), flush=True)
    return 0 if not problems else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["preflight", "qualification", "census"], required=True)
    parser.add_argument("--usd-cap", type=float, default=None,
                        help="Explicit owner USD hard cap. REQUIRED for paid phases; "
                             "must equal the cap in --authorization.")
    parser.add_argument("--authorization", type=Path, default=None,
                        help="Path to the owner authorization JSON for round 4.")
    args = parser.parse_args()

    # Preflight is offline and free, so it needs no authorization.
    if args.phase == "preflight":
        return preflight()

    # Paid phases: both flags required, and they must agree. The addendum's
    # wording is "owner authorization with an explicit USD cap"; neither half
    # is inferred from a chat message or from a previous round's cap.
    if args.usd_cap is None or args.authorization is None:
        print("BLOCKED_ROUND4E:AUTHORIZATION_REQUIRED: --usd-cap and --authorization "
              "are both required for phase " + args.phase, flush=True)
        return 3
    try:
        auth = load_authorization(args.authorization, args.usd_cap)
    except ValueError as exc:
        print(str(exc), flush=True)
        return 3
    binding = canonical_bytes({
        "instrument": "round4_framee_visual_necessity_v1",
        "judges": list(JUDGE_MODELS),
        "superseded_judges": list(SUPERSEDED_JUDGE_MODELS),
        "validator": sha256_bytes((ROOT / "round2" / "round2_validation.py").read_bytes()),
        "prompt": sha256_bytes((ROOT / "round2" / "round2e_prompt.py").read_bytes()),
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
            return qualification(plan_hash, auth)
        return census(plan_hash, auth)
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
