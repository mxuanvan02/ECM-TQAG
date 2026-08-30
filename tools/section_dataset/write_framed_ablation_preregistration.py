#!/usr/bin/env python3
"""Freeze the frame-D text-only ablation design BEFORE any call is made.

WHY THIS ABLATION EXISTS, AND WHY IT IS NOT A RE-RUN OF THE SEALED ONE
----------------------------------------------------------------------
The frame-D census returned a null on judged visual necessity: no contrast
rejected under Holm at n=67, with `visual_necessity` pinned at 1 in 208 of 239
judge records. Two explanations survive that result and the census cannot
separate them:

  H1  DOCUMENT CLASS. Vietnamese law textbooks are written so the prose is
      self-sufficient; the figure restates what the text already says. Under H1
      the null is a true finding about the corpus and no instrument change helps.

  H2  INSTRUMENT DESIGN. The generation gate requires a verbatim quotation from
      the recognised text `T_c`. A question that must anchor to a text span is
      structurally likely to be answerable from that span. Under H2 the null is
      partly manufactured by the gate, and it would persist even on a corpus
      whose figures do carry independent content.

Measured in the census records, 65 of 120 admitted questions open with "theo văn
bản nguồn ..." and only 40 of 120 refer to a figure at all, which is consistent
with H2 but does not test it.

This ablation tests them apart. It replaces the rated 1-5 score with a
mechanical measurement -- can the item be answered WITHOUT the figure? -- and
reads that measurement inside two strata fixed here, before execution:

  * whether the QUESTION refers to a figure, which is the H2 handle: if
    figure-referring items show materially higher measured necessity than
    prose-anchored ones, the gate is implicated and the remedy is instrument
    side. If both strata are near-zero, H1 is implicated and no prompt change
    will recover necessity from this corpus.
  * whether the CHUNK carries an embedded raster or only rendered vector
    regions. The owner's reading was that necessity fails because the figures
    are "only tables". The census contradicts that on rated scores -- table-only
    chunks scored vn>=3 five times against once for raster-bearing chunks -- so
    this stratum is carried to settle it on a measurement rather than a rating.

Relation to the sealed frame-C ablation: same two-branch design, same
deterministic grading, same discipline. Different frame (D, sections), different
item set (120 vs 50), and two added strata that the frame-C ablation did not
declare. It does not modify, re-analyse or re-label the frame-C ablation or the
frame-D census.

Read-only except for the one record it writes. Makes no network call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
EXPERIMENT = SANDBOX / "experiment"
MANIFEST = (EXPERIMENT / "dataset_framed"
            / "dataset_manifest_framed_20260829T195643Z.json")
CENSUS = EXPERIMENT / "runs" / "round4_framed_census_20260829T200000Z"
PREREG_FRAME_D = (SANDBOX / "prospective" / "v3103_round2"
                  / "ROUND4_FRAMED_PREREGISTRATION.json")
ADDENDUM = (SANDBOX / "prospective" / "v3103_round2"
            / "ROUND4_NECESSITY_ADDENDUM.md")
OUT = (SANDBOX / "prospective" / "v3103_round2"
       / "ROUND4_FRAMED_ABLATION_PREREGISTRATION.json")

GENERATOR = "qwen/qwen3-vl-8b-instruct"

# A question is treated as figure-referring when it names a figure-like object.
# Fixed here so the stratum cannot be redefined after seeing outcomes.
FIGURE_REFERENCE_RE = re.compile(
    r"h[ìi]nh|[ảa]nh|s[ơo]\s*đ[ồo]|b[ảa]ng|bi[ểe]u|đ[ồo]\s*th[ịi]|minh\s*h[ọo]a",
    re.I,
)

# Golds this short after normalisation make the containment rule vacuous.
TRIVIAL_GOLD_MAX_CHARS = 2


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def normalise(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).casefold()


def load_admitted() -> list[dict]:
    """Every generation that passed the deterministic gate G in the census."""
    out = []
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
        out.append({
            "item_id": f"{chunk}::{parts[5]}",
            "chunk_id": chunk,
            "arm": parts[5],
            "question_type": obj["question_type"],
            "question": obj["question"],
            "gold_answer": obj["answer"],
        })
    return sorted(out, key=lambda r: r["item_id"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text("utf-8"))
    packages = {p["chunk_id"]: p for p in manifest["packages"]}
    items = load_admitted()

    def raster_bearing(chunk_id: str) -> bool:
        return any(im.get("source") == "embedded_raster"
                   for im in packages[chunk_id]["evidence"]["images"])

    trivial = [i for i in items
               if i["question_type"] == "short_answer"
               and len(normalise(i["gold_answer"])) <= TRIVIAL_GOLD_MAX_CHARS]
    scored = [i for i in items if i not in trivial]

    strata = {
        "question_reference": {
            "question_refers_to_figure": [
                i["item_id"] for i in scored if FIGURE_REFERENCE_RE.search(i["question"])
            ],
            "question_does_not_refer_to_figure": [
                i["item_id"] for i in scored
                if not FIGURE_REFERENCE_RE.search(i["question"])
            ],
        },
        "chunk_composition": {
            "has_embedded_raster": [
                i["item_id"] for i in scored if raster_bearing(i["chunk_id"])
            ],
            "rendered_vector_only": [
                i["item_id"] for i in scored if not raster_bearing(i["chunk_id"])
            ],
        },
    }

    record = {
        "schema": "ecm-tqag.round4.framed-ablation-preregistration.v1",
        "status": ("FROZEN, prospective. No paid call is authorised by this "
                   "document; execution additionally requires an owner "
                   "authorization naming an explicit USD cap."),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),

        "question_this_answers": (
            "The frame-D census returned a null on judged visual necessity. Is "
            "that null a property of the DOCUMENT CLASS (law textbook prose is "
            "self-sufficient) or of the INSTRUMENT (the verbatim-quote gate "
            "anchors questions to a text span, so they are answerable from that "
            "span)? The census cannot separate the two; this design can."
        ),
        "hypotheses": {
            "H1_document_class": (
                "Vietnamese law textbooks restate figure content in prose. "
                "Predicts LOW measured necessity in BOTH question strata, and no "
                "instrument change recovers necessity from this corpus."
            ),
            "H2_instrument_design": (
                "The verbatim-quote gate pushes the generator toward "
                "prose-anchored questions. Predicts measured necessity "
                "materially HIGHER among figure-referring items than among "
                "prose-anchored ones, which would make the remedy instrument "
                "side rather than corpus side."
            ),
            "how_they_are_distinguished": (
                "By the question_reference stratum, whose membership is fixed in "
                "this record before any call. H1 and H2 are not exclusive; a "
                "split in both directions is reportable and is stated as such."
            ),
            "prior_evidence_that_motivates_H2_without_testing_it": {
                "questions_opening_theo_van_ban": 65,
                "questions_referring_to_any_figure": 40,
                "of_120_admitted": True,
                "source": "counted from the census generation records",
            },
        },

        "design": {
            "branches": {
                "TEXT": ("recognised text layer T_c plus the question. No image, "
                         "no figure description, no rationale."),
                "TEXT_IMG": ("the same T_c, the same question, plus the chunk's "
                             "own figure crops from I_c."),
            },
            "paired_within_item": True,
            "why_the_control_branch_is_required": (
                "Without TEXT_IMG a wrong answer under TEXT is ambiguous between "
                "'the item needs the figure' and 'the model cannot answer this "
                "item at all'. With it, the two separate."
            ),
            "answerer_model": GENERATOR,
            "why_the_generator_answers_its_own_items": (
                "It is the census generator, so the measurement is on the same "
                "model whose output the census judged. A different answerer would "
                "confound answerer capability with visual necessity. This is the "
                "same choice the sealed frame-C ablation made and is retained for "
                "comparability."
            ),
            "temperature": 0,
            "retry": 0,
            "fallback": False,
            "identical_between_branches": (
                "prompt text, response schema, decoding settings. Only the image "
                "content blocks differ."
            ),
        },

        "items": {
            "population": ("every generation that passed the deterministic gate G "
                           "in round4_framed_census_20260829T200000Z"),
            "n_admitted": len(items),
            "n_scored": len(scored),
            "n_fixed_before_the_first_call": True,
            "distinct_chunks": len({i["chunk_id"] for i in items}),
            "by_arm": dict(Counter(i["arm"] for i in items)),
            "by_question_type": dict(Counter(i["question_type"] for i in items)),
            "calls": len(items) * 2,
        },

        "declared_exclusion_before_execution": {
            "rule": (f"a short-answer item whose gold answer normalises to "
                     f"<= {TRIVIAL_GOLD_MAX_CHARS} characters is excluded from the "
                     f"graded denominator"),
            "why": (
                "The short-answer rule credits containment in either direction. A "
                "gold of '0' is contained in almost any returned string, so such "
                "an item would auto-pass both branches and count as evidence that "
                "the figure was unnecessary. That is a generation defect being "
                "read as a measurement."
            ),
            "n_excluded": len(trivial),
            "item_ids": [i["item_id"] for i in trivial],
            "by_arm": dict(Counter(i["arm"] for i in trivial)),
            "known_asymmetry_declared_now": (
                "The excluded items are 3 direct and 2 structured_no_contract, "
                "none from ecm_full. Removing them therefore removes items that "
                "would have auto-passed in two baseline arms only, which flatters "
                "those arms' necessity slightly LESS than leaving them in. The "
                "direction of the bias is stated here so it cannot be presented "
                "later as neutral."
            ),
            "sensitivity_required": (
                "Both endpoints are additionally reported over all "
                f"{len(items)} items with the excluded ones scored as correct in "
                "both branches. They are concordant by construction, so they "
                "cannot move the McNemar test, only the raw rates."
            ),
        },

        "grading": {
            "deterministic": True,
            "no_model_or_human_judges_correctness": True,
            "multiple_choice": ("correct iff the returned option_index equals the "
                                "item's recorded correct_option; chance level 25%"),
            "short_answer": (
                "let N' = casefold o whitespace-collapse o NFC; correct iff "
                "N'(gold) is contained in N'(returned) or the reverse"
            ),
            "leniency_direction": (
                "The containment rule is lenient, and leniency biases AGAINST the "
                "claim that items are visually necessary. A high measured "
                "necessity under this rule is therefore conservative."
            ),
        },

        "endpoints": {
            "primary": {
                "measured_visual_necessity": "V*(i) = 1 - R_TEXT(i)",
                "figure_attributable_gain": "G(i) = R_TEXT_IMG(i) - R_TEXT(i) in {-1,0,+1}",
                "test": ("exact two-sided McNemar on the items discordant between "
                         "branches, reported with its discordance counts"),
                "why_mcnemar_here": (
                    "It is within-item and does not depend on the arm structure, "
                    "so its denominator is defensible in a way the per-arm rates "
                    "are not."
                ),
                "alpha": 0.05,
            },
            "reported_separately": {
                "PRIMARY_ALL": f"all {len(scored)} scored items",
                "PRIMARY_MCQ": ("the multiple-choice items only, graded without any "
                                "string heuristic"),
            },
            "interval": "Clopper-Pearson exact 95% on every rate",
        },

        "pre_registered_strata": {
            "why_fixed_now": (
                "Both stratifications are the diagnostic content of this run. "
                "Fixing membership before execution is what prevents choosing the "
                "split that produces a result."
            ),
            "question_reference": {
                "definition": ("the question text matches the frozen regex for a "
                               "figure-like object (hình / ảnh / sơ đồ / bảng / "
                               "biểu / đồ thị / minh hoạ)"),
                "regex": FIGURE_REFERENCE_RE.pattern,
                "sizes": {k: len(v) for k, v in strata["question_reference"].items()},
                "reads_on": "H2",
            },
            "chunk_composition": {
                "definition": ("the chunk carries at least one embedded raster, "
                               "versus rendered vector regions only"),
                "sizes": {k: len(v) for k, v in strata["chunk_composition"].items()},
                "reads_on": (
                    "the owner's hypothesis that necessity fails because the "
                    "figures are only tables. The census rated table-only chunks "
                    "vn>=3 five times against once for raster-bearing chunks, "
                    "which contradicts that hypothesis on ratings; this stratum "
                    "settles it on a measurement."
                ),
            },
            "not_collinear": (
                "The two splits cross with all four cells populated "
                "(32 / 48 / 23 / 17 over the 120 admitted items), so neither is a "
                "relabelling of the other."
            ),
            "stratum_tests_are_descriptive": (
                "Each stratum is smaller than the item set and no stratum is "
                "powered for a confirmatory claim. Stratum McNemar tests are "
                "reported with discordance counts and carry NO significance claim; "
                "the confirmatory test is the pooled one."
            ),
            "membership": strata,
        },

        "power": {
            "n_scored": len(scored),
            "mcnemar_discordance_needed_for_alpha_0_05": (
                "6 unidirectional discordant items give p=0.0312; 5 give p=0.0625. "
                "Fewer than 6 unidirectional discordant items cannot reach 0.05, "
                "whatever the split looks like."
            ),
            "honest_limit": (
                "This design measures whether items are answerable without the "
                "figure. It does not measure whether a DIFFERENT gate would "
                "produce more visually necessary items; that would need a new "
                "generation round under a modified gate, which is out of scope "
                "here and is not authorised by this record."
            ),
        },

        "execution_discipline": {
            "one_call_per_item_per_branch": True,
            "zero_retry": True,
            "run_lock_and_per_task_claim": "O_EXCL claim plus a single flock run lock",
            "budget": ("reported cost accumulated per call and checked against the "
                       "USD cap BEFORE each call; if the cap would bind, remaining "
                       "tasks are recorded NOT_ATTEMPTED:budget_cap rather than "
                       "overspending"),
            "does_not_modify": (
                "the census records, the gate, the frame-D manifest, the frame-C "
                "ablation, or any sealed report. This adds a measurement."
            ),
        },

        "inputs_bound_by_sha256": {
            "frame_manifest": str(MANIFEST.relative_to(SANDBOX)),
            "frame_manifest_sha256": sha256_file(MANIFEST),
            "frame_d_preregistration": str(PREREG_FRAME_D.relative_to(SANDBOX)),
            "frame_d_preregistration_sha256": sha256_file(PREREG_FRAME_D),
            "parent_addendum": str(ADDENDUM.relative_to(SANDBOX)),
            "parent_addendum_sha256": sha256_file(ADDENDUM),
            "census_run": CENSUS.name,
        },

        "pre_committed_reporting": [
            "Reported whatever it shows, including every outcome below.",
            "If measured necessity is low in BOTH question strata, H1 is "
            "supported: the corpus limitation is real and no prompt or gate change "
            "recovers necessity from Vietnamese law textbooks. The census null "
            "then stands strengthened, with a measurement replacing a rated score.",
            "If measured necessity is materially higher among figure-referring "
            "items, H2 is supported: the gate contributes to the null, and the "
            "reported corpus limitation must be softened to a joint "
            "corpus-and-instrument limitation.",
            "If TEXT_IMG is not better than TEXT anywhere, that is reported as the "
            "figures adding nothing measurable, which is a stronger negative than "
            "the rated endpoint gave.",
            "If TEXT beats TEXT_IMG, that is reported too: images can distract, "
            "and the direction is not pre-assumed.",
            "No outcome licenses relaxing the gate, re-labelling the census "
            "endpoints as confirmatory, or generating replacement items.",
        ],

        "what_would_make_this_record_invalid": [
            "changing any stratum definition or membership after the first call",
            "changing the grading rule after seeing any response",
            "adding, dropping or regenerating items after the first call",
            "reporting one stratum and not the other",
            "presenting a stratum result as confirmatory",
        ],
    }

    print(f"census            {CENSUS.name}")
    print(f"items admitted    {len(items)}")
    print(f"items scored      {len(scored)}  (excluding {len(trivial)} trivial golds)")
    print(f"calls if executed {len(items) * 2}")
    print(f"by arm            {dict(Counter(i['arm'] for i in items))}")
    for name, split in strata.items():
        print(f"stratum {name:20s} {[(k, len(v)) for k, v in split.items()]}")

    if not args.apply:
        print("\ndry run; pass --apply to freeze")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(SANDBOX)}")
    print("sha256", sha256_file(OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
