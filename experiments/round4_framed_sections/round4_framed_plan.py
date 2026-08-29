"""Round-4 Frame-D call plan (section-granularity frame over HUL law textbooks).

`round4_framec_plan` is bound to Frame C by sha256 and must not be edited: the
sealed census that the paper reports loads through it. Frame D is a *fourth*
frame, pre-registered in
`prospective/v3103_round2/ROUND4_FRAMED_PREREGISTRATION.json` before any call,
so it gets its own plan module rather than a mutated copy of Frame C's.

Everything other than the frame is unchanged from round 2e / 3 / 4: same
generator, same three arm prompts with the minimal D3 clarification, same
repaired gates, same judge families, same seven-field judgement schema, same ITT
accounting, same zero retry / fallback / replacement.

Two differences from Frame C, both declared as deviations in the
pre-registration and both consequences of the frame rather than of the
instrument:

  1. RULE 3 READING. Frame C operationalised addendum rule 3 as "largest
     EMBEDDED RASTER >= 203 px". Frame D reads the frozen text literally -- "at
     least one extracted figure crop resolvable on disk" -- which a rendered
     vector region satisfies. This is the deviation the frame-C determination
     recorded as an owner option and declined to apply retrospectively; here it
     is pre-registered ahead of execution instead, which is the only admissible
     way to adopt it.

  2. ABOVE THE FLOOR. Frame C materialised at n=24, below the addendum's
     pre-specified floor of 40, so §4's floor clause forced underpowered-
     descriptive reporting with Holm flags suppressed. Frame D materialises at
     n=67, above the floor and above the frozen target of 46, so significance
     claims are permitted. `below_floor` is computed from n, never asserted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from ecm_tqag.v310_contracts import ARMS, GENERATOR_MODEL

# Frame C's frozen operationalisation of addendum rule 3, used ONLY to recompute
# the pre-registered sensitivity subset. Frame D's own admission rule is the
# literal reading and is applied by the dataset builder, not here.
FRAMEC_CROP_FLOOR_PX = 203

from .round2c_routes import JUDGE_MODELS_R2C

FRAMED_MODE = "r4d"

# The parent addendum, unchanged. Frame D does not relax V, does not move the
# threshold 3, and does not modify the gate G.
FRAMED_ADDENDUM_SHA256 = (
    "fea9078d43ee5ac32578233805425a83f1453f6fce374c9baf77687e4e9b3dfb"
)

# The pre-registration that authorises this frame's existence, written and
# frozen before the first call.
FRAMED_PREREGISTRATION = "ROUND4_FRAMED_PREREGISTRATION.json"
FRAMED_PREREGISTRATION_SHA256 = (
    "b487218b5e0955a74d7f5ade4d32f48f18164cf50aca0c80413b30c2c25384de"
)

FRAMED_MANIFEST_NAME = "dataset_manifest_framed_20260829T195643Z.json"
FRAMED_MANIFEST_SHA256 = (
    "2aca4def1d411097ca0917e4398f3bf7ec3c03441aa97ecd71b00b48f56594a2"
)

# Unchanged from the addendum. n=67 clears both.
PRE_REGISTERED_TARGET = 46
PRE_REGISTERED_FLOOR = 40


def load_framed(root: Path | str) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Return (chunk_ids, question_type assignments, manifest) for Frame D.

    Fails closed unless the manifest on disk is byte-identical to the one the
    pre-registration was frozen against. Same contract as `load_framec`.
    """
    root = Path(root)
    manifest_path = root / "dataset_framed" / FRAMED_MANIFEST_NAME
    raw = manifest_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FRAMED_MANIFEST_SHA256:
        raise ValueError("BLOCKED_ROUND4D:MANIFEST_SHA256:" + digest)
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema") != "ecm-tqag.multimodal-inputs.v4-work24":
        raise ValueError("BLOCKED_ROUND4D:MANIFEST_SCHEMA")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("BLOCKED_ROUND4D:MANIFEST_PACKAGES")

    chunk_ids: list[str] = []
    assignments: dict[str, str] = {}
    for row in packages:
        chunk_id = row.get("chunk_id")
        qtype = row.get("question_type")
        if not isinstance(chunk_id, str) or qtype not in {"short_answer", "multiple_choice"}:
            raise ValueError("BLOCKED_ROUND4D:MANIFEST_ROW")
        if chunk_id in assignments:
            raise ValueError("BLOCKED_ROUND4D:DUPLICATE_CHUNK")
        # Rule 4 must already have been applied upstream: an unsatisfiable gate
        # is a dataset defect, not a measurement.
        text = ((row.get("evidence") or {}).get("text") or "")
        if len("".join(str(text).split())) < 120:
            raise ValueError("BLOCKED_ROUND4D:RULE4_NOT_APPLIED:" + chunk_id)
        chunk_ids.append(chunk_id)
        assignments[chunk_id] = qtype
    return chunk_ids, assignments, manifest


