"""Round-4 Frame-C call plan (visual-necessity endpoint, frozen frame outside A/B).

`ecm_tqag.execution.build_call_plan` is audit-bound to the official 16-chunk
frame, and `round3_frameb_plan` is bound to Frame B. Round 4 measures a third,
prospectively frozen frame (prospective/v3103_round2/ROUND4_NECESSITY_ADDENDUM.md
v2), so this module supplies a Frame-C-local plan builder instead of modifying
sealed code.

Everything other than the frame and the endpoint is unchanged from round 2e /
round 3: same generator, same three arm prompts with the minimal clarification,
same repaired gates, same substituted judge families, same seven-field judgement
schema, same ITT accounting, same zero retry/fallback/replacement.

The frame loaded here is the RULE-4 CORRECTED manifest. The frame-C builder
carried forward ROUND3_FRAMEB_ADDENDUM rules 3 and 5 but omitted rule 4
(text-sufficiency), leaving two chunks whose T_c held 1 and 4 characters. With an
empty T_c the gate `q ⊑ T_c` is unsatisfiable, so those chunks would have
depressed every arm for a dataset reason and looked like a measured result.
Rule 4 is applied here as frozen -- using the exact measure from
round2/build_frameb.py (prose_chars = len(_FIG_RE.sub('', page_text).strip()),
EXCLUDE if prose_chars < 120, or enum_items >= 3 with prose_chars < 400). Two
earlier corrected manifests were voided: one renamed the manifest schema (which
sealed build_packages rejects) and one used a re-derived prose measure that
dropped 4 chunks instead of 2. Frame size is decided by the frozen rule, never by
a measure invented while fixing the defect. This plan is bound to the surviving
corrected manifest by sha256.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from ecm_tqag.contracts import ARMS, GENERATOR_MODEL

from .routes import JUDGE_MODELS_R2C

FRAMEC_MODE = "r4c"
FRAMEC_ADDENDUM_SHA256 = (
    "fea9078d43ee5ac32578233805425a83f1453f6fce374c9baf77687e4e9b3dfb"
)
FRAMEC_MANIFEST_NAME = "dataset_manifest_rule4_20260816T105100Z.json"
FRAMEC_MANIFEST_SHA256 = (
    "14325616771840623d2dbb8267fea0721255f29178400b1c94732e4b3559d648"
)
# Frame C is below the addendum's pre-specified floor of 40, so §4's floor clause
# applies: executed and reported as an underpowered descriptive measurement.
PRE_REGISTERED_TARGET = 46
PRE_REGISTERED_FLOOR = 40


def load_framec(root: Path | str) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Return (chunk_ids, question_type assignments, manifest) for Frame C.

    Fails closed unless the manifest on disk is byte-identical to the corrected
    manifest this plan was frozen against.
    """
    import hashlib

    root = Path(root)
    manifest_path = root / "dataset_framec" / FRAMEC_MANIFEST_NAME
    raw = manifest_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FRAMEC_MANIFEST_SHA256:
        raise ValueError("BLOCKED_ROUND4:MANIFEST_SHA256:" + digest)
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema") != "ecm-tqag.multimodal-inputs.v4-work24":
        raise ValueError("BLOCKED_ROUND4:MANIFEST_SCHEMA")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("BLOCKED_ROUND4:MANIFEST_PACKAGES")
    chunk_ids: list[str] = []
    assignments: dict[str, str] = {}
    for row in packages:
        chunk_id = row.get("chunk_id")
        qtype = row.get("question_type")
        if not isinstance(chunk_id, str) or qtype not in {"short_answer", "multiple_choice"}:
            raise ValueError("BLOCKED_ROUND4:MANIFEST_ROW")
        if chunk_id in assignments:
            raise ValueError("BLOCKED_ROUND4:DUPLICATE_CHUNK")
        # Rule 4 must already have been applied: an unsatisfiable gate is a
        # dataset defect, not a measurement.
        text = ((row.get("evidence") or {}).get("text") or "")
        if len("".join(str(text).split())) < 120:
            raise ValueError("BLOCKED_ROUND4:RULE4_NOT_APPLIED:" + chunk_id)
        chunk_ids.append(chunk_id)
        assignments[chunk_id] = qtype
    return chunk_ids, assignments, manifest


def build_call_plan_framec(chunk_ids: Sequence[str]) -> dict[str, Any]:
    """Frame-C plan: one generation call per chunk-arm, two judge calls per candidate."""
    ids = list(chunk_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("BLOCKED_ROUND4:CALL_PLAN")
    generation_tasks: list[dict[str, Any]] = []
    judge_tasks: list[dict[str, Any]] = []
    for chunk_id in ids:
        for arm in ARMS:
            source_task_id = f"generation::{FRAMEC_MODE}::{chunk_id}::{arm}"
            generation_tasks.append({
                "task_id": source_task_id,
                "phase": "generation",
                "mode": FRAMEC_MODE,
                "chunk_id": chunk_id,
                "arm": arm,
                "model": GENERATOR_MODEL,
                "calls": 1,
                "retry": 0,
                "fallback": False,
            })
            for judge in JUDGE_MODELS_R2C:
                judge_tasks.append({
                    "task_id": f"judge::{FRAMEC_MODE}::{chunk_id}::{arm}::{judge}",
                    "source_task_id": source_task_id,
                    "phase": "judging",
                    "mode": FRAMEC_MODE,
                    "chunk_id": chunk_id,
                    "model": judge,
                    "calls": 1,
                    "retry": 0,
                    "fallback": False,
                    "arm_masked": True,
                })
    tasks = generation_tasks + judge_tasks
    return {
        "schema": "ecm-tqag.round4.framec-call-plan.v1",
        "mode": FRAMEC_MODE,
        "frame": "C_hul_legal_documents",
        "frame_addendum_sha256": FRAMEC_ADDENDUM_SHA256,
        "frame_manifest": FRAMEC_MANIFEST_NAME,
        "frame_manifest_sha256": FRAMEC_MANIFEST_SHA256,
        "frame_size_n": len(ids),
        "pre_registered_target": PRE_REGISTERED_TARGET,
        "pre_registered_floor": PRE_REGISTERED_FLOOR,
        "below_floor": len(ids) < PRE_REGISTERED_FLOOR,
        "arms": list(ARMS),
        "generator_model": GENERATOR_MODEL,
        "judge_models": list(JUDGE_MODELS_R2C),
        "chunk_ids": ids,
        "generation_tasks": generation_tasks,
        "judge_tasks": judge_tasks,
        "max_http_calls": len(tasks),
        "retry": 0,
        "fallback": False,
        "replacement": False,
    }


__all__ = [
    "FRAMEC_MODE",
    "FRAMEC_ADDENDUM_SHA256",
    "FRAMEC_MANIFEST_NAME",
    "FRAMEC_MANIFEST_SHA256",
    "PRE_REGISTERED_TARGET",
    "PRE_REGISTERED_FLOOR",
    "load_framec",
    "build_call_plan_framec",
]
