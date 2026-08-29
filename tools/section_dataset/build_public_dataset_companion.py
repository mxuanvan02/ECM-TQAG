#!/usr/bin/env python3
"""Build the PUBLIC, metadata-only companion to the ECM section input dataset.

Why this exists rather than publishing the dataset itself:

  * The source PDFs, their text, and the figure crops are copyright of the
    University of Law, Hue University and are held on an internal-research
    basis. That basis is what the round-1 dataset already ships under
    (`experiment/dataset/DATASET_NOTICE.md`).
  * `repo/RIGHTS_AND_LIMITATIONS.md` states publicly that the repository
    contains no source-derived document images or restricted datasets.
    Publishing the payload would make that statement false.
  * Rule 1 of the standing rights attestation excludes a source outright when
    its PDF forbids copying, so the project already treats redistribution of
    this material as gated rather than assumed.

What the companion therefore carries, per chunk: identity, provenance hashes,
the gate decisions that admitted it, region geometry, and counts. What it does
NOT carry: any section prose, any figure word, any image bytes.

That is enough for a reader to verify the frame arithmetic and to rebuild the
dataset from their own copy of the catalogue, which is the reproducibility
claim the paper actually needs.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
PRIVATE = SANDBOX / "experiment/dataset_sections/dataset_manifest.json"
SECTION_MANIFEST = SANDBOX / "datasets_sections/MANIFEST.json"
OTHER_MANIFEST = SANDBOX / "datasets_sections_other/MANIFEST.json"
REPO = SANDBOX / "repo"
OUT_DIR = REPO / "datasets/sections-metadata"

REPORTS = {
    "ocr_fidelity": "corpus/reports/OCR_FIDELITY_PROBE.json",
    "figure_ocr_calibration": "corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json",
    "figure_text_augmentation": "corpus/reports/FIGURE_TEXT_AUGMENTATION.json",
    "region_ocr_surplus": "corpus/reports/REGION_OCR_SURPLUS_PROBE.json",
    "rights_ledger": "corpus/reports/SECTION_DATASET_RIGHTS_RECONCILIATION.json",
    "frame_determination": "corpus/reports/SECTION_FRAME_DETERMINATION.json",
    "scope_decision": "corpus/reports/DATASET_SCOPE_LAW_TEXTBOOKS.json",
    "shelf_discovery": "corpus/reports/round19_shelf_discovery_20260829T183005Z.json",
}


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

    private = json.loads(PRIVATE.read_text("utf-8"))
    sections = json.loads(SECTION_MANIFEST.read_text("utf-8"))
    doc_by_id = {d["doc_id"]: d for d in sections["docs"]}
    if OTHER_MANIFEST.is_file():
        for d in json.loads(OTHER_MANIFEST.read_text("utf-8"))["docs"]:
            doc_by_id.setdefault(d["doc_id"], d)

    # ---- per-document provenance, no content -----------------------------
    documents = []
    for doc_id, doc in sorted(doc_by_id.items()):
        documents.append({
            "doc_id": doc_id,
            "source_sha256": doc["source_sha256"],
            "pages": doc["pages"],
            "sections_detected": doc.get("sections_detected"),
            "units_built": doc.get("units", 0),
            "in_scope": doc.get("in_scope", True),
        })

    # ---- per-frame chunk metadata, no content ----------------------------
    frames = {}
    for name, frame in private["frames"].items():
        chunks = []
        for pkg in frame["packages"]:
            ev = pkg["evidence"]
            ds = ev["document_structure"]
            ft = ev.get("figure_text") or {}
            chunks.append({
                "chunk_id": pkg["chunk_id"],
                "doc_id": pkg["doc_id"],
                "question_type": pkg["question_type"],
                "condition": pkg["condition"],
                "split": pkg["split"],
                "section_label": ds.get("section_label"),
                "ancestor_depth": len(ds.get("ancestor_path") or []),
                "pages": ds.get("pages"),
                "section_pages": ds.get("section_pages"),
                "text_chars": len(ev.get("text") or ""),
                "figure_cues": ds.get("figure_cues"),
                "images": [
                    {
                        "declared_order": im.get("declared_order"),
                        "width": im["width"],
                        "height": im["height"],
                        "bytes": im["bytes"],
                        "sha256": im["sha256"],
                        "source": im.get("source"),
                    }
                    for im in ev.get("images", [])
                ],
                "figure_text_counts": {
                    "words_kept": len(ft.get("words") or []),
                    "surplus_count": len(ft.get("surplus_words") or []),
                },
            })
        frames[name] = {
            "rule3_reading": frame["rule3_reading"],
            "chunk_count": frame["chunk_count"],
            "reaches_floor": frame["reaches_floor"],
            "documents": frame["documents"],
            "question_types": frame["question_types"],
            "dropped_count": len(frame.get("dropped") or []),
            "chunks": chunks,
        }

    companion = {
        "schema": "ecm-tqag.section-dataset-public-companion.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "what_this_is": (
            "Metadata-only companion to the section-level ECM input dataset. It "
            "carries chunk identity, provenance hashes, gate decisions, region "
            "geometry and counts, and deliberately carries no section prose, no "
            "recognised figure word, and no image bytes."
        ),
        "why_content_is_withheld": (
            "The source PDFs, their text layer and the figure crops are copyright "
            "of the University of Law, Hue University and are held on an "
            "internal-research basis, not a redistribution basis. Publishing them "
            "would also contradict RIGHTS_AND_LIMITATIONS.md, which states this "
            "repository contains no source-derived document images or restricted "
            "datasets."
        ),
        "how_to_rebuild_the_full_dataset": [
            "obtain the 26 textbooks from the University of Law, Hue University "
            "catalogue (shelf 'Kệ C2-C8 (Giáo trình)'); each is identified here by "
            "sha256, so a rebuild is verifiable byte-for-byte",
            "run corpus/build_multimodal_dataset.py to screen figure-bearing pages",
            "run corpus/scripts/build_section_dataset.py for section granularity",
            "run corpus/reconcile_rights_sections.py for the rights ledger",
            "run corpus/scripts/augment_figure_text.py for the figure-text channel",
            "run corpus/scripts/build_ecm_input_dataset.py for the ECM input",
            "the image sha256 values recorded here then reproduce exactly",
        ],
        "scope": private["scope"],
        "text_source": private["text_source"],
        "figure_text_contract": private["figure_text_contract"],
        "authorisation": private["authorisation"],
        "private_manifest": {
            "path": str(PRIVATE.relative_to(SANDBOX)),
            "sha256": sha256_file(PRIVATE),
            "published": False,
        },
        "provenance_reports": {
            key: {
                "path": rel,
                "sha256": sha256_file(SANDBOX / rel),
            }
            for key, rel in REPORTS.items()
            if (SANDBOX / rel).is_file()
        },
        "documents": documents,
        "frames": frames,
    }

    print(f"documents          {len(documents)}")
    for name, frame in frames.items():
        imgs = sum(len(c["images"]) for c in frame["chunks"])
        surplus = sum(c["figure_text_counts"]["surplus_count"] for c in frame["chunks"])
        print(f"{name:16s} chunks={frame['chunk_count']:3d} images={imgs:3d} "
              f"surplus_words={surplus:4d} floor={frame['reaches_floor']}")

    blob = json.dumps(companion, ensure_ascii=False, indent=1) + "\n"

    # Refuse to emit if any withheld content leaked into the companion.
    banned = ("section.txt", '"text":', '"figure_words"', '"surplus_words":')
    leaked = [b for b in banned if b in blob]
    if leaked:
        raise SystemExit(f"refusing to write: withheld content leaked {leaked}")

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "section_dataset_companion.json"
    dest.write_text(blob, encoding="utf-8")
    print(f"\nwrote {dest.relative_to(SANDBOX)}")
    print("sha256", sha256_file(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
