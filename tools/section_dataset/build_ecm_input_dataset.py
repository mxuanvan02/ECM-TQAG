#!/usr/bin/env python3
"""Build the direct ECM input dataset from the section-level units.

Direction A, as decided by the owner: the PDF text layer stays the primary
source and is never overwritten. OCR contributes a SEPARATE channel covering
the figure regions only (`figure_text.json`, written by
corpus/scripts/augment_figure_text.py).

Package shape follows the sealed frame-C manifest
(`ecm-tqag.multimodal-inputs.v4-work24`) so the existing runner can consume it
without modification, plus one added evidence key:

    evidence.figure_text = {words, surplus_words, gate}

`figure_text` is declared NOT quotable as prose. The verbatim-quote gate reads
`evidence.text` only, exactly as in the sealed frame; at confidence 90 about one
figure word in ten is still an OCR slip on graphical strokes, so admitting them
to the quote gate would let a hallucinated quote pass.

Two frames are emitted, and the difference is the frozen rule-3 reading:

  frame_d_strict   embedded rasters >= 203 px only, the frozen operationalisation
  frame_d_vector   any crop on disk >= 203 px, the literal text of rule 3

Neither is authorised for a paid run by this script. Frame D requires its own
pre-registered determination before any model call; see
corpus/reports/SECTION_FRAME_DETERMINATION.json §binding_constraint.

Read-only with respect to every sealed input. Writes only under --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import unicodedata
from collections import Counter
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
CORPUS = SANDBOX / "corpus"
ROOTS = (SANDBOX / "datasets_sections", SANDBOX / "datasets_sections_other")
ELIGIBLE = SANDBOX / "datasets_sections/ELIGIBLE_UNITS.json"
SEALED = SANDBOX / "experiment/dataset_framec/dataset_manifest_rule4_20260816T105100Z.json"
INDEX = CORPUS / "DATASET_INDEX.json"
DETERMINATION = CORPUS / "reports/SECTION_FRAME_DETERMINATION.json"
RIGHTS = CORPUS / "reports/SECTION_DATASET_RIGHTS_RECONCILIATION.json"

CROP_FLOOR_PX = 203


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def find_unit(unit_id: str) -> tuple[Path, dict] | None:
    doc, sec = unit_id.split("::")
    for root in ROOTS:
        path = root / doc / sec / "unit.json"
        if path.exists():
            return path.parent, json.loads(path.read_text("utf-8"))
    return None


def qualifying(unit: dict, *, embedded_only: bool) -> list[dict]:
    out = []
    for img in unit.get("images", []):
        if embedded_only and img.get("source") != "embedded_raster":
            continue
        if min(img["width"], img["height"]) >= CROP_FLOOR_PX:
            out.append(img)
    return out


def sealed_pairs() -> set[tuple[str, int]]:
    sealed = json.loads(SEALED.read_text("utf-8"))
    index = json.loads(INDEX.read_text("utf-8"))
    by_doc: dict[str, str] = {}
    for rec in index["files"]:
        for did in rec.get("frame_doc_ids") or []:
            by_doc[did] = rec["sha256"]
    pairs = set()
    for pkg in sealed["packages"]:
        ds = pkg["evidence"]["document_structure"]
        sha = by_doc.get(ds["source_id"])
        if sha:
            pairs.add((sha, ds["page"]))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="experiment/dataset_sections")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    eligible = json.loads(ELIGIBLE.read_text("utf-8"))
    ids = list(eligible["unit_ids"])
    seen = sealed_pairs()
    out_root = SANDBOX / args.out

    frames = {
        "frame_d_strict": {"embedded_only": True,
                           "rule3": "embedded rasters only, min-dim >= 203 px "
                                    "(the frozen operationalisation)"},
        "frame_d_vector": {"embedded_only": False,
                           "rule3": "any crop on disk, min-dim >= 203 px "
                                    "(the literal text of rule 3)"},
    }

    built: dict[str, dict] = {}
    for frame_name, spec in frames.items():
        packages, dropped = [], []
        for unit_id in ids:
            found = find_unit(unit_id)
            if found is None:
                dropped.append({"unit_id": unit_id, "reason": "unit_record_missing"})
                continue
            udir, unit = found

            crops = qualifying(unit, embedded_only=spec["embedded_only"])
            if not crops:
                dropped.append({"unit_id": unit_id, "reason": "rule3_no_qualifying_crop"})
                continue
            if not unit["rule4_text_sufficient"]:
                dropped.append({"unit_id": unit_id, "reason": "rule4_insufficient_text"})
                continue
            pages = sorted({img["page"] for img in crops
                            if img.get("page") is not None} or set(unit["region_pages"]))
            reused = [p for p in pages if (unit["source_sha256"], p) in seen]
            if reused:
                dropped.append({"unit_id": unit_id,
                                "reason": "addendum_s7_page_already_in_sealed_frame",
                                "pages": reused})
                continue

            text = norm((udir / unit["text_file"]).read_text("utf-8"))
            fig_path = udir / "figure_text.json"
            figure_text = None
            if fig_path.exists():
                fig = json.loads(fig_path.read_text("utf-8"))
                figure_text = {
                    "words": fig["figure_words"],
                    "surplus_words": fig["surplus_words"],
                    "gate": fig["gate"],
                    "not_quotable_as_prose": fig["not_quotable_as_prose"],
                }

            images = []
            for order, img in enumerate(sorted(crops, key=lambda i: i["path"]), start=1):
                rel = f"{args.out.split('/')[-1]}/images/{unit['doc_id']}_{Path(img['path']).name}"
                if args.apply:
                    dest = out_root / "images" / f"{unit['doc_id']}_{Path(img['path']).name}"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(udir / img["path"], dest)
                images.append({
                    "path": rel, "declared_order": order,
                    "width": img["width"], "height": img["height"],
                    "bytes": img["bytes"], "sha256": img["sha256"],
                    "source": img["source"],
                })

            sec = unit["section"]
            evidence = {
                "document_structure": {
                    "source_id": unit["doc_id"],
                    "source_sha256": unit["source_sha256"],
                    "document_type": "giao_trinh",
                    "granularity": "section",
                    "section_label": sec["label"],
                    "section_title": sec["title"],
                    "ancestor_path": sec["ancestor_path"],
                    "pages": pages,
                    "section_pages": [sec["start_page"], sec["end_page"]],
                    "figure_cues": unit["figure_cues"],
                },
                "images": images,
                "text": text,
            }
            if figure_text is not None:
                evidence["figure_text"] = figure_text

            packages.append({
                "chunk_id": f"frameD::{unit_id}",
                "item_id": f"frameD::{unit_id}",
                "doc_id": unit["doc_id"],
                "condition": "TLV",
                "split": "test",
                "question_type": unit["question_type"],
                "evidence": evidence,
            })

        built[frame_name] = {"packages": packages, "dropped": dropped, **spec}
        n_fig = sum(1 for p in packages if "figure_text" in p["evidence"])
        surplus = sum(len(p["evidence"].get("figure_text", {}).get("surplus_words", []))
                      for p in packages)
        print(f"{frame_name:16s} chunks={len(packages):3d}  "
              f"with_figure_text={n_fig:3d}  surplus_words={surplus:4d}  "
              f"dropped={len(dropped)}")
        print(f"{'':16s} reasons: "
              f"{dict(Counter(d['reason'] for d in dropped))}")

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 0

    manifest = {
        "schema": "ecm-tqag.multimodal-inputs.v5-sections",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "what_this_is": (
            "Direct ECM input built from the section-level multimodal dataset. "
            "Package shape follows the sealed frame-C manifest so the existing "
            "runner consumes it unmodified, plus evidence.figure_text."
        ),
        "scope": "law textbooks (giáo trình luật) held by the HUL catalogue",
        "text_source": {
            "primary": "PDF text layer, layout-preserving, never overwritten",
            "why_not_rebuilt_from_ocr": (
                "All 26 sources are born-digital (Adobe InDesign / Acrobat / Word "
                "producers) and 86% of figure-bearing pages carry a real text "
                "layer. Measured on 24 sampled pages, tesseract vie+eng reaches "
                "median CER 1.89% against that layer, so rebuilding from OCR "
                "would replace the typesetter's own output with a lossy copy. "
                "Measurement: corpus/reports/OCR_FIDELITY_PROBE.json"
            ),
            "ocr_role": (
                "figure regions only, as a separate channel; see "
                "corpus/reports/FIGURE_TEXT_AUGMENTATION.json"
            ),
        },
        "figure_text_contract": {
            "quotable_as_prose": False,
            "why": ("At the chosen confidence gate roughly one word in ten is "
                    "still an OCR slip on graphical strokes. The verbatim-quote "
                    "gate must read evidence.text only, as the sealed frame does."),
            "gate_calibration": "corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json",
        },
        "authorisation": {
            "paid_run_authorised": False,
            "why": ("Frame D is not pre-registered. ROUND4_NECESSITY_ADDENDUM.md "
                    "§4 fixes n before the first call and forbids frame extension "
                    "after results were seen; the vector reading of rule 3 "
                    "additionally needs its own determination record written "
                    "before any call."),
            "floor": 40,
            "target": 46,
        },
        "inputs": {
            "eligible_units": "datasets_sections/ELIGIBLE_UNITS.json",
            "rights_ledger": str(RIGHTS.relative_to(SANDBOX)),
            "rights_ledger_sha256": sha256_file(RIGHTS),
            "determination": str(DETERMINATION.relative_to(SANDBOX)),
            "determination_sha256": sha256_file(DETERMINATION),
            "sealed_frame_c": str(SEALED.relative_to(SANDBOX)),
            "sealed_frame_c_sha256": sha256_file(SEALED),
        },
        "redistribution": (
            "Source text and figure crops are copyright of the University of Law, "
            "Hue University and are held for internal research only. This manifest "
            "and the images/ directory must NOT be published. The public release "
            "carries the metadata-only companion instead."
        ),
        "frames": {},
    }
    for name, data in built.items():
        pkgs = data["packages"]
        manifest["frames"][name] = {
            "rule3_reading": data["rule3"],
            "chunk_count": len(pkgs),
            "reaches_floor": len(pkgs) >= 40,
            "question_types": dict(Counter(p["question_type"] for p in pkgs)),
            "documents": len({p["doc_id"] for p in pkgs}),
            "chunks_with_figure_text": sum(1 for p in pkgs if "figure_text" in p["evidence"]),
            "dropped": data["dropped"],
            "packages": pkgs,
        }

    out_root.mkdir(parents=True, exist_ok=True)
    dest = out_root / "dataset_manifest.json"
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(f"\nwrote {dest.relative_to(SANDBOX)}")
    print(f"sha256 {sha256_file(dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
