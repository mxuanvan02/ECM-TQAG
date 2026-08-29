#!/usr/bin/env python3
"""Does OCR of a figure region recover lettering absent from the page text layer?

Direction A, as decided by the owner: the PDF text layer stays the primary
source (86.3% of unit pages are born-digital and carry a real layer, and
Tesseract reproduces that layer at only ~1.9% median CER, so a full re-OCR would
replace an exact source with a lossy copy). OCR is applied ONLY to the figure
regions, to recover text drawn inside a diagram that the text layer never held.

This matters for the ECM paper specifically. Its gate requires a quoted span to
be reproducible from the declared evidence, and judged visual necessity is the
binding endpoint. A question can only genuinely require the image if the image
carries information the text does not. This probe measures whether that
information exists at all, before any paid model call.

Method per region:
  1. render the region rect alone at --dpi (default 400; figure lettering is
     small, and the page-level 300 dpi is tuned for body prose)
  2. OCR the crop with --psm 11 (sparse text), which suits scattered node
     labels far better than the full-page mode --psm 3
  3. normalise, then split into candidate words of >= 4 characters
  4. a word is SURPLUS when it appears nowhere in the page's own text layer and
     nowhere in the text of the section the region belongs to

Reporting surplus at word level rather than string level is deliberate: an
edit-distance figure would be dominated by OCR noise on graphical strokes,
whereas a word either does or does not occur in the reference text.

Read-only. Writes one JSON report. Temp renders go under the project, never
/tmp: the sandbox denies the tesseract child process access to /tmp, which is
what made an earlier probe of mine report a spurious 100% CER.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import unicodedata
from pathlib import Path

import pymupdf

SANDBOX = Path(__file__).resolve().parents[2]
CORPUS = SANDBOX / "corpus"
PAGES = SANDBOX / "datasets_pages"
SECTIONS = SANDBOX / "datasets_sections"
OUT = CORPUS / "reports" / "REGION_OCR_SURPLUS_PROBE.json"
WORK = CORPUS / ".ocr_work"

MIN_WORD_CHARS = 4


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def fold(text: str) -> str:
    """Accent- and case-insensitive form, so a diacritic slip is not counted as
    new information."""
    s = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    raw = re.findall(r"[0-9A-Za-zÀ-ỹ]+", norm(text))
    return [w for w in raw if len(w) >= MIN_WORD_CHARS]


def ocr_image(path: Path, lang: str, psm: str) -> str:
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", lang, "--psm", psm],
        capture_output=True,
    )
    return proc.stdout.decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--lang", default="vie+eng")
    ap.add_argument("--psm", default="11")
    ap.add_argument("--pad-pt", type=float, default=4.0,
                    help="expand each region rect by this many points before rendering")
    ap.add_argument("--limit", type=int, default=0, help="stop after N regions")
    ap.add_argument("--emit", action="store_true", help="write the JSON report")
    args = ap.parse_args()

    WORK.mkdir(exist_ok=True)
    page_manifest = json.loads((PAGES / "MANIFEST.json").read_text("utf-8"))

    # Section text keyed by (doc_id, page), so a word already present in the
    # surrounding section prose is not called surplus either.
    section_by_page: dict[tuple[str, int], str] = {}
    for unit_path in SECTIONS.glob("*/*/unit.json"):
        unit = json.loads(unit_path.read_text("utf-8"))
        body = fold((unit_path.parent / unit["text_file"]).read_text("utf-8"))
        for page in unit["region_pages"]:
            key = (unit["doc_id"], page)
            section_by_page[key] = section_by_page.get(key, "") + " " + body

    rows: list[dict] = []
    t0 = time.time()

    for doc in page_manifest["docs"]:
        if not doc["units"]:
            continue
        doc_json = json.loads((PAGES / doc["doc_id"] / "doc.json").read_text("utf-8"))
        pdf_path = CORPUS / doc["source_pdf"]
        pdf = pymupdf.open(pdf_path)

        for unit in doc_json["unit_records"]:
            if args.limit and len(rows) >= args.limit:
                break
            page_no = unit["page"]
            page = pdf[page_no - 1]
            reference = fold(page.get_text()) + " " + section_by_page.get(
                (doc["doc_id"], page_no), "")

            for index, region in enumerate(unit["regions"], start=1):
                if args.limit and len(rows) >= args.limit:
                    break
                x0, y0, x1, y1 = region["rect_pt"]
                rect = pymupdf.Rect(x0 - args.pad_pt, y0 - args.pad_pt,
                                    x1 + args.pad_pt, y1 + args.pad_pt) & page.rect
                if rect.is_empty or rect.width < 8 or rect.height < 8:
                    continue
                crop = WORK / f"{doc['doc_id']}_p{page_no:04d}_r{index}.png"
                page.get_pixmap(dpi=args.dpi, clip=rect).save(crop)
                text = ocr_image(crop, args.lang, args.psm)
                crop.unlink(missing_ok=True)

                found = words(text)
                extra: dict[str, str] = {}
                for w in found:
                    f = fold(w)
                    if f not in reference:
                        extra.setdefault(f, w)
                rows.append({
                    "doc_id": doc["doc_id"],
                    "page": page_no,
                    "region_index": index,
                    "region_kind": region["kind"],
                    "region_w_pt": round(x1 - x0, 1),
                    "region_h_pt": round(y1 - y0, 1),
                    "ocr_words": len(found),
                    "surplus_words": len(extra),
                    "surplus_sample": list(extra.values())[:12],
                })
        pdf.close()
        if args.limit and len(rows) >= args.limit:
            break

    elapsed = time.time() - t0
    with_surplus = [r for r in rows if r["surplus_words"] > 0]
    by_kind: dict[str, dict] = {}
    for r in rows:
        k = by_kind.setdefault(r["region_kind"],
                               {"regions": 0, "with_surplus": 0, "surplus_words": 0})
        k["regions"] += 1
        k["with_surplus"] += 1 if r["surplus_words"] else 0
        k["surplus_words"] += r["surplus_words"]

    print(f"regions probed          {len(rows)}")
    print(f"regions with surplus    {len(with_surplus)}")
    print(f"surplus words total     {sum(r['surplus_words'] for r in rows)}")
    print(f"seconds                 {elapsed:.0f}  "
          f"({elapsed / max(1, len(rows)):.2f}/region)")
    print()
    print("by region kind")
    for kind, k in sorted(by_kind.items()):
        share = k["with_surplus"] / k["regions"] if k["regions"] else 0
        print(f"  {kind:10s} regions={k['regions']:4d} "
              f"with_surplus={k['with_surplus']:4d} ({share:.0%})  "
              f"words={k['surplus_words']}")
    print()
    print("top regions by surplus")
    for r in sorted(rows, key=lambda r: -r["surplus_words"])[:15]:
        print(f"  {r['doc_id'][:28]:28s} p{r['page']:<5d} {r['region_kind']:8s} "
              f"+{r['surplus_words']:3d}  {', '.join(r['surplus_sample'][:6])}")

    if args.emit:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "schema": "ecm-tqag.region-ocr-surplus-probe.v1",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "question": ("Do figure regions carry lettering absent from the page "
                         "text layer and from the surrounding section prose?"),
            "why": ("Direction A keeps the text layer as the primary source and "
                    "applies OCR only to figure regions. This measures whether "
                    "that adds information, which is also the precondition for a "
                    "question to genuinely require the image."),
            "method": {
                "render_dpi": args.dpi,
                "engine": f"tesseract {args.lang} --psm {args.psm}",
                "region_padding_pt": args.pad_pt,
                "word_rule": f">= {MIN_WORD_CHARS} chars, accent- and case-folded",
                "reference": ("the page's own text layer plus the full text of the "
                              "section the region was assigned to"),
                "why_words_not_edit_distance": (
                    "an edit distance over a figure crop is dominated by OCR noise "
                    "on graphical strokes; a word either occurs in the reference "
                    "text or it does not"),
            },
            "totals": {
                "regions_probed": len(rows),
                "regions_with_surplus": len(with_surplus),
                "surplus_words_total": sum(r["surplus_words"] for r in rows),
                "seconds": round(elapsed, 1),
            },
            "by_region_kind": by_kind,
            "regions": rows,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print()
        print(f"wrote {OUT.relative_to(SANDBOX)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
