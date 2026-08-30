"""Round-4 Frame-F call plan (ECM-v2: division of labour between the two channels).

`round4_framee_plan` is bound to Frame E by sha256 and is NOT edited: the Frame-E
census that reported the scoped-span null loads through it. Frame F is a
pre-registered METHOD EXTENSION, frozen in
`prospective/v3103_round2/ROUND4_FRAMEF_PREREGISTRATION.json` before any call, so
it gets its own plan module.

WHAT CHANGES FROM FRAME E

  Nothing about the DATA. Same 60 chunks, same unit of analysis (one section),
  same figure-scoped evidence spans, same question-type assignment. The manifest
  adds exactly one field per package -- `document_structure.figure_role` -- which
  the ECM-v2 prompt conditions on and which no gate reads.

  What changes is the METHOD under test. Frames C-E measured the v1 evidence
  contract, whose gate gets provenance right and never binds the answer to the
  figure. Measured consequence: the returned quotation already contained the whole
  answer in 58% of admitted frame-D items and 79% of frame-E items, so the image
  was decorative and every multimodal endpoint was null by construction.

  Frame F measures ECM-v2, which adds three mechanical gates (G6/G7/G8 in
  `round2/ecm_v2_gates.py`) and a prompt that states them.

FIVE ARMS, NOT THREE

  ecm_v2              the ordered contract: read the figure first, answer from it,
                      quote for context only, seal, self-check
  ecm_v2_disclosed    length-matched disclosure control: same division of labour,
                      same three gates stated verbatim, same role guidance, but
                      the ORDER OF WORK is left free (35 characters apart)
  ecm_full            the v1 contract, unchanged
  direct              unchanged
  structured_no_contract  unchanged

  The paired design is preserved: every chunk is attempted by all five arms, so
  each chunk is its own control and only the prompt varies. The disclosure control
  reproduces the identification argument the reported census used to attribute its
  effect to ordering rather than to naming the conditions.

NOT AN INDEPENDENT REPLICATION. All 60 Frame-F units are Frame-D/E units. This is
a further look at the same corpus after two nulls were seen, and the
pre-registration records that before any number exists.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from ecm_tqag.v310_contracts import ARMS as BASELINE_ARMS, GENERATOR_MODEL

from .ecm_v2_prompt import ARM_NAME as ECM_V2_ARM, CONTROL_ARM_NAME as ECM_V2_CONTROL_ARM
from .round2c_routes import JUDGE_MODELS_R2C

FRAMEF_MODE = "r4f"

# Report order: the method under test, its disclosure control, then the three
# sealed baseline arms in their frozen order. `BASELINE_ARMS` is imported rather
# than re-typed so a change to the sealed tuple cannot silently desync.
ARMS = (ECM_V2_ARM, ECM_V2_CONTROL_ARM, *BASELINE_ARMS)

# The parent addendum, unchanged. Frame F does not relax V, does not move the
# threshold 3, and does not modify any v1 gate: A2 is a strict subset of v1
# admission.
FRAMEF_ADDENDUM_SHA256 = (
    "fea9078d43ee5ac32578233805425a83f1453f6fce374c9baf77687e4e9b3dfb"
)

# The pre-registration that authorises this frame's existence, written and
# frozen before the first call.
FRAMEF_PREREGISTRATION = "ROUND4_FRAMEF_PREREGISTRATION.json"
FRAMEF_PREREGISTRATION_SHA256 = (
    "20695651ad624d370a908101a1039f6baddf5723cf99f07b064f7c3ca2832635"
)

FRAMEF_MANIFEST_NAME = "dataset_manifest_framef_20260830T122835Z.json"
FRAMEF_MANIFEST_SHA256 = (
    "5e667745e7ba5b1989bdfd7cd2ba36bb84eca420062a0f693a2cd8f9d552d943"
)

# The gate module the primary endpoint is computed by, bound so a later edit to
# the gates cannot silently redefine the endpoint of an executed census.
ECM_V2_GATES_SHA256 = (
    "7f18b0c9ee4543e851985bb00748caf0b3b522098c4199b7a9bb901362db0828"
)

# Unchanged from the addendum. n=60 clears both.
PRE_REGISTERED_TARGET = 46
PRE_REGISTERED_FLOOR = 40

# Frozen figure roles. The ECM-v2 prompt conditions on these; no gate reads them.
FIGURE_ROLES = ("table", "diagram", "pictorial")


def load_framef(root: Path | str) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """Return (chunk_ids, question_type assignments, manifest) for Frame F.

    Fails closed unless the manifest on disk is byte-identical to the one the
    pre-registration was frozen against. Same contract as `load_framec`, plus a
    check that every package carries a figure role: the ECM-v2 prompt cannot be
    rendered without one, and a missing role must fail here rather than at the
    first paid call.
    """
    root = Path(root)
    manifest_path = root / "dataset_framef" / FRAMEF_MANIFEST_NAME
    raw = manifest_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FRAMEF_MANIFEST_SHA256:
        raise ValueError("BLOCKED_ROUND4F:MANIFEST_SHA256:" + digest)
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("schema") != "ecm-tqag.multimodal-inputs.v4-work24":
        raise ValueError("BLOCKED_ROUND4F:MANIFEST_SCHEMA")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("BLOCKED_ROUND4F:MANIFEST_PACKAGES")

    chunk_ids: list[str] = []
    assignments: dict[str, str] = {}
    for row in packages:
        chunk_id = row.get("chunk_id")
        qtype = row.get("question_type")
        if not isinstance(chunk_id, str) or qtype not in {"short_answer", "multiple_choice"}:
            raise ValueError("BLOCKED_ROUND4F:MANIFEST_ROW")
        if chunk_id in assignments:
            raise ValueError("BLOCKED_ROUND4F:DUPLICATE_CHUNK")
        evidence = row.get("evidence") or {}
        # Rule 4 must already have been applied upstream: an unsatisfiable gate
        # is a dataset defect, not a measurement.
        text = evidence.get("text") or ""
        if len("".join(str(text).split())) < 120:
            raise ValueError("BLOCKED_ROUND4F:RULE4_NOT_APPLIED:" + chunk_id)
        role = (evidence.get("document_structure") or {}).get("figure_role")
        if role not in FIGURE_ROLES:
            raise ValueError("BLOCKED_ROUND4F:FIGURE_ROLE:" + str(role))
        # G7/G8 read the gated OCR channel; without it those gates fail closed for
        # a dataset reason rather than a method reason.
        words = (evidence.get("figure_text") or {}).get("words")
        if not isinstance(words, list) or not words:
            raise ValueError("BLOCKED_ROUND4F:FIGURE_TEXT_MISSING:" + chunk_id)
        chunk_ids.append(chunk_id)
        assignments[chunk_id] = qtype
    return chunk_ids, assignments, manifest


# The two strata frozen in ROUND4_FRAMEF_PREREGISTRATION.json. Frames D and E
# froze DIFFERENT pairs; carrying either over would report a split this record
# never pre-registered, so they are replaced rather than inherited.
def load_figure_role_stratum(root: Path | str) -> dict[str, list[str]]:
    """Pre-registered stratum 1: figure role.

    Reads on whether the effect depends on figure kind. Frame D's executed
    ablation put the entire measured visual gain in vector-rendered regions --
    tables and drawings -- which contradicts the intuition that tables carry no
    information a question can need.

    Roles are read from the manifest, not recomputed, so the split cannot drift
    from the one the prompt conditioned on.
    """
    _, _, manifest = load_framef(root)
    strata: dict[str, list[str]] = {}
    for row in manifest["packages"]:
        role = ((row.get("evidence") or {}).get("document_structure") or {})["figure_role"]
        strata.setdefault(role, []).append(row["chunk_id"])
    return strata


def load_question_type_stratum(root: Path | str) -> dict[str, list[str]]:
    """Pre-registered stratum 2: question type.

    Multiple-choice items are graded by option index alone, with no string
    heuristic anywhere in the chain, so they are the cleanest subset. Frame F has
    only 10 of them, far below the floor, so this stratum is descriptive.
    """
    ids, assignments, _ = load_framef(root)
    strata: dict[str, list[str]] = {"multiple_choice": [], "short_answer": []}
    for chunk_id in ids:
        strata[assignments[chunk_id]].append(chunk_id)
    return strata


def build_call_plan_framef(chunk_ids: Sequence[str]) -> dict[str, Any]:
    """Frame-F plan: one generation call per chunk-arm, two judge calls per candidate."""
    ids = list(chunk_ids)
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("BLOCKED_ROUND4F:CALL_PLAN")
    generation_tasks: list[dict[str, Any]] = []
    judge_tasks: list[dict[str, Any]] = []
    for chunk_id in ids:
        for arm in ARMS:
            source_task_id = f"generation::{FRAMEF_MODE}::{chunk_id}::{arm}"
            generation_tasks.append({
                "task_id": source_task_id,
                "phase": "generation",
                "mode": FRAMEF_MODE,
                "chunk_id": chunk_id,
                "arm": arm,
                "model": GENERATOR_MODEL,
                "calls": 1,
                "retry": 0,
                "fallback": False,
            })
            for judge in JUDGE_MODELS_R2C:
                judge_tasks.append({
                    "task_id": f"judge::{FRAMEF_MODE}::{chunk_id}::{arm}::{judge}",
                    "source_task_id": source_task_id,
                    "phase": "judging",
                    "mode": FRAMEF_MODE,
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
        "schema": "ecm-tqag.round4.framef-call-plan.v1",
        "mode": FRAMEF_MODE,
        "frame": "F_hul_law_textbook_sections_role_conditioned",
        "frame_addendum_sha256": FRAMEF_ADDENDUM_SHA256,
        "frame_preregistration": FRAMEF_PREREGISTRATION,
        "frame_preregistration_sha256": FRAMEF_PREREGISTRATION_SHA256,
        "frame_manifest": FRAMEF_MANIFEST_NAME,
        "frame_manifest_sha256": FRAMEF_MANIFEST_SHA256,
        "ecm_v2_gates_sha256": ECM_V2_GATES_SHA256,
        "frame_size_n": n,
        "pre_registered_target": PRE_REGISTERED_TARGET,
        "pre_registered_floor": PRE_REGISTERED_FLOOR,
        "below_floor": n < PRE_REGISTERED_FLOOR,
        "arms": list(ARMS),
        "arms_new_in_frame_f": [ECM_V2_ARM, ECM_V2_CONTROL_ARM],
        "arms_carried_unchanged": list(BASELINE_ARMS),
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
    "ARMS",
    "ECM_V2_ARM",
    "ECM_V2_CONTROL_ARM",
    "ECM_V2_GATES_SHA256",
    "FIGURE_ROLES",
    "FRAMEF_ADDENDUM_SHA256",
    "FRAMEF_MANIFEST_NAME",
    "FRAMEF_MANIFEST_SHA256",
    "FRAMEF_MODE",
    "FRAMEF_PREREGISTRATION",
    "FRAMEF_PREREGISTRATION_SHA256",
    "PRE_REGISTERED_FLOOR",
    "PRE_REGISTERED_TARGET",
    "build_call_plan_framef",
    "load_framef",
    "load_figure_role_stratum",
    "load_question_type_stratum",
]
