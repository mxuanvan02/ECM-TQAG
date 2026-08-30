#!/usr/bin/env python3
"""Freeze the Frame-F ablation pre-registration.

WHAT THIS ABLATION IS FOR
-------------------------
Frame F established that ECM-v2 raises A2, multimodal admission, against every
control including a length-matched disclosure arm. A2 is defined by three gates
that are checkable but are, in the end, PROXIES: G6 is structural, and G7/G8
compare against figure OCR with measured chance rates that are far from zero.

So A2 needs construct validity, and this ablation supplies it. The question is
not "does ECM-v2 raise A2" -- that is answered and sealed -- but:

    do the items A2 admits actually need the figure?

If A2-passing items are no more figure-dependent than A2-failing ones, then A2
is a gate that measures prompt compliance and nothing about multimodality, and
the Frame-F result must be restated as such. That outcome is declared reportable
here, before any call.

GRADING: THE DEFECT THIS RECORD FIXES FIRST
-------------------------------------------
The executed Frame-D ablation graded short answers by containment in either
direction. That rule is lenient on substrings but STRICT on insertions: an
answer differing from the gold by one inserted function word scores wrong. Three
of its ten figure-attributable items were of exactly that shape ("Thang du CUA
nguoi tieu dung" against "Thang du nguoi tieu dung"), and its headline
p=0.0386 did not survive its own sensitivity analysis.

Re-measured on those 115 sealed frame-D pairs under symmetric word-F1 at eight
thresholds, NO threshold reproduces significance:

    containment (frame-D primary) V*=0.426  p=0.0386
    F1 >= 0.50                    V*=0.287  p=0.7266
    F1 >= 0.60                    V*=0.383  p=0.1797
    F1 >= 0.65                    V*=0.426  p=0.2891
    F1 >= 0.70                    V*=0.461  p=1.0000
    F1 >= 0.75                    V*=0.504  p=1.0000
    F1 >= 0.80                    V*=0.530  p=0.6875
    F1 >= 0.90                    V*=0.574  p=0.1250

That is recorded here as a correction to a published number, not as a footnote.
Frame F therefore pre-registers SYMMETRIC word-F1 >= 0.70 as its primary grading
rule and reports containment beside it for comparability only.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
EXPERIMENT = SANDBOX / "experiment"
CENSUS = EXPERIMENT / "runs" / "round4_framef_census_20260830T140000Z"
MANIFEST = (EXPERIMENT / "dataset_framef"
            / "dataset_manifest_framef_20260830T122835Z.json")
FRAMEF_PREREG = (SANDBOX / "prospective" / "v3103_round2"
                 / "ROUND4_FRAMEF_PREREGISTRATION.json")
GATES_MODULE = EXPERIMENT / "round2" / "ecm_v2_gates.py"
OUT = (SANDBOX / "prospective" / "v3103_round2"
       / "ROUND4_FRAMEF_ABLATION_PREREGISTRATION.json")

ARMS = ("ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct",
        "structured_no_contract")
BRANCHES = ("TEXT", "TEXT_IMG")

# Primary grading rule, frozen here.
F1_THRESHOLD = 0.70
TRIVIAL_GOLD_MAX_CHARS = 2

_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹ]+")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fold(text: str) -> str:
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text or ""))).strip()
    return text.casefold()


def admitted_items() -> list[dict]:
    """Every v1-admitted generation of the frame-F census, with its A2 status."""
    gates = json.loads((CENSUS / "ECM_V2_GATE_RECORDS.json").read_text("utf-8"))
    out: list[dict] = []
    for path in sorted((CENSUS / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text("utf-8"))
        tid = rec.get("task_id", "")
        if not tid.startswith("generation::"):
            continue
        if rec.get("status") != "COMPLETE" or not rec.get("gates_passed"):
            continue
        obj = rec.get("object") or {}
        parts = tid.split("::")
        chunk = "::".join(parts[2:5])
        arm = parts[5]
        gate = gates.get(tid) or {}
        out.append({
            "item_id": f"{chunk}::{arm}",
            "chunk_id": chunk,
            "arm": arm,
            "question_type": obj["question_type"],
            "gold_answer": obj["answer"],
            "a2_passed": bool(gate.get("passed")),
            "a2_failed_gates": list(gate.get("failed_gates") or []),
        })
    return sorted(out, key=lambda r: r["item_id"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    items = admitted_items()

    excluded = [
        i["item_id"] for i in items
        if i["question_type"] != "multiple_choice"
        and len(fold(i["gold_answer"])) <= TRIVIAL_GOLD_MAX_CHARS
    ]
    scored = [i for i in items if i["item_id"] not in set(excluded)]

    by_a2 = Counter(i["a2_passed"] for i in scored)
    by_arm = Counter(i["arm"] for i in scored)
    a2_by_arm = {arm: {"pass": sum(1 for i in scored
                                   if i["arm"] == arm and i["a2_passed"]),
                       "fail": sum(1 for i in scored
                                   if i["arm"] == arm and not i["a2_passed"])}
                 for arm in ARMS}
    qtypes = Counter(i["question_type"] for i in scored)

    record = {
        "schema": "ecm-tqag.round4.framef-ablation-preregistration.v1",
        "status": ("FROZEN, prospective. No paid call is authorised by this "
                   "document; execution additionally requires an owner "
                   "authorization naming an explicit USD cap."),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),

        "question_this_answers": (
            "Frame F showed ECM-v2 raises A2 against every control. A2 is built "
            "from three gates that are PROXIES for multimodality: G6 is a "
            "structural relation between two returned fields, and G7/G8 are "
            "OCR-overlap tests with measured chance rates far above zero. This "
            "ablation asks whether the items A2 admits actually need the figure. "
            "If they do not, A2 measures prompt compliance rather than "
            "multimodality, and the Frame-F result must be restated as such."),

        "why_this_is_not_a_second_chance_at_the_frame_f_result": (
            "The Frame-F census is sealed and is NOT re-analysed by this record. "
            "A2 rates, the confirmatory family and its Holm flags stand as "
            "reported whatever this ablation shows. What is at stake here is the "
            "INTERPRETATION of A2, not its measured values."),

        "grading": {
            "primary_rule": (
                "symmetric word-F1 over accent- and case-folded content tokens; "
                "an answer is correct iff F1(returned, gold) >= %.2f" % F1_THRESHOLD),
            "f1_threshold": F1_THRESHOLD,
            "multiple_choice": ("correct iff the returned option_index equals the "
                                "recorded correct_option; no string heuristic, "
                                "chance level 0.25"),
            "secondary_rule_reported_beside_it": (
                "containment in either direction, the frame-D primary, reported "
                "for comparability only and carrying no claim here"),
            "why_the_rule_changed": {
                "defect": ("containment is lenient on substrings but STRICT on "
                           "insertions: one inserted function word scores an "
                           "otherwise identical answer wrong"),
                "found_in": "the executed frame-D ablation",
                "example": ("a returned answer differing from the gold by the "
                            "single word 'của' scored WRONG under containment and "
                            "scores F1=0.909 under the symmetric rule"),
                "consequence_for_the_published_frame_d_number": (
                    "the frame-D ablation reported V*=0.4261 and exact McNemar "
                    "p=0.0386 as evidence that figures were measurably necessary. "
                    "Re-graded under symmetric word-F1 at eight thresholds from "
                    "0.50 to 0.90, NO threshold reproduces significance. That "
                    "result is therefore a grading artefact and is corrected on "
                    "the record here rather than left standing."),
                "sensitivity_table_recomputed_on_the_sealed_frame_d_pairs": {
                    "n_pairs": 115,
                    "containment_frame_d_primary": {"v_star": 0.4261, "p": 0.0386},
                    "f1_0.50": {"v_star": 0.287, "p": 0.7266},
                    "f1_0.60": {"v_star": 0.383, "p": 0.1797},
                    "f1_0.65": {"v_star": 0.426, "p": 0.2891},
                    "f1_0.70": {"v_star": 0.461, "p": 1.0},
                    "f1_0.75": {"v_star": 0.504, "p": 1.0},
                    "f1_0.80": {"v_star": 0.530, "p": 0.6875},
                    "f1_0.90": {"v_star": 0.574, "p": 0.125},
                },
                "why_0.70_and_not_the_threshold_with_the_smallest_p": (
                    "0.70 is the knee where a single inserted or dropped function "
                    "word no longer flips a verdict, and it is chosen for that "
                    "structural reason. Choosing the threshold with the smallest "
                    "p-value would be the same defect in the opposite direction; "
                    "all eight thresholds are reported as a sensitivity curve "
                    "whatever the primary shows."),
            },
        },

        "design": {
            "branches": {
                "TEXT": ("the chunk's scoped evidence text plus the question. No "
                         "image, no figure description, no declared quotation, no "
                         "rationale."),
                "TEXT_IMG": ("the same text, the same question, plus the chunk's "
                             "own figure crops"),
            },
            "paired_within_item": True,
            "why_the_control_branch_is_required": (
                "without TEXT_IMG a wrong answer under TEXT is ambiguous between "
                "'the item needs the figure' and 'the item is unanswerable'"),
            "answerer_model": "qwen/qwen3-vl-8b-instruct",
            "why_the_generator_answers_its_own_items": (
                "it is the census generator, so the measurement is on the same "
                "model whose output was gated; a different answerer would confound "
                "answerer capability with figure dependence. Same choice as the "
                "sealed frame-C and frame-D ablations, retained for comparability."),
            "temperature": 0,
            "retry": 0,
            "fallback": False,
            "identical_between_branches": (
                "prompt text, response schema, decoding settings. Only the image "
                "content blocks differ."),
        },

        "items": {
            "population": ("every generation that passed the v1 gate in "
                           "round4_framef_census_20260830T140000Z, across all five "
                           "arms"),
            "n_v1_admitted": len(items),
            "n_scored": len(scored),
            "n_fixed_before_the_first_call": True,
            "by_arm": dict(by_arm),
            "by_question_type": dict(qtypes),
            "a2_split": {"pass": by_a2[True], "fail": by_a2[False]},
            "a2_split_by_arm": a2_by_arm,
            "calls": len(scored) * len(BRANCHES),
        },

        "declared_exclusion_before_execution": {
            "rule": ("a short-answer item whose gold answer folds to <= %d "
                     "characters is excluded" % TRIVIAL_GOLD_MAX_CHARS),
            "why": ("such a gold is contained in almost any returned string, so the "
                    "item auto-passes both branches under the containment rule and "
                    "would enter as evidence that the figure was unnecessary. That "
                    "is a generation defect read as a measurement."),
            "n_excluded": len(excluded),
            "item_ids": excluded,
        },

        "primary_endpoint": {
            "name": "A2 construct validity",
            "definition": (
                "V*(i) = 1 - R_TEXT(i) is 1 when item i is NOT answerable from "
                "text alone. The endpoint is the difference in V* between the "
                "items A2 admitted and the items A2 rejected."),
            "test": ("Fisher exact two-sided on the 2x2 table of A2 status against "
                     "V*, over all scored items pooled across arms"),
            "why_unpaired": (
                "A2 status is a property of an item, not a condition applied to a "
                "chunk, so A2-pass and A2-fail items are different items and the "
                "comparison is unpaired. The paired quantity is reported "
                "separately as the branch contrast below."),
            "alpha": 0.05,
            "n_a2_pass": by_a2[True],
            "n_a2_fail": by_a2[False],
            "direction_not_assumed": (
                "two-sided. A2-admitted items being LESS figure-dependent is a "
                "valid and reportable outcome, and would mean the gates select "
                "against the property they were built for."),
            "confound_declared_now": (
                "A2 status correlates with arm by construction: ECM-v2 supplies 24 "
                "of the %d A2-pass items. The pooled test therefore cannot "
                "separate 'A2 selects figure-dependent items' from 'the ECM-v2 arm "
                "writes figure-dependent items'. Both readings are reported, and "
                "the WITHIN-ARM version of the same table is reported for every "
                "arm with enough items, which is the form that breaks the "
                "confound." % by_a2[True]),
        },

        "secondary_endpoints": [
            {"name": "branch contrast within items",
             "definition": ("Gamma(i) = R_TEXT_IMG(i) - R_TEXT(i); exact two-sided "
                            "McNemar on the branch-discordant items"),
             "why": "the paired form: does supplying the figure change the outcome",
             "confirmatory": False},
            {"name": "V* and Gamma per arm",
             "why": "shows whether any effect is arm-specific",
             "confirmatory": False},
            {"name": "V* by A2 status WITHIN each arm",
             "why": ("the form that separates gate selection from arm effect; "
                     "reported for every arm, with its n, however small"),
             "confirmatory": False},
            {"name": "the eight-threshold F1 sensitivity curve",
             "why": ("so no reader has to trust the single frozen threshold; the "
                     "frame-D failure was invisible without exactly this"),
             "confirmatory": False},
            {"name": "PRIMARY_MCQ",
             "why": "graded by option index alone, with no string heuristic",
             "confirmatory": False},
        ],

        "power": {
            "n_scored": len(scored),
            "n_a2_pass": by_a2[True],
            "n_a2_fail": by_a2[False],
            "honest_limit": (
                "the within-arm tables are small: outside ECM-v2 no arm has more "
                "than 11 A2-pass items, so within-arm comparisons are descriptive "
                "and carry no significance claim. Only the pooled table is "
                "powered, and only the pooled table carries the confound above."),
        },

        "pre_committed_reporting": [
            "Reported whatever it shows.",
            ("If A2-admitted items are more figure-dependent than A2-rejected "
             "ones, A2 has construct validity as a multimodality gate and the "
             "Frame-F result reads as intended."),
            ("If they are not, A2 is reported as a compliance gate: it measures "
             "whether the generator followed the division-of-labour instruction, "
             "not whether the resulting item needs the figure. The Frame-F "
             "contrasts stand as measured and their INTERPRETATION narrows."),
            ("If the pooled table separates but the within-arm tables do not, the "
             "result is reported as confounded with arm and not as gate validity."),
            ("The frame-D ablation's published V*=0.4261 / p=0.0386 is corrected "
             "on the record as a grading artefact, whatever this ablation shows."),
            ("No outcome licenses changing the gates, the frame, the census, or "
             "regenerating items."),
        ],

        "what_would_make_this_record_invalid": [
            "any paid call before this file is frozen and an authorization exists",
            "editing the grading rule, the threshold, or the item set after the first call",
            "reporting the pooled table without the within-arm tables beside it",
            "presenting the frame-D correction as anything other than a correction",
        ],

        "inputs_bound_by_sha256": {
            "census_run": CENSUS.name,
            "frame_manifest": str(MANIFEST.relative_to(SANDBOX)),
            "frame_manifest_sha256": sha256_file(MANIFEST),
            "framef_preregistration": str(FRAMEF_PREREG.relative_to(SANDBOX)),
            "framef_preregistration_sha256": sha256_file(FRAMEF_PREREG),
            "gate_module": str(GATES_MODULE.relative_to(SANDBOX)),
            "gate_module_sha256": sha256_file(GATES_MODULE),
        },

        "budget_and_stop_rules": {
            "calls_if_executed": len(scored) * len(BRANCHES),
            "authorization_required": (
                "the runner requires --usd-cap and an authorization naming round "
                "round4_framef_ablation whose cap equals it"),
            "budget_cap_behaviour": (
                "remaining tasks are recorded NOT_ATTEMPTED:budget_cap rather than "
                "overspending"),
        },
    }

    print(f"census           {CENSUS.name}")
    print(f"v1 admitted      {len(items)}")
    print(f"scored           {len(scored)}  (excluded {len(excluded)} trivial golds)")
    print(f"A2 split         pass={by_a2[True]} fail={by_a2[False]}")
    print(f"by arm           {dict(by_arm)}")
    print(f"grading          symmetric word-F1 >= {F1_THRESHOLD}")
    print(f"calls if run     {len(scored) * len(BRANCHES)}")

    if not args.apply:
        print("\ndry run; pass --apply to freeze")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"\nwrote {OUT.relative_to(SANDBOX)}")
    print("sha256", sha256_file(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
