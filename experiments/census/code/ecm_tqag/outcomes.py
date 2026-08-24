"""Frozen membership and fail-closed endpoint derivation for the official experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
TYPE_ASSIGNMENT_PATH = ROOT / "prospective/v310/TYPE_ASSIGNMENT.json"
DATASET_PATH = ROOT / "dataset/dataset_manifest.json"
PILOT_MANIFEST_PATH = ROOT / "prospective/v310/PILOT_MANIFEST.json"
# LEGACY frame arms. Audit-bound to the round-1 16-chunk records: these three
# arms are what those records contain, so the replay path must not gain a fourth.
# The current census arm set lives in contracts.ARMS.
ARMS = ("ecm_full", "direct", "structured_no_contract")
# LEGACY replay raters (see execution.JUDGE_MODELS). Census raters live in
# routes.JUDGE_MODELS_R2C.
JUDGE_MODELS = ("claude-sonnet-5", "gpt-5.6-terra")
JUDGES = JUDGE_MODELS
JUDGE_KEYS = frozenset({
    "answerability", "critical_provenance_violation", "evidence_correctness",
    "pedagogical_value", "rationale", "vietnamese_language", "visual_necessity",
})


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_OFFICIAL_FRAME:" + reason)


def authoritative_frame() -> dict[str, Any]:
    """Load and cross-check the frozen assignment against the TLV census."""
    assignment = json.loads(TYPE_ASSIGNMENT_PATH.read_text(encoding="utf-8"))
    dataset_raw = DATASET_PATH.read_bytes()
    dataset = json.loads(dataset_raw)
    pilot_manifest = json.loads(PILOT_MANIFEST_PATH.read_text(encoding="utf-8"))
    dataset_sha256 = hashlib.sha256(dataset_raw).hexdigest()
    assignment_sha256 = hashlib.sha256(TYPE_ASSIGNMENT_PATH.read_bytes()).hexdigest()
    pilot_manifest_sha256 = hashlib.sha256(PILOT_MANIFEST_PATH.read_bytes()).hexdigest()
    assignments = assignment["type_assignment"]["assignments"]
    dataset_ids = {row["chunk_id"] for row in dataset["packages"] if row.get("condition") == "TLV"}
    full_ids = tuple(assignments)  # authoritative frozen order
    pilot_ids = tuple(row["chunk_id"] for row in assignment["pilot_selection"]["selected"])
    manifest_pilot_ids = tuple(row["chunk_id"] for row in pilot_manifest["selection"]["items"])
    if assignment.get("dataset_sha256") != dataset_sha256:
        raise _blocked("DATASET_BINDING")
    if (pilot_manifest.get("dataset", {}).get("sha256") != dataset_sha256
            or pilot_manifest.get("selection", {}).get("source") != "prospective/v310/TYPE_ASSIGNMENT.json"):
        raise _blocked("PILOT_BINDING")
    if len(full_ids) != 16 or len(set(full_ids)) != 16 or set(full_ids) != dataset_ids:
        raise _blocked("AUTHORITATIVE_CENSUS")
    if (len(pilot_ids) != 4 or len(set(pilot_ids)) != 4
            or not set(pilot_ids) <= set(full_ids) or pilot_ids != manifest_pilot_ids):
        raise _blocked("AUTHORITATIVE_PILOT")
    return {
        "full_chunk_ids": full_ids,
        "pilot_chunk_ids": pilot_ids,
        "assignments": dict(assignments),
        "dataset_sha256": dataset_sha256,
        "type_assignment_sha256": assignment_sha256,
        "pilot_manifest_sha256": pilot_manifest_sha256,
    }


def require_official_membership(mode: str, chunk_ids: Sequence[str]) -> tuple[str, ...]:
    frame = authoritative_frame()
    expected = frame["pilot_chunk_ids"] if mode == "pilot" else frame["full_chunk_ids"] if mode == "full" else None
    if expected is None or tuple(chunk_ids) != expected:
        raise _blocked("MEMBERSHIP")
    return expected


# Public immutable tuples used by the active planner, runner, tests, and analysis.
class _LazyFrame:
    """Frame A is loaded on first use, not at import time.

    Frame C (the 24-chunk census) resolves its own membership in
    ``ecm_tqag.frame_plan``, so importing this module must not require the
    Frame-A artifacts to be present.
    """

    _value: dict[str, Any] | None = None

    def _resolve(self) -> dict[str, Any]:
        if self._value is None:
            self._value = authoritative_frame()
        return self._value

    def __getitem__(self, key: str) -> Any:
        return self._resolve()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._resolve().get(key, default)


_FRAME = _LazyFrame()


def __getattr__(name: str):
    """Resolve the legacy 16-chunk frame only when actually asked for.

    Frame C (n=24) never touches these, so importing this module must not
    require the legacy frame artifacts to be present.
    """
    if name == "FULL_IDS":
        return tuple(_FRAME["full_chunk_ids"])
    if name == "PILOT_IDS":
        return tuple(_FRAME["pilot_chunk_ids"])
    raise AttributeError(name)


def _terminal_generation_ok(record: Any) -> bool:
    return (
        isinstance(record, Mapping)
        and record.get("status") == "COMPLETE"
        and record.get("gates_passed") is True
        and isinstance(record.get("object"), Mapping)
    )


def _strict_judgement(record: Any) -> bool:
    if not isinstance(record, Mapping) or record.get("status") != "COMPLETE" or record.get("gates_passed") is not True:
        return False
    obj = record.get("object")
    if not isinstance(obj, Mapping) or set(obj) != JUDGE_KEYS:
        return False
    for key in JUDGE_KEYS - {"critical_provenance_violation", "rationale"}:
        value = obj.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            return False
    return (
        isinstance(obj.get("critical_provenance_violation"), bool)
        and isinstance(obj.get("rationale"), str)
        and bool(obj["rationale"].strip())
    )


def derive_hard_valid(generation: Any, judgements: Any) -> bool:
    """Derive, never accept, the primary endpoint from terminal artifacts."""
    if not _terminal_generation_ok(generation):
        return False
    if not isinstance(judgements, Mapping) or set(judgements) != set(JUDGE_MODELS):
        return False
    if not all(_strict_judgement(judgements[judge]) for judge in JUDGE_MODELS):
        return False
    objects = [judgements[judge]["object"] for judge in JUDGE_MODELS]
    return all(
        not obj["critical_provenance_violation"]
        and obj["evidence_correctness"] >= 3
        and obj["visual_necessity"] >= 3
        and obj["answerability"] >= 3
        for obj in objects
    )


def _failure_reasons(generation: Any, judgements: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _terminal_generation_ok(generation):
        reasons.append("generation_missing_or_terminal_failure")
    for judge in JUDGE_MODELS:
        record = judgements.get(judge)
        if not _strict_judgement(record):
            reasons.append("judge_schema" if isinstance(record, Mapping) and record.get("status") == "COMPLETE" else "judge_missing_or_terminal_failure")
            continue
        obj = record["object"]
        if obj["critical_provenance_violation"]:
            reasons.append("judge_critical_provenance_violation")
        for key in ("evidence_correctness", "visual_necessity", "answerability"):
            if obj[key] < 3:
                reasons.append("judge_threshold_" + key)
    return sorted(set(reasons))


def derive_outcomes(*, plan: Mapping[str, Any], generation_records: Mapping[str, Any], judge_records: Mapping[str, Any]) -> dict[str, Any]:
    """Build the only analysis-admissible outcome artifact from terminal records.

    Missing expected records are retained as false ITT outcomes. Unexpected records,
    arbitrary membership, or a malformed task plan fail closed.
    """
    if not isinstance(plan, Mapping) or plan.get("schema") != "ecm-tqag.v3.10.call-plan.v1":
        raise _blocked("PLAN")
    mode = plan.get("mode")
    ids = require_official_membership(str(mode), plan.get("chunk_ids", ()))
    expected_generation = {
        f"generation::{mode}::{chunk}::{arm}" for chunk in ids for arm in ARMS
    }
    expected_judges = {
        f"judge::{mode}::{chunk}::{arm}::{judge}"
        for chunk in ids for arm in ARMS for judge in JUDGE_MODELS
    }
    if not isinstance(generation_records, Mapping) or not isinstance(judge_records, Mapping):
        raise _blocked("RECORD_SET")
    if not set(generation_records) <= expected_generation or not set(judge_records) <= expected_judges:
        raise _blocked("RECORD_SET")
    if {task.get("task_id") for task in plan.get("generation_tasks", []) if isinstance(task, Mapping)} != expected_generation:
        raise _blocked("PLAN")
    if {task.get("task_id") for task in plan.get("judge_tasks", []) if isinstance(task, Mapping)} != expected_judges:
        raise _blocked("PLAN")

    rows: list[dict[str, Any]] = []
    for chunk in ids:
        for arm in ARMS:
            generation_id = f"generation::{mode}::{chunk}::{arm}"
            judgements = {
                judge: judge_records.get(f"judge::{mode}::{chunk}::{arm}::{judge}")
                for judge in JUDGE_MODELS
            }
            generation = generation_records.get(generation_id)
            reasons = _failure_reasons(generation, judgements)
            hard_valid = derive_hard_valid(generation, judgements)
            rows.append({
                "chunk_id": chunk,
                "arm": arm,
                "hard_valid": hard_valid,
                "failure_reasons": [] if hard_valid else reasons or ["hard_valid_failed"],
            })
    return {
        "schema": "ecm-tqag.official.derived-outcomes.v1",
        "mode": mode,
        "chunk_ids": list(ids),
        "rows": rows,
    }


def derive_census_outcomes(records: Any) -> dict[str, list[bool]]:
    """Compatibility helper for nested records; still derives every boolean."""
    full_ids = __getattr__("FULL_IDS")
    if not isinstance(records, Mapping) or set(records) != set(full_ids):
        raise _blocked("RECORD_CENSUS")
    outcomes = {arm: [] for arm in ARMS}
    for chunk in full_ids:
        arms = records[chunk]
        if not isinstance(arms, Mapping) or set(arms) != set(ARMS):
            raise _blocked("RECORD_ARMS")
        for arm in ARMS:
            row = arms[arm]
            outcomes[arm].append(
                derive_hard_valid(row.get("generation"), row.get("judgements"))
                if isinstance(row, Mapping) else False
            )
    return outcomes


__all__ = [
    "ARMS", "JUDGE_MODELS", "JUDGES", "FULL_IDS", "PILOT_IDS",
    "authoritative_frame", "require_official_membership", "derive_hard_valid",
    "derive_outcomes", "derive_census_outcomes",
]
