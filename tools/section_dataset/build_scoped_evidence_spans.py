#!/usr/bin/env python3
"""Scope the evidence span of each section chunk to the pages carrying its figures.

WHY THIS EXISTS
---------------
The owner fixed the SECTION as the unit of analysis: a section is what a teacher
assigns and it can carry several items at different Bloom levels. That decision
is not revisited here.

But the section is ALSO, in the current instrument, the span the verbatim
evidence gate quotes from, and those two roles conflict. Measured on the 67
frame-D chunks, the section span runs to a median of 7,530 characters and a
maximum of 265,885. A verbatim-quotation gate over a span that long is nearly
free to satisfy: any prompt finds some sentence to copy, so the gate stops
discriminating between prompts. That is exactly what the frame-D census showed
(admission 0.64 / 0.61 / 0.54, no contrast separable), and the length effect is
visible directly: admission runs 1.00 in the shortest length band against 0.47
in the longest.

The repair keeps the unit and narrows the SPAN:

    unit of analysis   = the section              (unchanged)
    evidence span S_c  = the section's own text ON THE PAGES THAT CARRY ITS
                         FIGURE REGIONS, clipped to the section boundary

Two things follow, and the second is the one the paper actually needs:

  1. the span returns to a tractable size, so the gate can discriminate again;
  2. an admitted quotation must now come from the SAME PAGES as the figure, so
     "quote something real" becomes "quote something near the figure". The
     frame-D ablation measured only 8.7% of items as figure-attributable, and a
     gate that lets the generator quote any sentence in a 20-page section while
     naming a figure hash is a plausible cause of that.

METHOD
------
Page selection is `region_pages` as recorded by the section builder: the pages
on which a figure region was detected and assigned to this section. Nothing is
re-detected here.

Text extraction reuses `section_tree.section_clips` and
`section_tree.page_section_lines`, the same code the section dataset was built
with, so the scoped text is a SUBSET of the section text by construction rather
than a re-derivation that might drift. The clip matters: a page can hold the end
of one section and the start of the next, and without clipping the scoped span
would import prose belonging to a neighbouring section.

Furniture and watermark templates are taken from the section dataset's own
heading cache, so removal is identical to the full-section build.

Frozen rule 4 (ROUND3_FRAMEB_ADDENDUM, applied verbatim as in
round2/build_frameb.py) is then re-applied TO THE SCOPED SPAN, because a span
that no longer holds enough prose to quote from makes the gate unsatisfiable for
a dataset reason, which is a defect and not a measurement.

Read-only with respect to every existing record: reads PDFs and the section
dataset, writes one JSON report.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
SANDBOX = HERE.parents[1]
sys.path.insert(0, str(HERE))

import section_tree as st  # noqa: E402

CORPUS = SANDBOX / "corpus"
SECTIONS = SANDBOX / "datasets_sections"
# The section builder's own heading cache. Reused rather than recomputed so the
# furniture and watermark templates removed here are byte-identical to the ones
# the full-section build removed.
CACHE = CORPUS / "section_headings_cache.json"
FRAME_D = (SANDBOX / "experiment" / "dataset_framed"
           / "dataset_manifest_framed_20260829T195643Z.json")
OUT = CORPUS / "reports" / "SCOPED_EVIDENCE_SPANS.json"

# Frozen rule 4, character-for-character as build_frameb.py applies it.
_ENUM_RE = re.compile(r"^\s*-?\s*\d+[.)]\s", re.M)
RULE4_MIN_PROSE = 120
RULE4_ENUM_ITEMS = 3
RULE4_ENUM_PROSE = 400


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def rule4(text: str) -> tuple[bool, str | None, int, int]:
    """Frozen text-sufficiency rule. Returns (ok, reason, prose_chars, enum_items)."""
    enum_items = len(_ENUM_RE.findall(text or ""))
    prose_chars = len((text or "").strip())
    if enum_items >= RULE4_ENUM_ITEMS and prose_chars < RULE4_ENUM_PROSE:
        return False, "enumeration_without_prose", prose_chars, enum_items
    if prose_chars < RULE4_MIN_PROSE:
        return False, "insufficient_prose", prose_chars, enum_items
    return True, None, prose_chars, enum_items


def page_runs(pages: list[int]) -> list[list[int]]:
    """Contiguous runs of page numbers, for reporting only."""
    runs: list[list[int]] = []
    for p in sorted(set(pages)):
        if runs and p == runs[-1][1] + 1:
            runs[-1][1] = p
        else:
            runs.append([p, p])
    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true", help="write the JSON report")
    args = ap.parse_args()

    manifest = json.loads(FRAME_D.read_text("utf-8"))
    cache = json.loads(CACHE.read_text("utf-8")) if CACHE.is_file() else {}

    rows: list[dict] = []
    docs: dict[str, pymupdf.Document] = {}

    for pkg in manifest["packages"]:
        chunk_id = pkg["chunk_id"]
        ds = pkg["evidence"]["document_structure"]
        doc_id = ds["source_id"]
        label = ds["section_label"]
        region_pages = sorted(set(ds["pages"] or []))

        # locate the unit record, which carries the section geometry
        unit_path = None
        for cand in SECTIONS.glob(f"{doc_id}/*/unit.json"):
            rec = json.loads(cand.read_text("utf-8"))
            if rec["unit_id"] == chunk_id.split("::", 1)[1]:
                unit_path = cand
                unit = rec
                break
        if unit_path is None:
            raise SystemExit(f"no unit record for {chunk_id}")

        pdf_path = CORPUS / unit["source_pdf"]
        if doc_id not in docs:
            docs[doc_id] = pymupdf.open(pdf_path)
        doc = docs[doc_id]

        info = cache.get(doc_id)
        if info is None:
            raise SystemExit(f"no heading cache for {doc_id}; run the section build first")
        sections = st.build_sections(info["headings"], doc.page_count)
        idx = unit["section"]["section_index"]
        sec = sections[idx]
        furniture = set(info.get("furniture", []))
        watermarks = set(info.get("watermarks", []))

        # scoped text: the section's own lines, on the figure-bearing pages only
        parts: list[str] = []
        for pno in region_pages:
            page = doc[pno - 1]
            clip = st.section_clips(page, sec, pno)
            if clip is None:
                continue
            parts.extend(st.page_section_lines(page, clip, furniture, watermarks))
        scoped = "\n".join(parts)

        full = (unit_path.parent / unit["text_file"]).read_text("utf-8")
        ok, reason, prose, enum = rule4(scoped)

        rows.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "section_label": label,
            "section_start_page": sec["start_page"],
            "section_end_page": sec["end_page"],
            "section_span_pages": sec["end_page"] - sec["start_page"] + 1,
            "figure_pages": region_pages,
            "figure_page_runs": page_runs(region_pages),
            "full_chars": len(full),
            "scoped_chars": len(scoped),
            "reduction": round(len(scoped) / len(full), 4) if full else None,
            "scoped_is_subset_of_full": norm(scoped)[:400] in norm(full)
                                        if len(norm(scoped)) >= 400 else
                                        norm(scoped) in norm(full),
            "rule4_ok": ok,
            "rule4_reason": reason,
            "prose_chars": prose,
            "enum_items": enum,
            "scoped_text": scoped,
        })

    for doc in docs.values():
        doc.close()

    kept = [r for r in rows if r["rule4_ok"]]
    dropped = [r for r in rows if not r["rule4_ok"]]
    subset_fail = [r for r in rows if not r["scoped_is_subset_of_full"]]

    lens_full = sorted(r["full_chars"] for r in rows)
    lens_scoped = sorted(r["scoped_chars"] for r in kept)

    def med(xs: list[int]) -> int:
        return xs[len(xs) // 2] if xs else 0

    print(f"chunks in frame D          {len(rows)}")
    print(f"pass frozen rule 4 scoped  {len(kept)}")
    print(f"dropped by rule 4          {len(dropped)}")
    for r in dropped:
        print(f"    {r['chunk_id'][:70]:70s} prose={r['prose_chars']:5d} {r['rule4_reason']}")
    print()
    print(f"full span   median {med(lens_full):7d}  max {lens_full[-1]:7d}")
    print(f"scoped span median {med(lens_scoped):7d}  max {lens_scoped[-1] if lens_scoped else 0:7d}")
    print(f"subset check failures      {len(subset_fail)}")
    print(f"figure pages per chunk     "
          f"{ {k: sum(1 for r in rows if len(r['figure_pages']) == k) for k in sorted({len(r['figure_pages']) for r in rows})} }")

    if args.emit:
        report = {
            "schema": "ecm-tqag.scoped-evidence-spans.v1",
            "unit_of_analysis": "one section of a law textbook (owner decision, unchanged)",
            "what_changed": (
                "The evidence span quoted by the verbatim gate is narrowed from the "
                "whole section to the section's own text on the pages carrying its "
                "figure regions. The unit of analysis is not changed."),
            "why": (
                "Measured on frame D, the section span has median 7530 and maximum "
                "265885 characters. A verbatim gate over a span that long is nearly "
                "free to satisfy, so it stops discriminating between prompts; frame-D "
                "admission was 0.64 / 0.61 / 0.54 with no separable contrast, and "
                "admission by length band runs 1.00 (shortest) to 0.47 (longest). "
                "Narrowing the span also forces an admitted quotation to come from the "
                "same pages as the figure, which is the multimodal claim the paper "
                "makes and which the 8.7% figure-attributable rate did not support."),
            "method": {
                "page_selection": "region_pages as recorded by the section builder; nothing re-detected",
                "text_extraction": ("section_tree.section_clips + page_section_lines, the same "
                                    "code the section dataset was built with, so the scoped text "
                                    "is a subset of the section text by construction"),
                "clipping": ("required: a page can hold the end of one section and the start of "
                             "the next, and without clipping the scoped span would import prose "
                             "from a neighbouring section"),
                "furniture_removal": "identical templates to the full-section build, from its heading cache",
                "rule4": ("frozen ROUND3_FRAMEB_ADDENDUM rule 4, re-applied to the SCOPED span: "
                          f"exclude if prose < {RULE4_MIN_PROSE} chars, or >= {RULE4_ENUM_ITEMS} "
                          f"enumerated items with prose < {RULE4_ENUM_PROSE}"),
            },
            "counts": {
                "frame_d_chunks": len(rows),
                "pass_rule4_scoped": len(kept),
                "dropped_by_rule4_scoped": len(dropped),
                "subset_check_failures": len(subset_fail),
            },
            "span_lengths": {
                "full_median": med(lens_full), "full_max": lens_full[-1],
                "scoped_median": med(lens_scoped),
                "scoped_max": lens_scoped[-1] if lens_scoped else 0,
                "length_measure": "raw len() of the extracted text, consistent with MULTIMODAL_DATASET_QUALITY.json",
            },
            "dropped": [{k: r[k] for k in
                         ("chunk_id", "prose_chars", "enum_items", "rule4_reason",
                          "scoped_chars", "full_chars")}
                        for r in dropped],
            "rows": [{k: v for k, v in r.items() if k != "scoped_text"} for r in rows],
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf-8")
        # the scoped text itself is corpus prose: kept beside the report, not published
        (CORPUS / "reports" / ".scoped_text.json").write_text(
            json.dumps({r["chunk_id"]: r["scoped_text"] for r in rows},
                       ensure_ascii=False), "utf-8")
        print(f"\nwrote {OUT.relative_to(SANDBOX)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
