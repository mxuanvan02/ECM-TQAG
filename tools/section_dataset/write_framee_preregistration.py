#!/usr/bin/env python3
"""Freeze the Frame-E pre-registration: the figure-scoped evidence span.

WHY THIS SCRIPT EXISTS AT ALL
    A first version of this record was emitted inline, which made it
    unreproducible, and it carried a wrong number: it reported
    `chunks_shared_with_frame_d = 0`. That was a string-comparison bug -- the
    ids differ only by their `frameD::` / `frameE::` prefix, so a raw set
    intersection is empty by construction while the underlying material is the
    same. The true overlap is computed here on the UNIT part of the id.

    The direction of that error matters, which is why it is recorded rather
    than silently fixed: zero overlap would have implied Frame E is an
    independent sample, i.e. the most flattering possible reading of a second
    look at data whose first look was null. It is not one.

WHAT FRAME E CHANGES
    The unit of analysis stays the section (owner decision, unchanged). The
    span the verbatim-quote gate reads narrows from the whole section to the
    section's own text on the pages carrying its figure regions.

WHAT IT DOES NOT CHANGE
    Generator, the three arm prompts, the gate code, the judge families, the
    judgement schema, the endpoints, rule 4, and the execution discipline.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
EXPERIMENT = SANDBOX / "experiment"
PROSPECTIVE = SANDBOX / "prospective" / "v3103_round2"

FRAME_E = EXPERIMENT / "dataset_framee" / "dataset_manifest_framee_20260830T093119Z.json"
FRAME_D = EXPERIMENT / "dataset_framed" / "dataset_manifest_framed_20260829T195643Z.json"
FRAME_D_PREREG = PROSPECTIVE / "ROUND4_FRAMED_PREREGISTRATION.json"
ADDENDUM = PROSPECTIVE / "ROUND4_NECESSITY_ADDENDUM.md"
SCOPED = SANDBOX / "corpus" / "reports" / "SCOPED_EVIDENCE_SPANS.json"
QUALITY = SANDBOX / "corpus" / "reports" / "MULTIMODAL_DATASET_QUALITY.json"
D_CENSUS = (EXPERIMENT / "runs" / "round4_framed_census_20260829T200000Z"
            / "ROUND4_REPORT.json")
D_ABLATION = (EXPERIMENT / "runs" / "ablation_framed_20260830T060000Z"
              / "ABLATION_REPORT.json")

OUT = PROSPECTIVE / "ROUND4_FRAMEE_PREREGISTRATION.json"

ARMS = ("ecm_full", "direct", "structured_no_contract")
JUDGES = ("claude-opus-5", "gpt-5.6-sol")
FLOOR = 40
TARGET = 46


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def unit_of(chunk_id: str) -> str:
    """The frame-independent part of a chunk id.

    Chunk ids are `<frame>::<doc>::<section>`. Comparing raw ids across frames
    is always empty because the prefix differs; the unit part is what identifies
    the underlying material.
    """
    parts = chunk_id.split("::", 1)
    return parts[1] if len(parts) == 2 else chunk_id


def band_of(chars: int) -> str:
    if chars < 1000:
        return "under_1000"
    if chars < 2000:
        return "from_1000_to_2000"
    if chars < 4000:
        return "from_2000_to_4000"
    return "over_4000"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    e_man = json.loads(FRAME_E.read_text("utf-8"))
    d_man = json.loads(FRAME_D.read_text("utf-8"))
    scoped = json.loads(SCOPED.read_text("utf-8"))
    quality = json.loads(QUALITY.read_text("utf-8"))
    d_report = json.loads(D_CENSUS.read_text("utf-8"))
    d_abl = json.loads(D_ABLATION.read_text("utf-8"))

    e_pkgs = e_man["packages"]
    e_ids = [p["chunk_id"] for p in e_pkgs]
    d_ids = [p["chunk_id"] for p in d_man["packages"]]

    # --- overlap, computed on the unit part (the defect this script fixes) ---
    e_units = {unit_of(i) for i in e_ids}
    d_units = {unit_of(i) for i in d_ids}
    shared = sorted(e_units & d_units)
    e_only = sorted(e_units - d_units)

    # --- spans and strata, derived from the manifest, never hardcoded ---
    lengths = {p["chunk_id"]: len(p["evidence"]["text"]) for p in e_pkgs}
    ordered = sorted(lengths.values())
    band_sizes: dict[str, int] = {}
    for chars in lengths.values():
        band_sizes[band_of(chars)] = band_sizes.get(band_of(chars), 0) + 1

    comp_sizes = {"has_embedded_raster": 0, "rendered_vector_only": 0}
    for p in e_pkgs:
        raster = any(i.get("source") == "embedded_raster"
                     for i in p["evidence"]["images"])
        comp_sizes["has_embedded_raster" if raster
                   else "rendered_vector_only"] += 1

    qtypes: dict[str, int] = {}
    for p in e_pkgs:
        qtypes[p["question_type"]] = qtypes.get(p["question_type"], 0) + 1

    docs: dict[str, int] = {}
    for p in e_pkgs:
        docs[p["doc_id"]] = docs.get(p["doc_id"], 0) + 1
    top1_doc, top1_n = max(docs.items(), key=lambda kv: kv[1])

    n = len(e_pkgs)
    gen_calls = n * len(ARMS)
    judge_calls = gen_calls * len(JUDGES)

    d_full = quality["measured"]["section_chars"]
    d_contrasts = d_report["contrasts"]
    d_primary = d_abl["PRIMARY_ALL"]

    record = {
        "schema": "ecm-tqag.round4.framee-preregistration.v1",
        "status": ("FROZEN, prospective. No paid call is authorised by this "
                   "document; execution additionally requires an owner "
                   "authorization naming an explicit USD cap."),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "script": "corpus/scripts/write_framee_preregistration.py",

        "what_this_is": (
            "Frame E is a pre-registered METHOD ADAPTATION of the evidence "
            "contract, not a new sample. The unit of analysis stays the section, "
            "as the owner decided. What changes is the SPAN the verbatim-quote "
            "gate reads: the section's own text on the pages that carry its "
            "figure regions, instead of the whole section."),

        "this_is_not_independent_replication": {
            "why_stated_first": (
                "Frame E re-uses the same corpus and mostly the same chunks as "
                "Frame D, after Frame D's null was seen. A second look at the "
                "same data cannot be reported as independent confirmation, and "
                "this record fixes that reading before any number exists."),
            "frame_d_chunks": len(d_ids),
            "frame_e_chunks": n,
            "units_shared_with_frame_d": len(shared),
            "units_in_frame_e_not_in_frame_d": len(e_only),
            "share_of_frame_e_also_in_frame_d": round(len(shared) / n, 4),
            "correction_of_an_earlier_draft_of_this_record": {
                "was": "chunks_shared_with_frame_d = 0",
                "now": f"units_shared_with_frame_d = {len(shared)}",
                "why_it_was_wrong": (
                    "Chunk ids differ only by their frameD:: / frameE:: prefix, "
                    "so a raw set intersection is empty by construction. The "
                    "overlap is computed on the unit part of the id."),
                "why_the_direction_matters": (
                    "Zero overlap would have implied Frame E is an independent "
                    "sample, which is the most flattering available reading of a "
                    "second look at data whose first look was null. It is not "
                    "one, and the corrected number says so."),
            },
            "consequence": (
                "Frame D's reported census stands unchanged and is NOT "
                "re-analysed. Frame E is reported as a method-adaptation "
                "experiment whose evidence value is conditional on the same "
                "corpus; a positive result here needs a fresh frame before it "
                "can be stated as a general claim."),
        },

        "the_measured_defect_this_addresses": {
            "criterion": ("C5 of corpus/reports/MULTIMODAL_DATASET_QUALITY.json "
                          f"(verdict: {quality['overall']})"),
            "full_section_span_chars": {
                "median": d_full["median"],
                "max": d_full["max"],
                "over_20k_chunks": d_full["over_20k"],
            },
            "why_that_breaks_the_gate": (
                "The gate admits an item when its declared quotation reproduces "
                "inside the conditioning text. Over a span of that length a "
                "valid quotation is nearly free to find, so the gate stops "
                "separating prompts."),
            "evidence_from_the_frame_d_census": {
                "admission_per_arm": d_report["generation_pass_per_arm"],
                "ecm_vs_direct_paired_exact_p": d_contrasts[
                    "ecm_full_vs_direct"]["p_two_sided_exact"],
                "ecm_vs_structured_paired_exact_p": d_contrasts[
                    "ecm_full_vs_structured_no_contract"]["p_two_sided_exact"],
                "note": ("the census V-endpoint contrasts are quoted as the "
                         "motivation for this adaptation, not as a result"),
            },
            "second_defect_addressed": {
                "criterion": (f"C4 (warn): only {d_primary['figure_attributable_G']['rate']:.1%} "
                              "of admitted items were figure-attributable"),
                "why_scoping_bears_on_it": (
                    "An admitted quotation from anywhere in a section of "
                    f"{d_full['max']} characters need not relate to the figure "
                    "at all. Restricting the span to the figure's own pages "
                    "makes textual and visual evidence co-located, which is the "
                    "multimodal claim the method is supposed to make."),
            },
        },

        "frame": {
            "name": e_man["frame"],
            "manifest": str(FRAME_E.relative_to(SANDBOX)),
            "manifest_sha256": sha256_file(FRAME_E),
            "manifest_schema": e_man["schema"],
            "n": n,
            "n_is_fixed_before_the_first_call": True,
            "unit_of_analysis": "one section of a law textbook (unchanged from Frame D)",
            "evidence_span": (
                "the section's own lines on its figure-bearing pages, clipped to "
                "the section, with the same furniture and watermark templates "
                "removed as the full-section build"),
            "span_chars": {"median": ordered[len(ordered) // 2],
                           "min": ordered[0], "max": ordered[-1]},
            "question_types": qtypes,
            "documents": len(docs),
            "source_concentration": {
                "top1_doc": top1_doc, "top1_chunks": top1_n,
                "top1_share": round(top1_n / n, 4),
            },
            "why_n_is_not_the_frame_d_n": (
                "Frozen rule 4 (prose < 120 chars, or >= 3 enumerated items with "
                "prose < 400) is re-applied to the SCOPED span. The Frame-D "
                "chunks whose figure pages carry almost no prose fail it and are "
                "excluded. Rule 4 was not modified; it was applied to the span "
                "the gate actually reads, which is the only consistent choice "
                "once the span changes."),
            "dropped_units": [unit_of(r["chunk_id"])
                              for r in scoped["dropped"]],
        },

        "what_does_not_change": {
            "generator": "qwen/qwen3-vl-8b-instruct",
            "arms": list(ARMS),
            "arm_prompts": "the three round-2e prompts with the minimal D3 clarification",
            "gate": "the round-2 repaired gate, byte-identical code",
            "judges": list(JUDGES),
            "judgement_schema": "the frozen seven-field schema",
            "endpoints": "V, M, and the three pooling rules, as the parent addendum fixes them",
            "discipline": "zero retry, no fallback, run lock, per-task O_EXCL claim, ITT accounting",
            "unit_of_analysis": "the section",
        },

        "primary_hypothesis": {
            "H": ("Scoping the evidence span to the figure's own pages restores "
                  "the gate's ability to separate the evidence contract from its "
                  "controls."),
            "prediction_if_H_holds": (
                "the paired exact contrast ECM vs direct on admission reaches a "
                "one-directional discordance large enough to reject under Holm "
                "at family alpha 0.05"),
            "prediction_if_H_fails": (
                "admission stays statistically indistinguishable across arms, "
                "which would mean the effect does not survive at section "
                "granularity under any span this corpus supports, and the "
                "method's admission claim must be restated as specific to short "
                "page-level spans"),
            "direction_not_assumed": (
                "the test is two-sided; a control beating the contract is a "
                "valid, reportable outcome"),
            "decision_rule": (
                "The smallest discordant count reaching alpha=0.025 on a "
                "two-sided exact test is 7 unidirectional pairs (p=0.0156). "
                "Fewer than 7 cannot declare the first contrast significant "
                "under Holm, whatever the split looks like."),
        },

        "secondary_hypothesis_multimodal": {
            "H2": ("Co-locating the quotation with the figure raises the share "
                   "of admitted items whose figure is measurably necessary."),
            "measured_how": (
                "a text-only ablation on the Frame-E admitted items, identical "
                "in design to the executed Frame-D ablation, so the two are "
                "directly comparable"),
            "frame_d_baseline_to_beat": {
                "measured_visual_necessity_V_star":
                    d_primary["measured_visual_necessity_V_star"]["rate"],
                "figure_attributable_G": d_primary["figure_attributable_G"]["rate"],
                "n": d_primary["n"],
            },
            "status": ("declared here so the comparison cannot be assembled "
                       "after the fact; the ablation needs its own authorization"),
        },

        "pre_registered_strata": {
            "why_fixed_now": ("Membership is fixed before execution so the split "
                              "cannot be chosen to produce a result."),
            "scoped_span_band": {
                "definition": "raw character length of the scoped evidence span",
                "sizes": band_sizes,
                "reads_on": ("the length mechanism directly: if span length is "
                             "what broke the gate, admission should be flatter "
                             "across these bands than across Frame D's"),
            },
            "chunk_composition": {
                "definition": ("chunk carries at least one embedded raster, "
                               "versus rendered vector regions only"),
                "sizes": comp_sizes,
                "reads_on": ("the owner's table hypothesis, already contradicted "
                             "on Frame D where vector-only chunks carried the "
                             "entire measured visual gain"),
            },
            "stratum_tests_are_descriptive": (
                "no stratum is powered for a confirmatory claim; reported with "
                "discordance counts and no significance claim"),
        },

        "power": {
            "n": n, "floor": FLOOR, "target": TARGET,
            "reaches_floor": n >= FLOOR,
            "reaches_target": n >= TARGET,
            "consequence": (
                f"n={n} clears the addendum floor of {FLOOR} and its target of "
                f"{TARGET}, so section 4's floor clause does not apply and Holm "
                "rejection flags are live."),
            "honest_limit": (
                "The addendum's power table puts ECM-vs-structured near 0.43 at "
                "n=46 and needing about n=90. At this n that contrast stays "
                "underpowered and a null on it is not evidence of no effect."),
        },

        "inputs_bound_by_sha256": {
            "frame_e_manifest_sha256": sha256_file(FRAME_E),
            "frame_d_manifest_sha256": sha256_file(FRAME_D),
            "frame_d_preregistration_sha256": sha256_file(FRAME_D_PREREG),
            "parent_addendum_sha256": sha256_file(ADDENDUM),
            "scoped_spans_report_sha256": sha256_file(SCOPED),
            "dataset_quality_report_sha256": sha256_file(QUALITY),
            "frame_d_census_report": str(D_CENSUS.relative_to(SANDBOX)),
            "frame_d_ablation_report": str(D_ABLATION.relative_to(SANDBOX)),
        },

        "budget_and_stop_rules": {
            "calls_if_executed": gen_calls + judge_calls,
            "generation_calls": gen_calls,
            "judge_calls": judge_calls,
            "authorization_required": (
                "the runner requires --usd-cap and an authorization file naming "
                "round4_framee whose cap equals it; without both it makes no call"),
            "budget_cap_behaviour": (
                "remaining tasks are recorded NOT_ATTEMPTED:budget_cap rather "
                "than overspending"),
        },

        "pre_committed_reporting": [
            "Reported whatever it shows.",
            ("If the contrast rejects, the reported claim becomes: the evidence "
             "contract discriminates at section granularity ONCE the span is "
             "scoped to the figure, and the unscoped null is a property of span "
             "length. The dependence on the adaptation is reported, not hidden, "
             "and so is the fact that Frame E re-uses Frame D's material."),
            ("If it does not reject, the reported claim becomes: the admission "
             "effect does not survive at section granularity, and the method's "
             "contribution narrows to the failure-mode result (no image-channel "
             "quotation under the contract)."),
            "The Frame-D census and ablation are not re-run, re-analysed, or re-labelled.",
            "No outcome licenses relaxing rule 4, changing the gate code, or regenerating items.",
        ],

        "what_would_make_this_record_invalid": [
            "any paid call before this file is frozen and an authorization exists",
            "editing n, the span definition, or either stratum after the first call",
            "modifying the gate, the arm prompts, the judges, or rule 4",
            "reporting the scoped result without the Frame-D unscoped result beside it",
            ("reporting Frame E as an independent replication of Frame D, which "
             f"it is not: {len(shared)} of its {n} units are Frame-D units"),
        ],
    }

    print(f"frame            {record['frame']['name']}")
    print(f"n                {n}  floor {FLOOR}  target {TARGET}")
    print(f"span median      {record['frame']['span_chars']['median']} "
          f"max {record['frame']['span_chars']['max']}")
    print(f"units shared w/ frame D  {len(shared)} of {n}  "
          f"({record['this_is_not_independent_replication']['share_of_frame_e_also_in_frame_d']:.0%})")
    print(f"units new vs frame D     {len(e_only)}")
    print(f"strata band      {band_sizes}")
    print(f"strata comp      {comp_sizes}")
    print(f"calls if run     {gen_calls + judge_calls}")

    if not args.apply:
        print("\ndry run; pass --apply to freeze")
        return 0

    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"\nwrote {OUT.relative_to(SANDBOX)}")
    print("sha256", sha256_file(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