def load_stratum(root: Path | str) -> dict[str, list[str]]:
    """The pre-registered secondary stratum: does the figure carry lettering the
    prose does not?

    Frozen in the pre-registration before execution, and derived here from the
    manifest rather than recomputed, so the split cannot drift.
    """
    _, _, manifest = load_framed(root)
    strata: dict[str, list[str]] = {"image_only_content": [], "no_image_only_content": []}
    for row in manifest["packages"]:
        ft = (row.get("evidence") or {}).get("figure_text") or {}
        surplus = ft.get("surplus_words") or []
        key = "image_only_content" if surplus else "no_image_only_content"
        strata[key].append(row["chunk_id"])
    return strata


def load_sensitivity_subset(root: Path | str) -> list[str]:
    """Chunk ids that would also qualify under Frame C's frozen rule-3 reading.

    Reported every time as a sensitivity analysis, so a reader can see whether
    the deviation of §1 carries the result.

    Derived from the image records, not from a boolean flag: neither dataset
    builder writes `frame_c_rule3_eligible` at package level, so reading that
    key returned an empty subset and would have silently voided the
    pre-registered sensitivity analysis. The frozen reading is "largest EMBEDDED
    RASTER on the page has min-dimension >= 203 px", which is exactly what is
    recomputed here. Verified to reproduce the 28-chunk strict frame.
    """
    _, _, manifest = load_framed(root)
    subset: list[str] = []
    for row in manifest["packages"]:
        images = (row.get("evidence") or {}).get("images") or []
        for image in images:
            if image.get("source") != "embedded_raster":
                continue
            width = image.get("width")
            height = image.get("height")
            if not isinstance(width, int) or not isinstance(height, int):
                continue
            if min(width, height) >= FRAMEC_CROP_FLOOR_PX:
                subset.append(row["chunk_id"])
                break
    return subset


def build_call_plan_framed(chunk_ids: Sequence[str]) -> dict[str, Any]:
    """Frame-D plan: one generation call per chunk-arm, two judge calls per candidate."""
    ids = list(chunk_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("BLOCKED_ROUND4D:CALL_PLAN")
    generation_tasks: list[dict[str, Any]] = []
    judge_tasks: list[dict[str, Any]] = []
    for chunk_id in ids:
        for arm in ARMS:
            source_task_id = f"generation::{FRAMED_MODE}::{chunk_id}::{arm}"
            generation_tasks.append({
                "task_id": source_task_id,
                "phase": "generation",
                "mode": FRAMED_MODE,
                "chunk_id": chunk_id,
                "arm": arm,
                "model": GENERATOR_MODEL,
                "calls": 1,
                "retry": 0,
                "fallback": False,
            })
            for judge in JUDGE_MODELS_R2C:
                judge_tasks.append({
                    "task_id": f"judge::{FRAMED_MODE}::{chunk_id}::{arm}::{judge}",
                    "source_task_id": source_task_id,
                    "phase": "judging",
                    "mode": FRAMED_MODE,
                    "chunk_id": chunk_id,
                    "model": judge,
                    "calls": 1,
                    "retry": 0,
                    "fallback": False,
                    "arm_masked": True,
                })
    tasks = generation_tasks + judge_tasks
    n = len(ids)
    return {
        "schema": "ecm-tqag.round4.framed-call-plan.v1",
        "mode": FRAMED_MODE,
        "frame": "D_hul_law_textbooks_sections",
        "frame_addendum_sha256": FRAMED_ADDENDUM_SHA256,
        "frame_preregistration": FRAMED_PREREGISTRATION,
        "frame_preregistration_sha256": FRAMED_PREREGISTRATION_SHA256,
        "frame_manifest": FRAMED_MANIFEST_NAME,
        "frame_manifest_sha256": FRAMED_MANIFEST_SHA256,
        "frame_size_n": n,
        "pre_registered_target": PRE_REGISTERED_TARGET,
        "pre_registered_floor": PRE_REGISTERED_FLOOR,
        "below_floor": n < PRE_REGISTERED_FLOOR,
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
    "FRAMED_MODE",
    "FRAMED_ADDENDUM_SHA256",
    "FRAMED_PREREGISTRATION",
    "FRAMED_PREREGISTRATION_SHA256",
    "FRAMED_MANIFEST_NAME",
    "FRAMED_MANIFEST_SHA256",
    "PRE_REGISTERED_FLOOR",
    "PRE_REGISTERED_TARGET",
    "build_call_plan_framed",
    "load_framed",
    "load_sensitivity_subset",
    "load_stratum",
]
