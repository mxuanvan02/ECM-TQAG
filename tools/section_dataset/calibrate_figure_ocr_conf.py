#!/usr/bin/env python3
"""Calibrate the per-word confidence gate for figure-region OCR.

The surplus probe (reports/REGION_OCR_SURPLUS_PROBE.json) found 808 words inside
figure regions that are absent from the page text layer, but the sample mixes two
populations:

  genuine lettering   'PROCEEDINGS', 'Delimitation', 'Mahajanapadas'
  stroke noise        'EuBEIioTtI', 'rncaltvw', 'trademays'

Feeding noise into the ECM evidence bundle would corrupt the verbatim-quote gate,
so the channel needs a gate. Tesseract TSV reports a per-word confidence, and
this script measures how well that confidence separates the two populations.

Ground truth here is deliberately weak but independent of confidence: a word is
called PLAUSIBLE when it is a Vietnamese or English dictionary form, a number, or
an all-caps acronym; NOISE otherwise. That misclassifies rare proper nouns, so
the printed report shows the raw distribution as well as the derived threshold.

Read-only. Writes one JSON report when --emit is given.
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
WORK = CORPUS / ".ocrwork"
OUT = CORPUS / "reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json"

SYSTEM_WORDS = Path("/usr/share/dict/words")
MIN_WORD_CHARS = 3


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", t or "")).strip()


def fold(t: str) -> str:
    s = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def load_lexicon() -> set[str]:
    """English dictionary + every word the corpus's own text layers contain.

    The corpus lexicon is the important half: it supplies Vietnamese vocabulary
    and the domain's proper nouns without needing a Vietnamese word list.
    """
    lex: set[str] = set()
    if SYSTEM_WORDS.is_file():
        for line in SYSTEM_WORDS.read_text(errors="replace").splitlines():
            w = fold(line.strip())
            if len(w) >= MIN_WORD_CHARS:
                lex.add(w)
    for unit_path in SECTIONS.glob("*/*/unit.json"):
        unit = json.loads(unit_path.read_text("utf-8"))
        body = (unit_path.parent / unit["text_file"]).read_text("utf-8")
        for w in re.findall(r"[0-9A-Za-zÀ-ỹ]+", norm(body)):
            if len(w) >= MIN_WORD_CHARS:
                lex.add(fold(w))
    return lex


def tsv_words(path: Path, lang: str, psm: str) -> list[dict]:
    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", lang, "--psm", psm, "tsv"],
        capture_output=True,
    )
    rows = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        text = parts[11].strip()
        if not text:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        if conf < 0:
            continue
        rows.append({"text": text, "conf": conf})
    return rows


def plausible(word: str, lex: set[str]) -> bool:
    f = fold(word)
    if re.fullmatch(r"[0-9]{2,4}", word):          # a year or a figure number
        return True
    if f in lex:
        return True
    if word.isupper() and MIN_WORD_CHARS <= len(word) <= 8 and word.isalpha():
        return True                                # acronym, e.g. HDLD, WTO
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--lang", default="vie+eng")
    ap.add_argument("--psm", default="11")
    ap.add_argument("--pad-pt", type=float, default=4.0)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    WORK.mkdir(exist_ok=True)
    lex = load_lexicon()
    print(f"lexicon size {len(lex)} (system dict + corpus text layers)")

    surplus = json.loads((CORPUS / "reports/REGION_OCR_SURPLUS_PROBE.json").read_text("utf-8"))
    # Only regions the probe found surplus in: that is where the gate matters.
    targets = [r for r in surplus["regions"] if r["surplus_words"] > 0]
    print(f"regions to re-OCR with confidence {len(targets)}")

    page_manifest = json.loads((PAGES / "MANIFEST.json").read_text("utf-8"))
    src_by_doc = {d["doc_id"]: d["source_pdf"] for d in page_manifest["docs"]}

    section_by_page: dict[tuple[str, int], str] = {}
    for unit_path in SECTIONS.glob("*/*/unit.json"):
        unit = json.loads(unit_path.read_text("utf-8"))
        body = fold((unit_path.parent / unit["text_file"]).read_text("utf-8"))
        for page in unit["region_pages"]:
            key = (unit["doc_id"], page)
            section_by_page[key] = section_by_page.get(key, "") + " " + body

    words_out: list[dict] = []
    t0 = time.time()
    open_pdf: dict[str, pymupdf.Document] = {}

    for r in targets:
        doc_id, page_no = r["doc_id"], r["page"]
        if doc_id not in open_pdf:
            open_pdf[doc_id] = pymupdf.open(CORPUS / src_by_doc[doc_id])
        pdf = open_pdf[doc_id]
        page = pdf[page_no - 1]
        reference = fold(page.get_text()) + " " + section_by_page.get((doc_id, page_no), "")

        doc_json = json.loads((PAGES / doc_id / "doc.json").read_text("utf-8"))
        unit = next((u for u in doc_json["unit_records"] if u["page"] == page_no), None)
        if unit is None or r["region_index"] > len(unit["regions"]):
            continue
        region = unit["regions"][r["region_index"] - 1]
        x0, y0, x1, y1 = region["rect_pt"]
        rect = pymupdf.Rect(x0 - args.pad_pt, y0 - args.pad_pt,
                            x1 + args.pad_pt, y1 + args.pad_pt) & page.rect
        if rect.is_empty or rect.width < 8 or rect.height < 8:
            continue
        crop = WORK / f"cal_{doc_id}_p{page_no:04d}_r{r['region_index']}.png"
        page.get_pixmap(dpi=args.dpi, clip=rect).save(crop)
        for w in tsv_words(crop, args.lang, args.psm):
            text = w["text"]
            if len(re.sub(r"[^0-9A-Za-zÀ-ỹ]", "", text)) < MIN_WORD_CHARS:
                continue
            if fold(text) in reference:
                continue                            # already in the text layer
            words_out.append({
                "doc_id": doc_id, "page": page_no,
                "region_kind": r["region_kind"],
                "word": text, "conf": round(w["conf"], 1),
                "plausible": plausible(text, lex),
            })
        crop.unlink(missing_ok=True)

    for pdf in open_pdf.values():
        pdf.close()
    elapsed = time.time() - t0

    total = len(words_out)
    plaus = sum(1 for w in words_out if w["plausible"])
    print(f"\nsurplus words with confidence  {total}")
    print(f"  dictionary-plausible         {plaus} ({plaus/max(1,total):.0%})")
    print(f"  implausible (noise-like)     {total-plaus}")
    print(f"seconds {elapsed:.0f}")

    print("\nconfidence distribution")
    print(f"  {'band':>10s} {'n':>5s} {'plausible':>10s} {'share':>7s}")
    bands = [(0, 40), (40, 50), (50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]
    band_rows = []
    for lo, hi in bands:
        sel = [w for w in words_out if lo <= w["conf"] < hi]
        if not sel:
            continue
        p = sum(1 for w in sel if w["plausible"])
        band_rows.append({"lo": lo, "hi": hi, "n": len(sel), "plausible": p,
                          "share": round(p / len(sel), 3)})
        print(f"  {lo:3d}-{hi-1:3d} {len(sel):9d} {p:10d} {p/len(sel):7.0%}")

    print("\nthreshold sweep (precision = share of kept words that are plausible)")
    print(f"  {'thr':>4s} {'kept':>6s} {'precision':>10s} {'recall_of_plausible':>20s}")
    sweep = []
    for thr in (0, 40, 50, 55, 60, 65, 70, 75, 80, 85, 90):
        kept = [w for w in words_out if w["conf"] >= thr]
        if not kept:
            continue
        p = sum(1 for w in kept if w["plausible"])
        prec = p / len(kept)
        rec = p / max(1, plaus)
        sweep.append({"threshold": thr, "kept": len(kept), "precision": round(prec, 3),
                      "recall_of_plausible": round(rec, 3)})
        print(f"  {thr:4d} {len(kept):6d} {prec:10.0%} {rec:20.0%}")

    # Pick the lowest threshold reaching 0.80 precision, so the channel is clean
    # enough to quote from while keeping as much lettering as possible.
    chosen = next((s["threshold"] for s in sweep if s["precision"] >= 0.80), 90)
    kept = [w for w in words_out if w["conf"] >= chosen]
    print(f"\nchosen threshold {chosen}: keeps {len(kept)} of {total} words "
          f"({len(kept)/max(1,total):.0%})")
    print("\nsample KEPT")
    for w in sorted(kept, key=lambda w: -w["conf"])[:14]:
        print(f"  {w['conf']:5.1f}  {w['word'][:34]:34s} {w['doc_id'][:22]} p{w['page']}")
    print("\nsample DROPPED")
    for w in sorted((w for w in words_out if w["conf"] < chosen),
                    key=lambda w: w["conf"])[:14]:
        print(f"  {w['conf']:5.1f}  {w['word'][:34]:34s} {w['doc_id'][:22]} p{w['page']}")

    if args.emit:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "schema": "ecm-tqag.figure-ocr-confidence-calibration.v1",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "question": ("At what per-word confidence does figure-region OCR stop "
                         "being dominated by stroke noise?"),
            "why": ("Direction A adds figure lettering as an extra evidence channel. "
                    "Unfiltered, that channel carries OCR noise on graphical strokes, "
                    "which would corrupt a verbatim-quote gate."),
            "method": {
                "engine": f"tesseract {args.lang} --psm {args.psm} tsv",
                "render_dpi": args.dpi,
                "region_padding_pt": args.pad_pt,
                "population": ("words inside a figure region that are absent from "
                               "both the page text layer and the section prose"),
                "weak_label": ("PLAUSIBLE = in the system English dictionary, or in "
                               "the lexicon built from this corpus's own text layers, "
                               "or a 2-4 digit number, or a 3-8 letter all-caps "
                               "acronym; NOISE otherwise"),
                "label_limitation": ("rare proper nouns absent from both lexicons are "
                                     "labelled NOISE, so precision is understated"),
                "lexicon_size": len(lex),
            },
            "totals": {"surplus_words": total, "plausible": plaus,
                       "implausible": total - plaus, "seconds": round(elapsed, 1)},
            "confidence_bands": band_rows,
            "threshold_sweep": sweep,
            "chosen_threshold": chosen,
            "chosen_rule": ("lowest threshold whose kept set is >= 80% "
                            "dictionary-plausible"),
            "kept_at_chosen": len(kept),
            "words": words_out,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {OUT.relative_to(SANDBOX)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
