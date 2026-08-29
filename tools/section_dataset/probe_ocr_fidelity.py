#!/usr/bin/env python3
"""Measure OCR fidelity against the PDF text layer, on this corpus.

Why this exists: the owner asked to rebuild the dataset "from OCR". Whether that
is an improvement or a regression is an empirical question about THESE files, not
a question about OCR leaderboards. Every one of the 26 textbooks is born-digital
(Adobe InDesign / Acrobat / Word producers, embedded fonts), so the text layer is
what the typesetter emitted. It is the reference, and OCR is the hypothesis.

Metric: character error rate of OCR against the page text layer, plus a
diacritic-retention rate, since Vietnamese meaning lives in the tone marks and a
CER can look tolerable while every dấu is gone.

Sampling: unit pages only (the pages the dataset is actually built from), with a
text layer over --min-ref chars so the reference is meaningful.

IMPORTANT: renders go to a temp dir INSIDE the project. A child process here
cannot open /tmp, which silently yields empty OCR and a fake 100% CER.

Read-only apart from its own temp renders and its report.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import pymupdf

SANDBOX = Path(__file__).resolve().parents[2]
CORPUS = SANDBOX / "corpus"
PAGE_MANIFEST = SANDBOX / "datasets_pages/MANIFEST.json"
TMP = CORPUS / ".ocr_fidelity_tmp"
REPORT = CORPUS / "reports/OCR_FIDELITY_PROBE.json"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def cer(ref: str, hyp: str) -> float | None:
    """Levenshtein distance / len(ref), rolling row."""
    if not ref:
        return None
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(ref)


def accented(text: str) -> int:
    """Count characters that carry a Vietnamese diacritic."""
    n = 0
    for ch in text:
        if not ch.isalpha():
            continue
        if unicodedata.normalize("NFD", ch) != ch:
            n += 1
    return n


def ocr_png(png: Path, lang: str, psm: int) -> str:
    proc = subprocess.run(
        ["tesseract", str(png), "stdout", "-l", lang, "--psm", str(psm)],
        capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:300]
        raise SystemExit(f"tesseract failed on {png}: {err}")
    return proc.stdout.decode("utf-8", "replace")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", type=int, default=24)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang", default="vie+eng")
    ap.add_argument("--psm", type=int, default=3)
    ap.add_argument("--min-ref", type=int, default=800)
    ap.add_argument("--seed", type=int, default=20260829)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(PAGE_MANIFEST.read_text("utf-8"))
    candidates = [(d["doc_id"], d["source_pdf"], p)
                  for d in manifest["docs"] for p in d["unit_pages"]]
    random.Random(args.seed).shuffle(candidates)

    TMP.mkdir(exist_ok=True)
    rows: list[dict] = []
    t_total = 0.0
    skipped_thin = 0

    try:
        for doc_id, src, page_no in candidates:
            if len(rows) >= args.pages:
                break
            doc = pymupdf.open(CORPUS / src)
            page = doc[page_no - 1]
            ref = norm(page.get_text())
            if len(ref) < args.min_ref:
                skipped_thin += 1
                doc.close()
                continue
            png = TMP / f"{doc_id}_p{page_no:04d}.png"
            page.get_pixmap(dpi=args.dpi).save(png)
            t0 = time.time()
            hyp = norm(ocr_png(png, args.lang, args.psm))
            dt = time.time() - t0
            t_total += dt
            png.unlink()
            doc.close()

            ref_acc, hyp_acc = accented(ref), accented(hyp)
            rows.append({
                "doc_id": doc_id,
                "page": page_no,
                "ref_chars": len(ref),
                "ocr_chars": len(hyp),
                "cer": round(cer(ref, hyp), 4),
                "ref_accented": ref_acc,
                "ocr_accented": hyp_acc,
                "diacritic_retention": round(hyp_acc / ref_acc, 4) if ref_acc else None,
                "ocr_seconds": round(dt, 2),
            })
            r = rows[-1]
            print(f"  {doc_id[:30]:30s} p{page_no:<5d} ref={r['ref_chars']:5d} "
                  f"ocr={r['ocr_chars']:5d} CER={r['cer']*100:6.2f}%  "
                  f"dấu {ref_acc:4d}->{hyp_acc:4d}  {dt:.1f}s", flush=True)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

    if not rows:
        raise SystemExit("no page had a text layer above --min-ref")

    cers = sorted(r["cer"] for r in rows)
    ret = [r["diacritic_retention"] for r in rows if r["diacritic_retention"] is not None]
    mid = cers[len(cers) // 2]
    summary = {
        "pages_measured": len(rows),
        "pages_skipped_thin_text_layer": skipped_thin,
        "cer_median": round(mid, 4),
        "cer_mean": round(sum(cers) / len(cers), 4),
        "cer_best": cers[0],
        "cer_worst": cers[-1],
        "diacritic_retention_median": round(sorted(ret)[len(ret) // 2], 4),
        "seconds_per_page_mean": round(t_total / len(rows), 2),
        "dpi": args.dpi,
        "engine": f"tesseract {args.lang} --psm {args.psm}",
    }

    print()
    print("=" * 68)
    for k, v in summary.items():
        print(f"  {k:34s} {v}")
    print("=" * 68)

    if args.emit:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({
            "schema": "ecm-tqag.ocr-fidelity-probe.v1",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "question": ("Would rebuilding the dataset text from OCR improve or "
                         "degrade fidelity on this corpus?"),
            "why_the_text_layer_is_the_reference": (
                "All 26 sources are born-digital: producers are Adobe InDesign, "
                "Adobe Acrobat and Microsoft Word, and every file embeds fonts. "
                "The text layer is the typesetter's own output, so OCR of a "
                "render of that text can at best re-derive it."),
            "method": {
                "sampling": "unit pages drawn at random from datasets_pages/MANIFEST.json",
                "seed": args.seed,
                "min_reference_chars": args.min_ref,
                "render_dpi": args.dpi,
                "engine": summary["engine"],
                "metric": "character error rate vs the page text layer, NFC normalised, whitespace collapsed",
                "diacritic_metric": "count of characters whose NFD differs from NFC, i.e. carrying a Vietnamese tone or vowel mark",
                "note_on_tmp": ("renders are written inside the project; a child "
                                "process here cannot open /tmp, which silently "
                                "produces empty OCR and a spurious 100% CER"),
            },
            "summary": summary,
            "per_page": rows,
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {REPORT.relative_to(SANDBOX)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
