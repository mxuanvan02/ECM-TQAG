"""Round-4 Frame-E call plan (figure-scoped evidence span over the same sections).

`round4_framed_plan` is bound to Frame D by sha256 and is NOT edited: the Frame-D
census that reported the unscoped null loads through it. Frame E is a
pre-registered METHOD ADAPTATION, frozen in
`prospective/v3103_round2/ROUND4_FRAMEE_PREREGISTRATION.json` before any call, so
it gets its own plan module.

WHAT CHANGES, AND WHAT DOES NOT

  The UNIT OF ANALYSIS is unchanged: a chunk is still one section of a law
  textbook. What changes is the SPAN the verbatim-quote gate reads -- the
  section's own text on the pages carrying its figure regions, instead of the
  whole section. Median span falls from 7530 to 1571 characters, maximum from
  265885 to 7634.

  Frozen rule 4 is re-applied to that scoped span, which is the only consistent
  choice once the span changes, and drops 7 of Frame D's 67 chunks whose figure
  pages carry almost no prose. n = 60, above the addendum floor of 40 and its
  target of 46.

  Generator, the three arm prompts, the round-2 repaired gate, both judge
  families, the seven-field judgement schema, ITT accounting and the zero
  retry/fallback/replacement discipline are all carried over byte-identical.

NOT AN INDEPENDENT REPLICATION. All 60 Frame-E units are Frame-D units. This is a
second look at the same corpus after its null was seen, and the pre-registration
records that before any number exists.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from ecm_tqag.v310_contracts import ARMS, GENERATOR_MODEL

from .round2c_routes import JUDGE_MODELS_R2C

FRAMEE_MODE = "r4e"

# The parent addendum, unchanged. Frame D does not relax V, does not move the
# threshold 3, and does not modify the gate G.
FRAMEE_ADDENDUM_SHA256 = (
    "fea9078d43ee5ac32578233805425a83f1453f6fce374c9baf77687e4e9b3dfb"
)

# The pre-registration that authorises this frame's existence, written and
# frozen before the first call.
FRAMEE_PREREGISTRATION = "ROUND4_FRAMEE_PREREGISTRATION.json"
FRAMEE_PREREGISTRATION_SHA256 = (
    "000cf1cd50dc190c221880442aa73cdb7dc77c77c91a54cf645f132418eeb024"
)

FRAMEE_MANIFEST_NAME = "dataset_manifest_framee_20260830T093119Z.json"
FRAMEE_MANIFEST_SHA256 = (
    "051db6ac66e09ece70d71391068f32893a76a1fd1186c563b3d24146e78dec52"
)

# Unchanged from the addendum. n=60 clears both.
PRE_REGISTERED_TARGET = 46
PRE_REGISTERED_FLOOR = 40


def load_framee(root: Path | str) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Return (chunk_ids, question_type assignments, manifest) for Frame D.

    Fails closed unless the manifest on disk is byte-identical to the one the
    pre-registration was frozen against. Same contract as `load_framec`.
    """
    root = Path(root)
    manifest_path = root / "dataset_framee" / FRAMEE_MANIFEST_NAME
    raw = manifest_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FRAMEE_MANIFEST_SHA256:
        raise ValueError("BLOCKED_ROUND4E:MANIFEST_SHA256:" + digest)
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema") != "ecm-tqag.multimodal-inputs.v4-work24":
        raise ValueError("BLOCKED_ROUND4E:MANIFEST_SCHEMA")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("BLOCKED_ROUND4E:MANIFEST_PACKAGES")

    chunk_ids: list[str] = []
    assignments: dict[str, str] = {}
    for row in packages:
        chunk_id = row.get("chunk_id")
        qtype = row.get("question_type")
        if not isinstance(chunk_id, str) or qtype not in {"short_answer", "multiple_choice"}:
            raise ValueError("BLOCKED_ROUND4E:MANIFEST_ROW")
        if chunk_id in assignments:
            raise ValueError("BLOCKED_ROUND4E:DUPLICATE_CHUNK")
        # Rule 4 must already have been applied upstream: an unsatisfiable gate
        # is a dataset defect, not a measurement.
        text = ((row.get("evidence") or {}).get("text") or "")
        if len("".join(str(text).split())) < 120:
            raise ValueError("BLOCKED_ROUND4E:RULE4_NOT_APPLIED:" + chunk_id)
        chunk_ids.append(chunk_id)
        assignments[chunk_id] = qtype
    return chunk_ids, assignments, manifest


