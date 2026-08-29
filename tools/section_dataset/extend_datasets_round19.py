#!/usr/bin/env python3
"""Add the round-19 shelf textbooks to both dataset builds, additively.

The two builders (`corpus/build_multimodal_dataset.py`,
`corpus/scripts/build_section_dataset.py`) both `rmtree` their output and both
number documents positionally, by descending page count. Re-running either one
with six extra books would therefore

  1. destroy the existing build, and
  2. renumber every document: the 504-page new book sorts into slot 7, so the
     current T07 becomes T08, and every `unit_id` in ELIGIBLE_UNITS.json, the
     rights ledger and SECTION_FRAME_DETERMINATION.json would silently point at
     a different book.

This script instead drives the same detection code over the six new PDFs only,
pins their ids to the next free indices in staging order, and merges the results
into both manifests. Existing doc records and unit directories are never touched.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent
SANDBOX = CORPUS.parent

sys.path.insert(0, str(CORPUS))
sys.path.insert(0, str(HERE))
import build_multimodal_dataset as bmd  # noqa: E402
import build_section_dataset as bsd  # noqa: E402
import section_tree as st  # noqa: E402

PAGES_ROOT = SANDBOX / "datasets_pages"
SECTIONS_ROOT = SANDBOX / "datasets_sections"
STAGING_REPORT = CORPUS / "reports/round19_shelf_staging_fetch_20260829T183234Z.json"
CLASSIFICATION = CORPUS / "TEXTBOOK_CLASSIFICATION.json"
CACHE = bsd.CACHE

CONTEXT_WINDOW = bmd.CONTEXT_WINDOW
OCR_THRESHOLD = 200
MIN_SECTION_CHARS = bsd.MIN_SECTION_CHARS


def doc_id_for(index: int, staged_path: str) -> str:
    """Same shape as the builders' ids, but the index is pinned, not sorted."""
    import re
    name = Path(staged_path).stem
    name = re.sub(r"^(R\d+_\d+_|P\d_\d+_)", "", name)
    name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"T{index:02d}_{name[:56]}"


def build_page_units(pdf: Path, doc_id: str, doc: pymupdf.Document,
                     out_root: Path, *, apply: bool, tmp: Path,
                     totals: Counter) -> list[dict]:
    """One unit per page carrying a figure-like region. Mirrors bmd.main."""
    furniture = bmd.furniture_signatures(doc)
    units: list[dict] = []
    for page_number in range(1, doc.page_count + 1):
        page = doc[page_number - 1]
        regions = bmd.detect_regions(page, furniture)
        if not regions:
            continue
        totals["pages_with_regions"] += 1

        own_text = bmd.layout_text(pdf, page_number, page_number)
        text_source = "pdf_text_layer"
        if len(bmd.norm(own_text)) < OCR_THRESHOLD:
            if apply:
                ocr = bmd.ocr_page(pdf, page_number, tmp, "vie+eng")
                if len(bmd.norm(ocr)) > len(bmd.norm(own_text)):
                    own_text = ocr
                    text_source = "tesseract:vie+eng"
            else:
                text_source = "would_ocr:vie+eng"
            totals["pages_ocr"] += 1

        ok, reason = bmd.rule4_verdict(own_text)
        cues = bmd.figure_cues(own_text)
        qtype, qreason = bmd.assign_question_type(cues)
        kinds = Counter(r["kind"] for r in regions)

        unit_dir = out_root / doc_id / f"p{page_number:04d}"
        images: list[dict] = []
        page_render: dict | None = None
        if apply:
            unit_dir.mkdir(parents=True, exist_ok=True)
            (unit_dir / "text.txt").write_text(own_text, encoding="utf-8")
            first = max(1, page_number - CONTEXT_WINDOW)
            last = min(doc.page_count, page_number + CONTEXT_WINDOW)
            (unit_dir / "context.txt").write_text(
                bmd.layout_text(pdf, first, last), encoding="utf-8")
            page_render = bmd.render_page(page, unit_dir / "page.png")
            images.extend(bmd.extract_rasters(pdf, page_number, unit_dir,
                                              f"{doc_id}_p{page_number:04d}"))
            vector_index = 0
            for region in regions:
                if region["kind"] == "raster":
                    continue
                vector_index += 1
                images.append(bmd.render_region(
                    page, region["rect"], unit_dir / f"region_{vector_index}.png"))

        unit = {
            "unit_id": f"{doc_id}::p{page_number:04d}",
            "doc_id": doc_id,
            "page": page_number,
            "region_kinds": dict(kinds),
            "regions": [
                {"kind": r["kind"],
                 "rect_pt": [round(r["rect"].x0, 1), round(r["rect"].y0, 1),
                             round(r["rect"].x1, 1), round(r["rect"].y1, 1)]}
                for r in regions
            ],
            "text_source": text_source,
            "text_chars": len(bmd.norm(own_text)),
            "context_pages": list(range(max(1, page_number - CONTEXT_WINDOW),
                                        min(doc.page_count,
                                            page_number + CONTEXT_WINDOW) + 1)),
            "figure_cues": cues,
            "question_type": qtype,
            "question_type_reason": qreason,
            "rule4_text_sufficient": ok,
            "rule4_reason": reason,
            "has_embedded_raster": bool(kinds.get("raster")),
            "frame_c_rule3_eligible": None,
            "page_render": page_render,
            "images": images,
        }
        if apply:
            unit["frame_c_rule3_eligible"] = any(
                i["source"] == "embedded_raster" for i in images)
            (unit_dir / "unit.json").write_text(
                json.dumps(unit, ensure_ascii=False, indent=2), encoding="utf-8")
        units.append(unit)
        totals["units"] += 1
        for kind, n in kinds.items():
            totals[f"regions_{kind}"] += n
        if ok:
            totals["units_rule4_ok"] += 1
    return units


