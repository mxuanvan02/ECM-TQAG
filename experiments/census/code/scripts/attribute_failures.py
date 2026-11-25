#!/usr/bin/env python3
"""Trace every non-reproducing quotation back to the channel it came from.

This is the paper's central mechanism claim: the contract removes quotations of
text rendered INSIDE the page image, which the text layer T_c does not contain.
The claim is only meaningful if each failed quotation is attributed to a source
channel rather than counted as an undifferentiated failure.

Two decisive splits, both offline, no paid call:

  1. T_c SCOPING. Search the quotation in the target page AND its +/-2
     neighbours in the source PDF text layer (pdftotext -layout, the same
     extractor the frame used). A hit on a neighbour would mean the failure is
     an artefact of the single-page window, not a model failure.

  2. CHANNEL. OCR the chunk's own figure crops (tesseract, vie+eng) and search
     the quotation there. A hit means the model quoted image-rendered text.

Case-only rejections are separated out: the content IS present in T_c and the
rejection turns on capitalisation alone. Those are instrument false rejects, and
the gate is NOT modified to accommodate them; they are reported as a
counterfactual only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.gate import classify_quote, normalize_text  # noqa: E402

CENSUS = ROOT / "runs" / "census_4arm_framec_20260824T120000Z"
MANIFEST = ROOT / "dataset_framec" / "dataset_manifest_rule4_20260816T105100Z.json"
CORPUS = ROOT.parent / "user_data" / "frameC_acquisition"
ARMS = ("ecm_full", "gate_disclosed", "direct", "structured_no_contract")
NEIGHBOUR_WINDOW = 2


def fold(value: str) -> str:
    return normalize_text(value).casefold()


def source_pdfs() -> dict[str, Path]:
    """doc_id -> source PDF. Frame C doc ids are filename prefixes."""
    out: dict[str, Path] = {}
    for pdf in CORPUS.rglob("*.pdf"):
        stem = pdf.stem
        for doc_id in ("P1_006", "P1_008", "P2_006", "P2_007",
                       "P3_002", "P3_003", "P4_001", "R12_P1_03", "R15_P1_03"):
            if stem == doc_id or stem.startswith(doc_id + "_"):
                # Prefer a non-quarantine copy when both exist.
                if doc_id not in out or "quarantine" in str(out[doc_id]):
                    out[doc_id] = pdf
    return out


def page_text(pdf: Path, page: int) -> str:
    try:
        res = subprocess.run(
            ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
            capture_output=True, text=True, timeout=60)
        return res.stdout if res.returncode == 0 else ""
    except Exception:
        return ""


def ocr(path: Path) -> str:
    try:
        res = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "vie+eng"],
            capture_output=True, text=True, timeout=120)
        return res.stdout if res.returncode == 0 else ""
    except Exception:
        return ""


def overlap(quote: str, text: str) -> float:
    """Token overlap, used only to report how close an unresolved quote came."""
    q = set(fold(quote).split())
    t = set(fold(text).split())
    return round(len(q & t) / len(q), 4) if q else 0.0


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    packages = {p["chunk_id"]: p for p in manifest["packages"]}
    pdfs = source_pdfs()

    failures = []
    for path in sorted((CENSUS / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        tid = rec.get("task_id", "")
        if not tid.startswith("generation::") or rec.get("status") != "TERMINAL_FAILURE":
            continue
        parts = tid.split("::")
        failures.append({
            "chunk_id": "::".join(parts[2:5]),
            "arm": parts[5],
            "reason": str(rec.get("reason") or ""),
        })

    # Recover each failed response object from the sealed transport sidecars.
    ledger = CENSUS / "state" / "transport" / "CALL_LEDGER.jsonl"
    bodies: dict[tuple[str, str], dict] = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("record_type") != "CALL_TERMINAL" or row.get("phase") != "generation":
            continue
        if row.get("outcome") != "OK":
            continue
        sidecar = ledger.parent / (row.get("response_path") or "")
        if not sidecar.exists():
            continue
        try:
            body = json.loads(sidecar.read_text(encoding="utf-8"))
            content = body["choices"][0]["message"]["content"]
        except Exception:
            continue
        bodies[(row.get("chunk_id", ""), row.get("arm", ""))] = {"content": content}

    ocr_cache: dict[str, str] = {}
    rows = []
    for f in failures:
        key = (f["chunk_id"], f["arm"])
        row = dict(f)
        body = bodies.get(key)
        if "QUOTE_NON_VERBATIM" not in f["reason"]:
            row["category"] = ("malformed_no_single_json_object"
                               if "JSON_OBJECT" in f["reason"]
                               else "schema_or_field_violation")
            rows.append(row)
            continue

        # Extract the declared quotation from the raw response.
        quote = ""
        if body:
            m = re.search(r'"text_evidence_quote"\s*:\s*"((?:[^"\\]|\\.)*)"', body["content"])
            if m:
                try:
                    quote = json.loads('"' + m.group(1) + '"')
                except Exception:
                    quote = m.group(1)
        row["quote_chars"] = len(quote)
        if not quote:
            row["category"] = "quote_unrecoverable"
            rows.append(row)
            continue

        pkg = packages[f["chunk_id"]]
        tc = pkg["evidence"]["text"]

        # Split 0: case-only rejection (content present, capitalisation differs).
        if fold(quote) in fold(tc):
            row["category"] = "case_only_false_reject"
            row["detail"] = "present in T_c under case folding"
            rows.append(row)
            continue

        # Split 1: T_c scoping. Search target page +/- NEIGHBOUR_WINDOW.
        doc_id = pkg["doc_id"]
        page = int(f["chunk_id"].rsplit("::p", 1)[1])
        found_on = None
        pdf = pdfs.get(doc_id)
        if pdf:
            for offset in range(-NEIGHBOUR_WINDOW, NEIGHBOUR_WINDOW + 1):
                if offset == 0:
                    continue
                target = page + offset
                if target < 1:
                    continue
                if fold(quote) in fold(page_text(pdf, target)):
                    found_on = target
                    break
        if found_on is not None:
            row["category"] = "neighbouring_page_scoping"
            row["detail"] = f"found on page {found_on}"
            rows.append(row)
            continue

        # Split 2: channel. OCR the chunk's own figure crops.
        best = 0.0
        hit = False
        for image in pkg["evidence"]["images"]:
            ipath = ROOT / image["path"]
            if not ipath.exists():
                continue
            if image["path"] not in ocr_cache:
                ocr_cache[image["path"]] = ocr(ipath)
            text = ocr_cache[image["path"]]
            if fold(quote) and fold(quote) in fold(text):
                hit = True
                break
            best = max(best, overlap(quote, text))
        if hit:
            row["category"] = "quotation_of_image_rendered_text"
        else:
            row["category"] = "unresolved"
            row["crop_ocr_overlap"] = best
        rows.append(row)

    by_cat: dict[str, dict[str, int]] = {}
    for row in rows:
        by_cat.setdefault(row["category"], {a: 0 for a in ARMS})
        by_cat[row["category"]][row["arm"]] += 1

    counterfactual = {}
    for arm in ARMS:
        base = sum(1 for p in sorted((CENSUS / "state" / "tasks").glob("*.json"))
                   for r in [json.loads(p.read_text(encoding="utf-8"))]
                   if r.get("task_id", "").startswith("generation::")
                   and r.get("task_id", "").split("::")[5] == arm
                   and r.get("status") == "COMPLETE" and r.get("gates_passed"))
        extra = sum(1 for row in rows
                    if row["arm"] == arm and row["category"] == "case_only_false_reject")
        counterfactual[arm] = {"admitted": base, "if_case_folded": base + extra}

    report = {
        "schema": "ecm-tqag.failure-attribution.v2-4arm",
        "run": CENSUS.name,
        "paid_calls_by_this_audit": 0,
        "gate_modified": False,
        "method": [
            "Failed responses recovered from sealed transport sidecars.",
            "Split 0: quotation present in T_c under case folding -> instrument false reject.",
            f"Split 1: quotation searched on the target page +/-{NEIGHBOUR_WINDOW} "
            "neighbours of the source PDF text layer (pdftotext -layout) -> tests T_c scoping.",
            "Split 2: quotation searched in tesseract (vie+eng) OCR of the chunk's own "
            "figure crops -> tests the image channel.",
        ],
        "totals": {k: sum(v.values()) for k, v in sorted(by_cat.items())},
        "by_category_and_arm": by_cat,
        "case_folding_counterfactual": counterfactual,
        "rows": sorted(rows, key=lambda r: (r["category"], r["arm"], r["chunk_id"])),
    }
    out = CENSUS / "FAILURE_ATTRIBUTION.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                     ensure_ascii=False, indent=1))
    print("\nwrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