# The two strata frozen in ROUND4_FRAMEE_PREREGISTRATION.json. Frame D froze a
# DIFFERENT pair (image-only figure lettering, and a frame-C rule-3 sensitivity
# subset); carrying those over would have reported a split this record never
# pre-registered, so they are replaced rather than inherited.
SPAN_BANDS = (
    ("under_1000", 0, 1000),
    ("from_1000_to_2000", 1000, 2000),
    ("from_2000_to_4000", 2000, 4000),
    ("over_4000", 4000, None),
)


def span_band(chars: int) -> str:
    """Frozen band membership for a scoped span length."""
    for name, low, high in SPAN_BANDS:
        if chars >= low and (high is None or chars < high):
            return name
    raise ValueError("BLOCKED_ROUND4E:SPAN_BAND:" + str(chars))


def load_span_band_stratum(root: Path | str) -> dict[str, list[str]]:
    """Pre-registered stratum 1: scoped span length band.

    Reads directly on the length mechanism this adaptation targets. If span
    length is what disabled the gate on Frame D, admission should be flatter
    across these bands than it was across Frame D's.

    Length is `len(evidence.text)` of the manifest, the same raw measure the
    scoped-span report and the quality report use, so the three cannot disagree.
    """
    _, _, manifest = load_framee(root)
    strata: dict[str, list[str]] = {name: [] for name, _, _ in SPAN_BANDS}
    for row in manifest["packages"]:
        text = (row.get("evidence") or {}).get("text") or ""
        strata[span_band(len(text))].append(row["chunk_id"])
    return strata


def load_composition_stratum(root: Path | str) -> dict[str, list[str]]:
    """Pre-registered stratum 2: embedded raster present, versus vector renders only.

    Reads on the owner's hypothesis that necessity fails because the figures are
    only tables. Frame D's executed ablation already contradicted it -- the whole
    measured visual gain sat in the vector-only chunks -- and this stratum keeps
    the same split visible under the scoped gate.
    """
    _, _, manifest = load_framee(root)
    strata: dict[str, list[str]] = {"has_embedded_raster": [], "rendered_vector_only": []}
    for row in manifest["packages"]:
        images = (row.get("evidence") or {}).get("images") or []
        raster = any(image.get("source") == "embedded_raster" for image in images)
        strata["has_embedded_raster" if raster else "rendered_vector_only"].append(
            row["chunk_id"])
    return strata


def build_call_plan_framee(chunk_ids: Sequence[str]) -> dict[str, Any]:
    """Frame-E plan: one generation call per chunk-arm, two judge calls per candidate."""
    ids = list(chunk_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("BLOCKED_ROUND4E:CALL_PLAN")
    generation_tasks: list[dict[str, Any]] = []
    judge_tasks: list[dict[str, Any]] = []
    for chunk_id in ids:
        for arm in ARMS:
            source_task_id = f"generation::{FRAMEE_MODE}::{chunk_id}::{arm}"
            generation_tasks.append({
                "task_id": source_task_id,
                "phase": "generation",
                "mode": FRAMEE_MODE,
                "chunk_id": chunk_id,
                "arm": arm,
                "model": GENERATOR_MODEL,
                "calls": 1,
                "retry": 0,
                "fallback": False,
            })
            for judge in JUDGE_MODELS_R2C:
                judge_tasks.append({
                    "task_id": f"judge::{FRAMEE_MODE}::{chunk_id}::{arm}::{judge}",
                    "source_task_id": source_task_id,
                    "phase": "judging",
                    "mode": FRAMEE_MODE,
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
        "schema": "ecm-tqag.round4.framee-call-plan.v1",
        "mode": FRAMEE_MODE,
        "frame": "E_hul_law_textbook_sections_figure_scoped",
        "frame_addendum_sha256": FRAMEE_ADDENDUM_SHA256,
        "frame_preregistration": FRAMEE_PREREGISTRATION,
        "frame_preregistration_sha256": FRAMEE_PREREGISTRATION_SHA256,
        "frame_manifest": FRAMEE_MANIFEST_NAME,
        "frame_manifest_sha256": FRAMEE_MANIFEST_SHA256,
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
    "FRAMEE_MODE",
    "FRAMEE_ADDENDUM_SHA256",
    "FRAMEE_PREREGISTRATION",
    "FRAMEE_PREREGISTRATION_SHA256",
    "FRAMEE_MANIFEST_NAME",
    "FRAMEE_MANIFEST_SHA256",
    "PRE_REGISTERED_FLOOR",
    "PRE_REGISTERED_TARGET",
    "SPAN_BANDS",
    "build_call_plan_framee",
    "load_composition_stratum",
    "load_framee",
    "load_span_band_stratum",
    "span_band",
]