def build_section_units(pdf: Path, doc_id: str, doc: pymupdf.Document,
                        unit_pages: list[int], out_root: Path, *, apply: bool,
                        cache: dict, totals: Counter) -> tuple[list[dict], dict]:
    """One unit per section holding a figure-like region. Mirrors bsd.main."""
    if doc_id not in cache:
        cache[doc_id] = st.extract_headings(doc)
    info = cache[doc_id]
    sections = st.build_sections(info["headings"], doc.page_count)
    excluded = st.non_body_pages(doc, info)
    furniture = set(info.get("furniture", []))
    watermarks = set(info.get("watermarks", []))
    page_furniture = bmd.furniture_signatures(doc)

    text_cache: dict[int, str] = {}

    def text_of(idx: int) -> str:
        if idx not in text_cache:
            text_cache[idx] = st.section_text(doc, sections[idx], furniture, watermarks)
        return text_cache[idx]

    assigned: dict[int, list[dict]] = defaultdict(list)
    for page in unit_pages:
        regions = bmd.detect_regions(doc[page - 1], page_furniture)
        if page in excluded:
            totals["regions_dropped_non_body"] += len(regions)
            continue
        for region in regions:
            rect = region["rect"]
            idx = bsd.containing_section(sections, page, rect.y0, rect.y1)
            if idx is None:
                totals["regions_orphaned"] += 1
                continue
            while (len(st.norm(text_of(idx))) < MIN_SECTION_CHARS
                   and sections[idx]["parent"] is not None):
                idx = sections[idx]["parent"]
            assigned[idx].append({"page": page, "kind": region["kind"], "rect": rect})

    units_out: list[dict] = []
    for idx, regions in sorted(assigned.items()):
        sec = sections[idx]
        path = st.section_path(sections, idx)
        text = text_of(idx)
        prose = st.norm(text)
        ok, reason = bmd.rule4_verdict(text)
        cues = bmd.figure_cues(text)
        qtype, qreason = bmd.assign_question_type(cues)
        region_pages = sorted({r["page"] for r in regions})
        section_id = f"s{idx:04d}_{bsd.slug(sec['label'])}"
        unit_dir = out_root / doc_id / section_id

        images: list[dict] = []
        page_renders: list[dict] = []
        if apply:
            unit_dir.mkdir(parents=True, exist_ok=True)
            (unit_dir / "section.txt").write_text(text, encoding="utf-8")
            for page in region_pages:
                prefix = f"p{page:04d}"
                render = bmd.render_page(doc[page - 1], unit_dir / f"page_{prefix}.png")
                page_renders.append({**render, "page": page})
                images.extend(bsd.extract_page_rasters(pdf, page, unit_dir, prefix))
                vector = 0
                for region in [r for r in regions if r["page"] == page]:
                    if region["kind"] == "raster":
                        continue
                    vector += 1
                    images.append({
                        **bmd.render_region(doc[page - 1], region["rect"],
                                            unit_dir / f"{prefix}_region_{vector}.png"),
                        "page": page, "region_kind": region["kind"],
                    })

        unit = {
            "unit_id": f"{doc_id}::{section_id}",
            "doc_id": doc_id,
            "source_pdf": None,  # filled by the caller, which knows the corpus path
            "source_sha256": None,
            "granularity": "section",
            "section": {
                "section_index": idx,
                "label": sec["label"],
                "title": sec["title"],
                "rank": sec["rank"],
                "raw_level": sec["raw_level"],
                "ancestor_path": [{"label": s["label"], "title": s["title"]} for s in path],
                "start_page": sec["start_page"],
                "end_page": sec["end_page"],
                "span_pages": sec["end_page"] - sec["start_page"] + 1,
            },
            "text_file": "section.txt",
            "text_source": "pdf_text_layer",
            "text_chars": len(prose),
            "region_pages": region_pages,
            "region_kinds": dict(Counter(r["kind"] for r in regions)),
            "regions": [
                {"page": r["page"], "kind": r["kind"],
                 "rect_pt": [round(r["rect"].x0, 1), round(r["rect"].y0, 1),
                             round(r["rect"].x1, 1), round(r["rect"].y1, 1)]}
                for r in regions
            ],
            "figure_cues": cues,
            "question_type": qtype,
            "question_type_reason": qreason,
            "rule4_text_sufficient": ok,
            "rule4_reason": reason,
            "has_embedded_raster": any(r["kind"] == "raster" for r in regions),
            "frame_c_rule3_eligible": any(
                i["source"] == "embedded_raster" for i in images) if apply else None,
            "page_renders": page_renders,
            "images": images,
        }
        units_out.append(unit)
        totals["units"] += 1
        totals["regions_assigned"] += len(regions)
        for kind, n in Counter(r["kind"] for r in regions).items():
            totals[f"regions_{kind}"] += n
        if ok:
            totals["units_rule4_ok"] += 1

    doc_rec = {
        "doc_id": doc_id,
        "pages": doc.page_count,
        "sections_detected": len(sections),
        "toc_pages": info["toc_pages"],
        "back_matter_pages": info.get("back_matter_pages", []),
        "furniture_templates": info.get("furniture", []),
        "watermark_templates": info.get("watermarks", []),
        "units": len(units_out),
        "unit_sections": [u["section"]["label"] for u in units_out],
    }
    return units_out, doc_rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    report = json.loads(STAGING_REPORT.read_text("utf-8"))
    staged = [r for r in report["records"] if r["outcome"] == "STAGED"]

    page_manifest = json.loads((PAGES_ROOT / "MANIFEST.json").read_text("utf-8"))
    section_manifest = json.loads((SECTIONS_ROOT / "MANIFEST.json").read_text("utf-8"))
    existing_pages = {d["doc_id"] for d in page_manifest["docs"]}
    existing_sha = {d["source_sha256"] for d in page_manifest["docs"]}
    next_index = max(int(d["doc_id"][1:3]) for d in page_manifest["docs"]) + 1

    plan = []
    for offset, rec in enumerate(staged):
        if rec["sha256"] in existing_sha:
            print(f"  skip (already built): {rec['staged_path']}")
            continue
        doc_id = doc_id_for(next_index + len(plan), rec["staged_path"])
        if doc_id in existing_pages:
            raise SystemExit(f"id collision: {doc_id}")
        plan.append({"doc_id": doc_id, **rec})

    print(f"round-19 additions: {len(plan)} documents, ids "
          f"{plan[0]['doc_id'][:3]}..{plan[-1]['doc_id'][:3]}")
    for p in plan:
        print(f"  {p['doc_id'][:34]:34s} {p['pages']:4d}pp  {p['title'][:44]}")
    print()
    print("existing builds are not rebuilt; doc indices are pinned, not re-sorted")

    if not args.apply:
        print("\ndry run; pass --apply to build")
        return 0

    cache = json.loads(CACHE.read_text("utf-8")) if CACHE.is_file() else {}
    tmp = PAGES_ROOT / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    page_totals: Counter = Counter()
    section_totals: Counter = Counter()
    new_page_docs, new_section_docs = [], []

    for p in plan:
        pdf = CORPUS / p["staged_path"]
        doc_id = p["doc_id"]
        doc = pymupdf.open(pdf)

        page_units = build_page_units(pdf, doc_id, doc, PAGES_ROOT,
                                      apply=True, tmp=tmp, totals=page_totals)
        page_rec = {
            "doc_id": doc_id,
            "title": p["title"],
            "source_pdf": p["staged_path"],
            "source_sha256": p["sha256"],
            "pages": doc.page_count,
            "furniture_signatures": len(bmd.furniture_signatures(doc)),
            "units": len(page_units),
            "unit_pages": [u["page"] for u in page_units],
            "acquisition_round": 19,
        }
        (PAGES_ROOT / doc_id).mkdir(parents=True, exist_ok=True)
        (PAGES_ROOT / doc_id / "doc.json").write_text(
            json.dumps({**page_rec, "unit_records": page_units},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        new_page_docs.append(page_rec)
        page_totals["docs"] += 1
        page_totals["pages_scanned"] += doc.page_count

        sec_units, sec_rec = build_section_units(
            pdf, doc_id, doc, page_rec["unit_pages"], SECTIONS_ROOT,
            apply=True, cache=cache, totals=section_totals)
        for u in sec_units:
            u["source_pdf"] = p["staged_path"]
            u["source_sha256"] = p["sha256"]
            (SECTIONS_ROOT / doc_id / u["unit_id"].split("::")[1]
             / "unit.json").write_text(
                json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")
        sec_rec.update({"source_pdf": p["staged_path"],
                        "source_sha256": p["sha256"],
                        "acquisition_round": 19, "in_scope": True})
        if sec_units:
            (SECTIONS_ROOT / doc_id).mkdir(parents=True, exist_ok=True)
            (SECTIONS_ROOT / doc_id / "doc.json").write_text(
                json.dumps({**sec_rec, "unit_records": sec_units},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        new_section_docs.append(sec_rec)
        section_totals["docs_scanned"] += 1
        if sec_units:
            section_totals["docs_contributing"] += 1
        doc.close()
        print(f"  {doc_id[:34]:34s} page_units={len(page_units):3d} "
              f"section_units={len(sec_units):3d}")

    if tmp.exists():
        shutil.rmtree(tmp)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for manifest, root, new_docs, totals in (
        (page_manifest, PAGES_ROOT, new_page_docs, page_totals),
        (section_manifest, SECTIONS_ROOT, new_section_docs, section_totals),
    ):
        manifest["docs"].extend(new_docs)
        for key, value in totals.items():
            manifest["totals"][key] = manifest["totals"].get(key, 0) + value
        manifest.setdefault("extensions", []).append({
            "utc": stamp,
            "added_docs": [d["doc_id"] for d in new_docs],
            "acquisition_round": 19,
            "shelf": "Kệ C2-C8 (Giáo trình)",
            "discovery": "corpus/reports/round19_shelf_discovery_20260829T183005Z.json",
            "staging": str(STAGING_REPORT.relative_to(SANDBOX)),
            "script": "corpus/scripts/extend_datasets_round19.py",
            "why_ids_are_pinned": (
                "the builders number documents by descending page count, so a "
                "rebuild would renumber existing docs and invalidate every "
                "unit_id already cited by the rights ledger, ELIGIBLE_UNITS.json "
                "and SECTION_FRAME_DETERMINATION.json"
            ),
            "totals_added": dict(totals),
        })
        (root / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"updated {(root / 'MANIFEST.json').relative_to(SANDBOX)}")

    print()
    print("page-level added   :", dict(page_totals))
    print("section-level added:", dict(section_totals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
