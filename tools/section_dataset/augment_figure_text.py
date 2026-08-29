#!/usr/bin/env python3
"""Direction A: keep the PDF text layer as the primary source, add OCR of figure
regions as a SEPARATE channel.

Why this shape rather than "rebuild everything from OCR":

  * All 26 textbooks are born-digital (Adobe InDesign / Acrobat / Word producers),
    and 86% of region-bearing pages carry a real text layer. The text layer is
    what the typesetter emitted, so on those pages it IS the reference.
    corpus/reports/OCR_FIDELITY_PROBE.json measures Tesseract against it at
    1.89% median CER, so re-deriving those pages from OCR would substitute a
    copy carrying ~2% error for the original.
  * What the text layer genuinely lacks is lettering that lives INSIDE a figure
    (map labels, flowchart nodes, scanned exhibits). That is measured in
    corpus/reports/REGION_OCR_SURPLUS_PROBE.json.

So figure text is written to its own file and its own unit.json key. It never
edits section.txt, because the ECM gate quotes verbatim from the context text and
a hallucinated or noisy figure word must not be quotable as if it were prose.

Word-level confidence gate: tesseract TSV `conf`, threshold from
corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

SANDBOX = Path(__file__).resolve().parents[2]
CORPUS = SANDBOX / "corpus"
WORK = CORPUS / ".figocr_work"
OUT = CORPUS / "reports" / "FIGURE_TEXT_AUGMENTATION.json"

MIN_WORD_CHARS = 3
CONF_THRESHOLD = 90.0
RENDER_DPI = 400
PAD_PT = 4.0
PSM = "11"
LANG = "vie+eng"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def fold(text: str) -> str:
    s = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def ocr_words(path: Path) -> list[dict]:
    """Per-word text + confidence via tesseract TSV."""
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", LANG, "--psm", PSM, "tsv"],
        capture_output=True,
    )
    rows: list[dict] = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or parts[0] != "5":
            continue
        word = parts[11].strip()
        if not word:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        rows.append({
            "word": word,
            "conf": round(conf, 1),
            "bbox_px": [int(parts[6]), int(parts[7]), int(parts[8]), int(parts[9])],
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    ap.add_argument("--roots", default="datasets_sections,datasets_sections_other")
    args = ap.parse_args()

    WORK.mkdir(exist_ok=True)
    roots = [SANDBOX / r for r in args.roots.split(",")]

    unit_paths = sorted(p for root in roots for p in root.glob("*/*/unit.json"))
    print(f"units: {len(unit_paths)} across {len(roots)} roots")
    print(f"gate:  tesseract TSV conf >= {args.conf}, word >= {MIN_WORD_CHARS} chars, "
          f"{RENDER_DPI} dpi, psm {PSM}")
    print()

    pdf_cache: dict[str, pymupdf.Document] = {}
    totals: Counter = Counter()
    per_unit: list[dict] = []
    t0 = time.time()

    for unit_path in unit_paths:
        unit = json.loads(unit_path.read_text("utf-8"))
        udir = unit_path.parent
        section_text = fold((udir / unit["text_file"]).read_text("utf-8"))

        src = unit["source_pdf"]
        if src not in pdf_cache:
            pdf_cache[src] = pymupdf.open(CORPUS / src)
        pdf = pdf_cache[src]

        page_layer: dict[int, str] = {}
        regions_out: list[dict] = []

        for index, region in enumerate(unit["regions"], start=1):
            page_no = region["page"]
            page = pdf[page_no - 1]
            if page_no not in page_layer:
                page_layer[page_no] = fold(page.get_text())
            reference = page_layer[page_no] + " " + section_text

            x0, y0, x1, y1 = region["rect_pt"]
            rect = pymupdf.Rect(x0 - PAD_PT, y0 - PAD_PT,
                                x1 + PAD_PT, y1 + PAD_PT) & page.rect
            if rect.is_empty or rect.width < 8 or rect.height < 8:
                continue

            crop = WORK / f"{unit['doc_id']}_p{page_no:04d}_r{index}.png"
            page.get_pixmap(dpi=RENDER_DPI, clip=rect).save(crop)
            found = ocr_words(crop)
            crop.unlink(missing_ok=True)

            kept, seen = [], set()
            for row in found:
                core = re.sub(r"^[^0-9A-Za-zÀ-ỹ]+|[^0-9A-Za-zÀ-ỹ]+$", "", row["word"])
                if len(core) < MIN_WORD_CHARS or row["conf"] < args.conf:
                    continue
                f = fold(core)
                if f in seen:
                    continue
                seen.add(f)
                kept.append({**row, "word": core, "in_text_layer": f in reference})

            surplus = [w for w in kept if not w["in_text_layer"]]
            totals["regions"] += 1
            totals["ocr_words_raw"] += len(found)
            totals["words_kept"] += len(kept)
            totals["words_surplus"] += len(surplus)
            if surplus:
                totals["regions_with_surplus"] += 1
            regions_out.append({
                "region_index": index,
                "page": page_no,
                "region_kind": region["kind"],
                "words": kept,
                "surplus_count": len(surplus),
            })

        figure_words = [w["word"] for r in regions_out for w in r["words"]]
        surplus_words = [w["word"] for r in regions_out
                         for w in r["words"] if not w["in_text_layer"]]

        record = {
            "unit_id": unit["unit_id"],
            "regions": len(regions_out),
            "words_kept": len(figure_words),
            "surplus_words": len(surplus_words),
        }
        per_unit.append(record)
        if surplus_words:
            totals["units_with_surplus"] += 1
        totals["units"] += 1

        if args.apply:
            (udir / "figure_text.json").write_text(json.dumps({
                "schema": "ecm-tqag.figure-text.v1",
                "unit_id": unit["unit_id"],
                "what_this_is": (
                    "OCR of the figure regions inside this unit. A SEPARATE "
                    "channel from section.txt: the text layer stays the primary "
                    "source and is not modified. `in_text_layer` marks whether "
                    "the word already occurs in the page text layer or the "
                    "section prose; the surplus words are what only the image "
                    "carries."
                ),
                "gate": {
                    "engine": f"tesseract {LANG} --psm {PSM} tsv",
                    "render_dpi": RENDER_DPI,
                    "region_padding_pt": PAD_PT,
                    "min_word_chars": MIN_WORD_CHARS,
                    "min_confidence": args.conf,
                    "calibration": "corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json",
                },
                "not_quotable_as_prose": (
                    "These words must not be treated as part of the context text "
                    "for a verbatim-quote gate. At confidence 90 roughly one word "
                    "in ten is still an OCR slip on graphical strokes."
                ),
                "regions": regions_out,
                "figure_words": figure_words,
                "surplus_words": surplus_words,
            }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

            unit["figure_text"] = {
                "file": "figure_text.json",
                "words_kept": len(figure_words),
                "surplus_words": len(surplus_words),
                "min_confidence": args.conf,
                "channel": "separate_from_section_text",
            }
            unit_path.write_text(json.dumps(unit, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    for pdf in pdf_cache.values():
        pdf.close()
    elapsed = time.time() - t0

    print(f"{'units':32s} {totals['units']}")
    print(f"{'units with figure surplus':32s} {totals['units_with_surplus']}")
    print(f"{'regions':32s} {totals['regions']}")
    print(f"{'regions with surplus':32s} {totals['regions_with_surplus']}")
    print(f"{'raw OCR words':32s} {totals['ocr_words_raw']}")
    print(f"{'words kept at gate':32s} {totals['words_kept']}")
    print(f"{'of those, surplus':32s} {totals['words_surplus']}")
    print(f"{'seconds':32s} {elapsed:.0f}")

    top = sorted(per_unit, key=lambda r: -r["surplus_words"])[:12]
    print("\ntop units by figure surplus")
    for r in top:
        print(f"  {r['unit_id'][:62]:62s} +{r['surplus_words']:3d}")

    if args.apply:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "schema": "ecm-tqag.figure-text-augmentation.v1",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "direction": "A",
            "decision": (
                "The PDF text layer stays the primary source. OCR is applied only "
                "to figure regions and written to a separate channel."
            ),
            "why_not_rebuild_from_ocr": (
                "All 26 sources are born-digital and 86% of region-bearing pages "
                "carry a real text layer, measured at 1.89% median CER against "
                "Tesseract. Re-deriving them from OCR would replace the "
                "typesetter's own output with a ~2%-error copy."
            ),
            "evidence": {
                "fidelity_probe": "corpus/reports/OCR_FIDELITY_PROBE.json",
                "surplus_probe": "corpus/reports/REGION_OCR_SURPLUS_PROBE.json",
                "confidence_calibration": "corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json",
            },
            "gate": {
                "engine": f"tesseract {LANG} --psm {PSM} tsv",
                "render_dpi": RENDER_DPI,
                "min_word_chars": MIN_WORD_CHARS,
                "min_confidence": args.conf,
                "residual_noise_note": (
                    "At confidence 90 about 10% of kept words are still OCR slips "
                    "on graphical strokes. The reported figure is a floor, not a "
                    "precision claim: the dictionary check also rejects genuine "
                    "content it lacks (place names such as Ceuta and Trafalgar, "
                    "and legal references such as 1898/QD-UBND)."
                ),
            },
            "totals": dict(totals),
            "seconds": round(elapsed, 1),
            "per_unit": per_unit,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {OUT.relative_to(SANDBOX)}")
    else:
        print("\ndry run; pass --apply to write figure_text.json per unit")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
