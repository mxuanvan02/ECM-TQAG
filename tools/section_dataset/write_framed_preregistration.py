#!/usr/bin/env python3
"""Write the Frame-D pre-registration record. Must run BEFORE any paid call.

ROUND4_NECESSITY_ADDENDUM.md §4 fixes n before the first call and forbids frame
extension after results are seen; §7 forbids reusing a seen frame. Frame D is a
new frame drawn from the law-textbook section dataset, and it adopts the LITERAL
reading of ROUND3_FRAMEB_ADDENDUM rule 3, which the frame-C records declined.
Both facts are deviations and are declared here, before execution, with the
frame bound by sha256.

What this record fixes, and cannot be changed afterwards:
  * the frame manifest, by sha256
  * n = 67
  * the rule-3 reading, stated verbatim, with the count under the frozen
    reading (28) also recorded so the choice is visible rather than implied
  * the endpoint, the three pooling rules, and the Holm family - all inherited
    unchanged from the addendum, which this record does not relax
  * the stratum split (chunks whose figure carries text the prose does not),
    declared now so it cannot be chosen after seeing results

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
FRAMED_DIR = SANDBOX / "experiment/dataset_framed"
OUT = SANDBOX / "prospective/v3103_round2/ROUND4_FRAMED_PREREGISTRATION.json"

ADDENDUM = SANDBOX / "prospective/v3103_round2/ROUND4_NECESSITY_ADDENDUM.md"
FRAMEB_ADDENDUM = SANDBOX / "prospective/v3103_round2/ROUND3_FRAMEB_ADDENDUM.md"
DETERMINATION = SANDBOX / "corpus/reports/SECTION_FRAME_DETERMINATION.json"
RIGHTS = SANDBOX / "corpus/reports/SECTION_DATASET_RIGHTS_RECONCILIATION.json"
CALIBRATION = SANDBOX / "corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json"
OCR_PROBE = SANDBOX / "corpus/reports/OCR_FIDELITY_PROBE.json"
SCOPE = SANDBOX / "corpus/reports/DATASET_SCOPE_LAW_TEXTBOOKS.json"
SEALED_C = SANDBOX / "experiment/dataset_framec/dataset_manifest_rule4_20260816T105100Z.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    manifests = sorted(FRAMED_DIR.glob("dataset_manifest_framed_*.json"))
    if not manifests:
        raise SystemExit("no frame-D manifest; run build_framed_manifest.py --apply")
    manifest_path = manifests[-1]
    manifest = json.loads(manifest_path.read_text("utf-8"))
    packages = manifest["packages"]
    n = len(packages)

    qtypes = Counter(p["question_type"] for p in packages)
    docs = Counter(p["doc_id"] for p in packages)
    stratum = Counter(
        "image_only_content"
        if (p["evidence"].get("figure_text") or {}).get("surplus_words")
        else "no_image_only_content"
        for p in packages
    )

    record = {
        "schema": "ecm-tqag.round4.framed-preregistration.v1",
        "status": "FROZEN, prospective. No paid call is authorised by this document.",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "what_this_is": (
            "Pre-registration for a round-4 census on Frame D, a new frame drawn "
            "from the section-level law-textbook dataset. Written before any call, "
            "so that the frame, its size, and the rule reading that produced it "
            "cannot be chosen after seeing results."
        ),
        "parent_addendum": {
            "path": str(ADDENDUM.relative_to(SANDBOX)),
            "sha256": sha256_file(ADDENDUM),
            "what_is_inherited_unchanged": [
                "primary endpoint M(c,a) = min_j N_j(c,a), unthresholded judged visual necessity",
                "paired two-sided exact sign test on discordant pairs",
                "all three pooling rules reported every time: strict (PRIMARY), lenient, itt",
                "Holm control at family alpha 0.05 over the two contrasts",
                "V, the round-1..3 hard-valid endpoint, still computed and reported",
                "generator, the three arm prompts, the repaired gates, the seven-field judgement schema",
                "zero retry, zero fallback, zero replacement; ITT accounting",
                "the floor of 40 and the target of 46",
            ],
            "what_this_record_does_not_do": (
                "It does not relax V, does not move the necessity threshold, does "
                "not modify the gate G, and does not change the floor or the target."
            ),
        },
        "frame": {
            "name": "D_hul_law_textbooks_sections",
            "manifest": str(manifest_path.relative_to(SANDBOX)),
            "manifest_sha256": sha256_file(manifest_path),
            "manifest_schema": manifest["schema"],
            "n": n,
            "n_is_fixed_before_the_first_call": True,
            "question_types": dict(qtypes),
            "documents": len(docs),
            "source_concentration": {
                "top1_doc_chunks": docs.most_common(1)[0][1],
                "top1_doc_share": round(docs.most_common(1)[0][1] / n, 3),
                "top5_doc_share": round(sum(c for _, c in docs.most_common(5)) / n, 3),
                "note": (
                    "Declared because round-4 §7 recorded top-5 concentration as a "
                    "frame-quality concern. It is not a stopping rule."
                ),
            },
            "granularity": (
                "one section of a textbook, not one page: the whole section text "
                "plus every figure-like region inside it"
            ),
        },
        "deviation_1_rule_3_reading": {
            "what_changed": (
                "Frame D admits a rendered vector region as a resolvable figure "
                "crop. Frames B and C counted embedded rasters only."
            ),
            "rule_3_frozen_text": (
                "ROUND3_FRAMEB_ADDENDUM.md rule 3 - 'At least one extracted figure "
                "crop resolvable on disk; pages without a resolvable crop are EXCLUDED'"
            ),
            "frameb_addendum_sha256": sha256_file(FRAMEB_ADDENDUM),
            "frame_c_operationalisation": (
                "ROUND4_FRAME_DETERMINATION_v3: largest EMBEDDED RASTER on the page "
                "must have min-dimension >= 203 px"
            ),
            "frame_d_operationalisation": (
                "any crop written to disk for the unit, embedded raster or rendered "
                "vector region, must have min-dimension >= 203 px"
            ),
            "why_the_wider_reading_is_defensible": (
                "Law textbooks draw their tables and diagrams with strokes rather "
                "than placing scans, so the narrow reading excludes the corpus's "
                "dominant figure form. Visual adjudication of the vector regions "
                "found them to be genuine flowcharts, org charts, specimen forms "
                "and ruled tables, not artefacts."
            ),
            "why_this_is_still_a_deviation": (
                "Vector renders were never in the round-1 or Frame-B evidence "
                "bundles, and SECTION_FRAME_DETERMINATION.json declined this "
                "reading precisely because it was the binding constraint. Adopting "
                "it now is a gate change and must be read as one."
            ),
            "counts_under_both_readings": {
                "frozen_reading_embedded_rasters_only": 28,
                "literal_reading_any_crop": n,
                "floor": 40,
                "note": (
                    "Recorded so the choice is visible: the frozen reading is below "
                    "the floor and the literal reading is above it. A reader may "
                    "discount Frame D on exactly this ground."
                ),
            },
            "pre_registered_sensitivity_analysis": {
                "requirement": (
                    "The 28 chunks that also pass the frozen reading are a subset "
                    "of the 67. Every endpoint must ALSO be reported on that subset, "
                    "every time, whatever it shows."
                ),
                "why": (
                    "It is the only way a reader can see whether the result depends "
                    "on the widened gate. Fixed now so it cannot be dropped later."
                ),
                "subset_n": 28,
                "subset_is_below_floor": True,
                "subset_significance_claims": "suppressed, as the floor clause requires",
            },
        },
        "deviation_2_new_frame_not_the_three_named_frames": {
            "s7_frozen_text": (
                "ROUND4_NECESSITY_ADDENDUM.md §7 - the frame must not be the round-1 "
                "16, the Frame B 15, or the repaired 16"
            ),
            "how_freshness_was_established": (
                "By source bytes and by passage text, not by doc_id: no Frame-D "
                "source PDF is byte-identical to any of the legacy 48 documents "
                "those frames were drawn from, and the maximum 8-word shingle "
                "containment against every chunk of those frames is 0.023."
            ),
            "audit": "corpus/reports/SECTION_FRAME_DETERMINATION.json, block freshness_audit_s7",
            "sealed_frame_c_pages_excluded": (
                "A unit whose (source_sha256, page) appears in the sealed frame-C 24 "
                "is excluded from Frame D, so Frame D does not re-test pages that "
                "have already been run."
            ),
        },
        "figure_text_channel": {
            "what_it_is": (
                "Per-unit OCR of the figure regions, carried as evidence.figure_text, "
                "with each word marked for whether it also occurs in the text layer."
            ),
            "measured_fact_about_the_instrument": (
                "The sealed evidence contract publishes only text, document_structure "
                "and images to the model, so figure_text does NOT enter the prompt "
                "and does NOT change what any arm sees. Verified by rendering a "
                "generation request and searching the payload."
            ),
            "therefore_its_role": (
                "A pre-registered stratifier and a diagnostic, not an input. It is "
                "the operational test of whether the image carries information the "
                "text does not, which is the premise of the visual-necessity endpoint."
            ),
            "gate": (
                "tesseract vie+eng --psm 11, TSV per-word confidence >= 90, word >= 3 "
                "chars, 400 dpi, region padded 4 pt"
            ),
            "gate_calibration": str(CALIBRATION.relative_to(SANDBOX)),
            "gate_calibration_sha256": sha256_file(CALIBRATION),
            "not_quotable_as_prose": (
                "At confidence 90 roughly one word in ten is still an OCR slip on "
                "graphical strokes, so these words must never be treated as context "
                "text for the verbatim-quote gate. The gate reads evidence.text only."
            ),
        },
        "pre_registered_stratum": {
            "definition": (
                "image_only_content = the unit's figure regions yield at least one "
                "gate-passing word absent from both the page text layer and the "
                "section prose"
            ),
            "counts": dict(stratum),
            "declared_before_execution": True,
            "what_is_expected": (
                "If judged visual necessity is driven by the image carrying "
                "information the text lacks, necessity should be higher in the "
                "image_only_content stratum. This is a secondary, descriptive "
                "comparison; it is not a confirmatory contrast and carries no Holm "
                "correction."
            ),
            "why_declared_now": (
                "Rounds 1-3 found the corpus text-sufficient, with OCR text "
                "restating the diagram in 10 of 15 Frame-B pages. Splitting on that "
                "property after seeing results would be a post-hoc subgroup."
            ),
        },
        "text_source": {
            "primary": "PDF text layer, layout-preserving, never overwritten by OCR",
            "why_not_rebuilt_from_ocr": (
                "All 26 sources are born-digital and 86% of figure-bearing pages "
                "carry a real text layer. Measured on 24 sampled pages, tesseract "
                "vie+eng reaches median CER 1.89% against that layer, so rebuilding "
                "from OCR would replace the typesetter's own output with a lossy copy."
            ),
            "measurement": str(OCR_PROBE.relative_to(SANDBOX)),
            "measurement_sha256": sha256_file(OCR_PROBE),
        },
        "power": {
            "n": n,
            "floor": 40,
            "target": 46,
            "reaches_floor": n >= 40,
            "reaches_target": n >= 46,
            "consequence": (
                "n=67 is above the floor of 40 and above the target of 46, so the "
                "floor clause does not apply to the full frame and Holm rejection "
                "flags are NOT suppressed for it."
            ),
            "honest_statement_of_what_is_still_underpowered": (
                "The addendum's own power table puts ECM-vs-structured at roughly "
                "0.43 at n=46 and needing n~90. At n=67 that contrast remains "
                "underpowered, and a null on it is not evidence of no effect. This "
                "is declared now rather than presented afterwards as a fair test "
                "that happened to fail."
            ),
            "sensitivity_subset_is_below_floor": True,
        },
        "inputs_bound_by_sha256": {
            "eligible_units": {
                "path": "datasets_sections/ELIGIBLE_UNITS.json",
                "sha256": sha256_file(SANDBOX / "datasets_sections/ELIGIBLE_UNITS.json"),
            },
            "rights_ledger": {
                "path": str(RIGHTS.relative_to(SANDBOX)),
                "sha256": sha256_file(RIGHTS),
            },
            "scope_decision": {
                "path": str(SCOPE.relative_to(SANDBOX)),
                "sha256": sha256_file(SCOPE),
            },
            "determination": {
                "path": str(DETERMINATION.relative_to(SANDBOX)),
                "sha256": sha256_file(DETERMINATION),
            },
            "sealed_frame_c": {
                "path": str(SEALED_C.relative_to(SANDBOX)),
                "sha256": sha256_file(SEALED_C),
            },
        },
        "budget_and_stop_rules": {
            "calls_if_executed": n * 3 + n * 3 * 2,
            "generation_calls": n * 3,
            "judge_calls": n * 3 * 2,
            "owner_authorization_required": True,
            "why": (
                "ROUND4_NECESSITY_ADDENDUM.md §6 requires an explicit hard USD cap "
                "from the owner. The runner must refuse every paid call without one, "
                "and must record remaining tasks as NOT_ATTEMPTED:budget_cap rather "
                "than overspending."
            ),
            "stop_on_first_qualification_failure": True,
            "retry": 0,
            "fallback": False,
            "replacement": False,
        },
        "what_would_make_this_record_invalid": [
            "changing n after the first call",
            "changing the rule-3 reading after seeing results",
            "reporting the strict/lenient/itt triple selectively",
            "omitting the 28-chunk sensitivity analysis",
            "treating figure_text words as quotable context for the gate",
            "pooling Frame D with the sealed frame-C 24",
        ],
    }

    print(f"frame            D_hul_law_textbooks_sections")
    print(f"manifest         {manifest_path.name}")
    print(f"manifest sha256  {record['frame']['manifest_sha256']}")
    print(f"n                {n}   floor 40   target 46")
    print(f"question types   {dict(qtypes)}")
    print(f"documents        {len(docs)}  top1 share "
          f"{record['frame']['source_concentration']['top1_doc_share']:.0%}")
    print(f"stratum          {dict(stratum)}")
    print(f"sensitivity      28-chunk frozen-reading subset, reported every time")
    print(f"calls if run     {record['budget_and_stop_rules']['calls_if_executed']} "
          f"({n*3} generation + {n*3*2} judge)")

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(SANDBOX)}")
    print("sha256", sha256_file(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
