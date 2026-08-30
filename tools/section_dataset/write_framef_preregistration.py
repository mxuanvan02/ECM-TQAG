#!/usr/bin/env python3
"""Freeze the Frame-F (ECM-v2) pre-registration before any paid call.

Frame F is the FINAL experiment of this line: the same 60 section chunks and the
same figure-scoped evidence spans as Frame E, plus

  * the figure ROLE exposed to the generator (table / diagram / pictorial), and
  * two new arms: the ECM-v2 division-of-labour contract and its length-matched
    disclosure control, and
  * a new PRIMARY endpoint that requires the answer to come from the figure
    rather than from the quotation.

Everything the record binds is computed from artefacts on disk, so the record is
reproducible rather than asserted. Nothing here makes a call.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
EXPERIMENT = SANDBOX / "experiment"
sys.path.insert(0, str(EXPERIMENT))

FRAME_F = (EXPERIMENT / "dataset_framef"
           / "dataset_manifest_framef_20260830T122835Z.json")
FRAME_E = (EXPERIMENT / "dataset_framee"
           / "dataset_manifest_framee_20260830T093119Z.json")
FRAME_D = (EXPERIMENT / "dataset_framed"
           / "dataset_manifest_framed_20260829T195643Z.json")
ADDENDUM = SANDBOX / "prospective/v3103_round2/ROUND4_NECESSITY_ADDENDUM.md"
PREREG_E = SANDBOX / "prospective/v3103_round2/ROUND4_FRAMEE_PREREGISTRATION.json"
GATES = EXPERIMENT / "round2" / "ecm_v2_gates.py"
PROMPT = EXPERIMENT / "round2" / "ecm_v2_prompt.py"
E_CENSUS = (EXPERIMENT / "runs" / "round4_framee_census_20260830T100000Z"
            / "ROUND4_REPORT.json")
D_CENSUS = (EXPERIMENT / "runs" / "round4_framed_census_20260829T200000Z"
            / "ROUND4_REPORT.json")
QUALITY = SANDBOX / "corpus/reports/MULTIMODAL_DATASET_QUALITY.json"

OUT = SANDBOX / "prospective/v3103_round2/ROUND4_FRAMEF_PREREGISTRATION.json"

PRE_REGISTERED_FLOOR = 40
PRE_REGISTERED_TARGET = 46

# The five arms of the paired census, in report order.
ARMS = ("ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct", "structured_no_contract")

# Confirmatory family: ECM-v2 against each of its four controls.
FAMILY = (
    ("ecm_v2", "ecm_full"),
    ("ecm_v2", "ecm_v2_disclosed"),
    ("ecm_v2", "direct"),
    ("ecm_v2", "structured_no_contract"),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def exact_sign_p(d: int) -> float:
    """Two-sided exact p when all d discordant pairs point one way."""
    return min(1.0, 2.0 * 0.5 ** d)


def min_discordance_for(alpha: float) -> int:
    d = 1
    while exact_sign_p(d) > alpha and d < 64:
        d += 1
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    man = json.loads(FRAME_F.read_text("utf-8"))
    packages = man["packages"]
    n = len(packages)

    roles = Counter(p["evidence"]["document_structure"]["figure_role"]
                    for p in packages)
    mixed = [p["chunk_id"] for p in packages
             if p["evidence"]["document_structure"]
                 .get("figure_role_provenance", {}).get("figure_role_mixed")]
    qtypes = Counter(p["question_type"] for p in packages)
    docs = Counter(p["doc_id"] for p in packages)
    spans = sorted(len(p["evidence"]["text"]) for p in packages)

    # prompt lengths, read from the module that will render them
    from round2.ecm_v2_prompt import prompt_lengths  # noqa: E402
    lengths = prompt_lengths()

    # gate thresholds and their measured chance baselines, read from the module
    from round2.ecm_v2_gates import (  # noqa: E402
        CHANCE_BASELINES, G7_MIN_ANSWER_FIGURE_WORDS,
        G8_MIN_DESCRIPTION_FIGURE_WORDS,
    )

    holm_thresholds = {
        f"rank_{i}": round(0.05 / (len(FAMILY) - i + 1), 6)
        for i in range(1, len(FAMILY) + 1)
    }
    smallest_alpha = min(holm_thresholds.values())

    generation_calls = n * len(ARMS)
    judge_calls = generation_calls * 2

    record = {
        "schema": "ecm-tqag.round4.framef-preregistration.v1",
        "status": ("FROZEN, prospective. No paid call is authorised by this "
                   "document; execution additionally requires an owner "
                   "authorization naming an explicit USD cap."),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),

        "what_this_is": (
            "Frame F tests ECM-v2: an evidence contract that requires the two "
            "channels to DIVIDE LABOUR -- the text quotation establishes what the "
            "question is about, the figure supplies what the question asks for -- "
            "together with three mechanical gates that check exactly that, and a "
            "prompt that states them. The corpus, the unit of analysis and the "
            "evidence spans are unchanged from Frame E."
        ),

        "the_defect_this_addresses": {
            "found_by": ("a clause-by-clause audit of the v1 contract against the "
                         "v1 gate"),
            "finding": ("five of the v1 contract's nine clauses have a mechanical "
                        "gate; the four without one are exactly the multimodal "
                        "clauses (the question must need the image, the answer must "
                        "be supported by both channels, ANSWER-FIRST, SEAL)"),
            "measured_consequence": {
                "admitted_items_whose_quotation_already_contains_the_whole_answer": {
                    "frame_d_full_section": "70 of 120 = 0.583",
                    "frame_e_figure_scoped": "101 of 128 = 0.789",
                },
                "why_that_matters": ("such an item is answerable by reading the "
                                     "quotation alone, so the image is decorative "
                                     "and its hash a formality"),
            },
            "why_the_earlier_nulls_follow": (
                "the instrument enforced provenance and reported multimodality. The "
                "provenance endpoint reproduced across frames C, D and E (no "
                "image-channel quotation under the contract); every multimodal "
                "endpoint returned null. Frame F changes what is enforced."
            ),
        },

        "frame": {
            "name": man["frame"],
            "manifest": str(FRAME_F.relative_to(SANDBOX)),
            "manifest_sha256": sha256_file(FRAME_F),
            "manifest_schema": man["schema"],
            "n": n,
            "n_is_fixed_before_the_first_call": True,
            "unit_of_analysis": "one section of a law textbook (unchanged)",
            "evidence_span": ("the section's own lines on its figure-bearing "
                              "pages, unchanged from Frame E"),
            "span_chars": {"median": spans[len(spans) // 2],
                           "min": spans[0], "max": spans[-1]},
            "question_types": dict(qtypes),
            "documents": len(docs),
            "source_concentration": {
                "top1_doc": docs.most_common(1)[0][0],
                "top1_chunks": docs.most_common(1)[0][1],
                "top1_share": round(docs.most_common(1)[0][1] / n, 3),
            },
            "figure_roles": dict(roles),
            "figure_role_rule": ("kind of the largest region by area on the "
                                 "unit's figure-bearing pages, from the section "
                                 "builder's own regions[].kind; nothing "
                                 "re-detected"),
            "mixed_role_chunks": {
                "n": len(mixed),
                "chunk_ids": mixed,
                "why_declared": ("five chunks carry more than one figure kind; "
                                 "the largest-area rule assigns one role and the "
                                 "choice is recorded per package in "
                                 "figure_role_provenance"),
            },
        },

        "this_is_not_independent_replication": {
            "why_stated_first": (
                "Frame F re-uses the same 60 units as Frame E, after Frame E's null "
                "was seen. This is a method-development experiment on the same "
                "corpus, not independent confirmation, and the record fixes that "
                "reading before any number exists."
            ),
            "units_shared_with_frame_e": n,
            "share_of_frame_f_also_in_frame_e": 1.0,
            "consequence": (
                "A positive result licenses the claim that ECM-v2 discriminates on "
                "THIS corpus at section granularity with figure-scoped spans. It "
                "does not license a general claim; that needs a fresh frame."
            ),
            "frames_not_re_analysed": ["C", "D", "E"],
        },

        "arms": {
            "list": list(ARMS),
            "new_in_frame_f": ["ecm_v2", "ecm_v2_disclosed"],
            "carried_unchanged": ["ecm_full", "direct", "structured_no_contract"],
            "paired": ("every chunk is attempted by all five arms, so each chunk "
                       "is its own control and only the prompt varies"),
            "prompt_lengths_chars": lengths,
            "length_match": {
                "ecm_v2_vs_its_disclosure_control": abs(
                    lengths["ecm_v2"]["total"] - lengths["ecm_v2_disclosed"]["total"]),
                "why": ("prompt length is a confound: a longer prompt could raise "
                        "admission by attention alone. The reported census handles "
                        "this with a disclosure control at matched length, and "
                        "Frame F reproduces that design."),
                "what_differs_between_them": (
                    "ONLY the ordering clauses. The control names the same "
                    "division of labour, states G6/G7/G8 verbatim, and carries the "
                    "same role guidance, but leaves the order of work free: no "
                    "figure-first step, no answer-first plan, no seal."),
            },
            "why_ecm_v2_is_a_new_arm_not_an_edited_prompt": (
                "official/PROMPT_SCHEMA_CONTRACT.json and the frozen ARMS tuple are "
                "audit-bound and are not modified; ECM-v2 ships a local prompt and "
                "a local request builder, as round2c_routes did for judge routes."
            ),
        },

        "primary_endpoint": {
            "name": "A2 -- multimodal admission",
            "definition": (
                "A2(c,a) = 1 iff the item passes ALL v1 gates AND the three ECM-v2 "
                "gates. No v1 condition is relaxed: A2 is a strict subset of v1 "
                "admission."
            ),
            "gates": {
                "g6_answer_not_in_quote": (
                    "the normalised answer is not a case-insensitive substring of "
                    "the normalised quotation"),
                "g7_answer_meets_figure": (
                    f">= {G7_MIN_ANSWER_FIGURE_WORDS} content words of the answer "
                    "occur in the recognised lettering of the chunk's figures"),
                "g8_description_meets_figure": (
                    f">= {G8_MIN_DESCRIPTION_FIGURE_WORDS} content words of "
                    "visual_evidence.description occur in that lettering"),
            },
            "gate_module": str(GATES.relative_to(SANDBOX)),
            "gate_module_sha256": sha256_file(GATES),
            "test": ("paired two-sided exact McNemar on discordant chunks, one "
                     "contrast per control arm, Holm step-down at family-wise "
                     "alpha 0.05"),
            "family": [f"{a}_vs_{b}" for a, b in FAMILY],
            "holm_thresholds": holm_thresholds,
            "decision_rule": {
                "smallest_family_alpha": smallest_alpha,
                "min_unidirectional_discordance_to_reject_first": (
                    min_discordance_for(smallest_alpha)),
                "note": ("with fewer unidirectional discordant chunks than that, "
                         "the first contrast cannot be declared significant "
                         "whatever the split looks like"),
            },
            "direction_not_assumed": ("two-sided; a control beating ECM-v2 is a "
                                      "valid, reportable outcome"),
        },

        "gate_validity_stated_before_execution": {
            "g6_is_load_bearing": ("a structural relation between two returned "
                                   "fields; no external reference, no chance "
                                   "baseline"),
            "g7_g8_are_weak_and_measured": CHANCE_BASELINES,
            "consequence_for_interpretation": (
                "G7 and G8 are corroborating, not decisive. A result that depends "
                "on them rather than on G6 must be reported as such, and the "
                "per-gate pass rates are reported for every arm so a reader can "
                "see which gate carried the contrast."
            ),
            "rejected_stricter_variant": CHANCE_BASELINES[
                "rejected_variant_answer_meets_surplus_only"],
        },

        "secondary_endpoints": [
            {"name": "v1 admission A",
             "why": ("ECM-v2 must not buy multimodality by breaking provenance. "
                     "A is reported per arm with Clopper-Pearson intervals and "
                     "paired contrasts, exactly as in frames C-E."),
             "confirmatory": False},
            {"name": "per-gate pass rates G6, G7, G8 per arm",
             "why": "shows which gate carries any contrast",
             "confirmatory": False},
            {"name": "quotation provenance taxonomy",
             "why": ("the one endpoint that reproduced across frames C, D and E: "
                     "share of non-reproducing quotations traced to the image "
                     "channel, per arm, counted strictly (a distinctive figure "
                     "word absent from the prose)"),
             "confirmatory": False},
            {"name": "judged endpoints V and M with all three pooling rules",
             "why": "as the parent addendum fixes them; unchanged",
             "confirmatory": False},
            {"name": "the four other judged vectors, unaveraged, per arm",
             "why": "addendum section 2.1 item 4",
             "confirmatory": False},
            {"name": "judge-record completeness per arm",
             "why": "addendum section 2.1 item 5",
             "confirmatory": False},
        ],

        "pre_registered_strata": {
            "why_fixed_now": ("membership is fixed before execution so no split "
                              "can be chosen after seeing the numbers"),
            "figure_role": {
                "definition": "the role assigned by the largest-area rule",
                "sizes": dict(roles),
                "reads_on": ("whether the effect depends on figure kind. On "
                             "frame D the measured visual gain sat entirely in "
                             "vector-rendered regions, i.e. tables and drawings, "
                             "which contradicts the intuition that tables are "
                             "uninformative."),
            },
            "question_type": {
                "definition": "the frozen question-type assignment",
                "sizes": dict(qtypes),
                "reads_on": ("multiple-choice items are graded without any string "
                             "heuristic, so they are the cleanest subset"),
            },
            "stratum_tests_are_descriptive": (
                "no stratum reaches the floor of 40; stratum contrasts are "
                "reported with discordance counts and carry no significance claim"
            ),
        },

        "planned_ablation": {
            "what": ("a text-only ablation on the Frame-F admitted items, "
                     "identical in design to the executed Frame-D ablation"),
            "grading_defect_to_fix_first": {
                "found_in": "the executed Frame-D ablation",
                "defect": ("the frozen containment rule is lenient on substrings "
                           "but STRICT on insertions, so an answer differing by one "
                           "inserted function word scores wrong. Three of the ten "
                           "figure-attributable items were of that shape."),
                "sensitivity_already_measured": {
                    "containment_preregistered": {"v_star": 0.4261, "mcnemar_p": 0.0386},
                    "word_f1_ge_0.70": {"v_star": 0.3217, "mcnemar_p": 0.3877},
                    "word_f1_ge_0.60": {"v_star": 0.2696, "mcnemar_p": 1.0},
                },
                "consequence": ("the Frame-D ablation result does not survive its "
                                "own sensitivity analysis and is reported that way; "
                                "any Frame-F ablation must pre-register a grading "
                                "rule that is symmetric to insertion"),
            },
            "status": ("declared here so the comparison cannot be assembled after "
                       "the fact; the ablation needs its own authorization"),
        },

        "power": {
            "n": n,
            "floor": PRE_REGISTERED_FLOOR,
            "target": PRE_REGISTERED_TARGET,
            "reaches_floor": n >= PRE_REGISTERED_FLOOR,
            "reaches_target": n >= PRE_REGISTERED_TARGET,
            "consequence": (
                f"n={n} clears the addendum floor of {PRE_REGISTERED_FLOOR} and its "
                f"target of {PRE_REGISTERED_TARGET}, so the floor clause does not "
                "apply and Holm rejection flags are live."),
            "honest_limit": (
                "the family has four contrasts, so the Holm-first threshold is "
                f"{smallest_alpha} and needs "
                f"{min_discordance_for(smallest_alpha)} unidirectional discordant "
                "chunks. A null on the later contrasts is not evidence of no "
                "effect."),
        },

        "what_does_not_change": {
            "generator": "qwen/qwen3-vl-8b-instruct",
            "judges": ["claude-opus-5", "gpt-5.6-sol"],
            "judgement_schema": "the frozen seven-field schema",
            "v1_gates": "the round-2 repaired gate, byte-identical code",
            "rule_4": "frozen thresholds, already applied to the scoped spans",
            "discipline": ("zero retry, no fallback, run lock, per-task O_EXCL "
                           "claim, ITT accounting"),
            "evidence_bundle": ("identical bytes and identical evidence digest "
                                "across all five arms, verified offline"),
            "figure_text_channel": ("evidence.figure_text is NOT in any prompt "
                                    "payload and is not quotable as prose; it is "
                                    "read only by G7/G8 as a reference"),
        },

        "budget_and_stop_rules": {
            "calls_if_executed": generation_calls + judge_calls,
            "generation_calls": generation_calls,
            "judge_calls": judge_calls,
            "authorization_required": (
                "the runner requires --usd-cap and an authorization naming round "
                "round4_framef whose cap equals it; without both it makes no call"),
            "budget_cap_behaviour": ("remaining tasks are recorded "
                                     "NOT_ATTEMPTED:budget_cap rather than "
                                     "overspending"),
            "spend_so_far_on_this_line_usd": 0.43976,
        },

        "pre_committed_reporting": [
            "Reported whatever it shows.",
            ("If ECM-v2 separates from ecm_full on A2, the claim becomes: making "
             "the division of labour a checked condition rather than a requested "
             "property is what produces multimodal items, on this corpus."),
            ("If ECM-v2 separates from the baselines but NOT from its "
             "length-matched disclosure control, the honest claim is that stating "
             "the conditions suffices and fixing the construction order adds "
             "nothing measurable. That is weaker and it is what gets written."),
            ("If ECM-v2 does not separate at all, the reported contribution of the "
             "method narrows to the provenance result that reproduced across "
             "frames C, D and E, and the paper says the multimodal claim was not "
             "established on this corpus."),
            ("If A2 is near zero in every arm, that is reported as the corpus "
             "being unable to support figure-answered items at this granularity, "
             "with the per-gate rates showing which condition was binding."),
            ("Any result that rests on G7/G8 rather than G6 is reported with the "
             "chance baselines beside it."),
            "No outcome licenses relaxing a v1 gate, changing rule 4, or regenerating items.",
        ],

        "what_would_make_this_record_invalid": [
            "any paid call before this file is frozen and an authorization exists",
            "editing n, the arms, the gates, the thresholds or either stratum after the first call",
            "modifying the v1 gate, the judges, rule 4 or the evidence bundle",
            "reporting Frame F without the Frame-D and Frame-E results beside it",
            "presenting Frame F as independent replication",
        ],

        "inputs_bound_by_sha256": {
            "frame_f_manifest": str(FRAME_F.relative_to(SANDBOX)),
            "frame_f_manifest_sha256": sha256_file(FRAME_F),
            "frame_e_manifest_sha256": sha256_file(FRAME_E),
            "frame_d_manifest_sha256": sha256_file(FRAME_D),
            "frame_e_preregistration_sha256": sha256_file(PREREG_E),
            "parent_addendum_sha256": sha256_file(ADDENDUM),
            "ecm_v2_gates_sha256": sha256_file(GATES),
            "ecm_v2_prompt_sha256": sha256_file(PROMPT),
            "dataset_quality_report_sha256": sha256_file(QUALITY),
            "frame_e_census_report_sha256": sha256_file(E_CENSUS),
            "frame_d_census_report_sha256": sha256_file(D_CENSUS),
        },
    }

    print(f"frame            {record['frame']['name']}")
    print(f"n                {n}  floor {PRE_REGISTERED_FLOOR} target {PRE_REGISTERED_TARGET}")
    print(f"arms             {len(ARMS)}  {list(ARMS)}")
    print(f"figure roles     {dict(roles)}  mixed {len(mixed)}")
    print(f"span chars       median {spans[len(spans)//2]} max {spans[-1]}")
    print(f"prompt lengths   " + "  ".join(
        f"{a}={v['total']}" for a, v in lengths.items()))
    print(f"length match     {record['arms']['length_match']['ecm_v2_vs_its_disclosure_control']} chars")
    print(f"family           {len(FAMILY)} contrasts, holm-first alpha {smallest_alpha}")
    print(f"  needs          {min_discordance_for(smallest_alpha)} unidirectional discordant chunks")
    print(f"calls if run     {generation_calls + judge_calls}"
          f" ({generation_calls} generation + {judge_calls} judge)")

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
