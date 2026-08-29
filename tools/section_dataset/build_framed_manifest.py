#!/usr/bin/env python3
"""Emit the Frame-D census manifest in the schema the sealed loader accepts.

Frame D is the section-level frame drawn from the law-textbook scope. It differs
from the sealed Frame C in exactly two declared ways:

  1. GRANULARITY. A chunk is one section of a textbook, not one page. The context
     text is the whole section with page furniture removed, so an argument is not
     cut at a page boundary.

  2. RULE 3 READING. Frame C's frozen operationalisation counted only embedded
     rasters at or above 203 px. Frame D applies the literal text of rule 3 --
     "at least one extracted figure crop resolvable on disk" -- which a rendered
     vector region satisfies. This is a DEVIATION and is declared as one: vector
     renders were never in the round-1 or Frame-B evidence bundles. It is the
     reason Frame D must be pre-registered before any call rather than folded
     into the frame-C record.

Everything else is carried unchanged: rule 4 text sufficiency at the frozen
thresholds, the addendum §7 no-reuse clause against the sealed 24, the frozen
question-type rule, condition TLV, split test.

`evidence.figure_text` rides alongside as a separate channel and is NOT part of
`evidence.text`. The verbatim-quote gate reads `evidence.text` only, exactly as
the sealed frame does, so the OCR channel cannot enter the gate.

Output schema is `ecm-tqag.multimodal-inputs.v4-work24` because
`ecm_tqag.v310_runner.build_packages` fails closed on any other value. Reusing
the sealed schema string is deliberate: the package SHAPE is identical, and the
frame identity is carried by the manifest `frame` field and its sha256, not by
the schema string.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
EXPERIMENT = SANDBOX / "experiment"
SECTIONS_INPUT = EXPERIMENT / "dataset_sections" / "dataset_manifest.json"
OUT_DIR = EXPERIMENT / "dataset_framed"
SEALED_C = EXPERIMENT / "dataset_framec" / "dataset_manifest_rule4_20260816T105100Z.json"

# Frozen thresholds, quoted from ROUND3_FRAMEB_ADDENDUM rule 4.
RULE4_MIN_PROSE = 120

FRAME_NAME = "D_hul_law_textbook_sections"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reading", default="vector", choices=["vector", "strict"],
                    help="which rule-3 reading to materialise as Frame D")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    src = json.loads(SECTIONS_INPUT.read_text("utf-8"))
    frame = src["frames"][f"frame_d_{args.reading}"]
    packages_in = frame["packages"]

    problems: list[str] = []
    packages_out: list[dict] = []

    for pkg in packages_in:
        ev = pkg["evidence"]
        text = ev["text"]
        prose_nonspace = len("".join(str(text).split()))
        if prose_nonspace < RULE4_MIN_PROSE:
            problems.append(f"rule4_violation:{pkg['chunk_id']}")
            continue

        images_out = []
        for image in ev["images"]:
            rel = image["path"]
            abs_path = EXPERIMENT / rel
            if not abs_path.is_file():
                problems.append(f"missing_image:{rel}")
                continue
            raw = abs_path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != image["sha256"] or len(raw) != image["bytes"]:
                problems.append(f"image_integrity:{rel}")
                continue
            images_out.append({
                "path": rel,
                "declared_order": image["declared_order"],
                "width": image["width"],
                "height": image["height"],
                "bytes": len(raw),
                "sha256": actual,
                "source": image.get("source"),
            })
        if not images_out:
            problems.append(f"no_resolvable_image:{pkg['chunk_id']}")
            continue

        packages_out.append({
            "chunk_id": pkg["chunk_id"],
            "item_id": pkg["chunk_id"],
            "doc_id": pkg["doc_id"],
            "condition": "TLV",
            "split": "test",
            "question_type": pkg["question_type"],
            "evidence": {
                "text": text,
                "document_structure": ev["document_structure"],
                "images": images_out,
                "figure_text": ev.get("figure_text"),
            },
        })

    n = len(packages_out)
    manifest = {
        "schema": "ecm-tqag.multimodal-inputs.v4-work24",
        "schema_note": (
            "The schema string is the sealed one because ecm_tqag.v310_runner."
            "build_packages fails closed on any other value and that code is "
            "sealed. The package shape is identical to Frame C's. Frame identity "
            "is carried by `frame` and by this file's sha256, not by the schema "
            "string."
        ),
        "frame": FRAME_NAME,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunk_count": n,
        "granularity": "section",
        "source": (
            "26 law textbooks (giáo trình luật) held by the University of Law, "
            "Hue University catalogue, shelf Kệ C2-C8 (Giáo trình)"
        ),
        "deviations_from_frame_c": {
            "granularity": (
                "a chunk is one section with its full text, not one page with two "
                "neighbouring pages"
            ),
            "rule_3_reading": (
                "the literal text of rule 3 ('at least one extracted figure crop "
                "resolvable on disk'), which a rendered vector region satisfies. "
                "Frame C's frozen operationalisation counted embedded rasters only."
                if args.reading == "vector" else
                "none; the frozen embedded-raster operationalisation is applied"
            ),
            "why_declared": (
                "vector renders were never in the round-1 or Frame-B evidence "
                "bundles, so admitting them widens the gate. Declared as a "
                "deviation and pre-registered before any call rather than "
                "absorbed silently."
            ),
        },
        "rules_carried_unchanged": {
            "rule_4_text_sufficiency": (
                f"EXCLUDE if prose_chars < {RULE4_MIN_PROSE}, or enum_items >= 3 "
                "with prose_chars < 400; applied by the section builder and "
                "re-checked here"
            ),
            "addendum_s7_no_reuse": (
                "a unit whose (source_sha256, page) appears in the sealed 24-chunk "
                "frame is excluded; freshness against the round-1 16, Frame B 15 "
                "and repaired 16 is established by source bytes and 8-word shingle "
                "containment in corpus/reports/SECTION_FRAME_DETERMINATION.json"
            ),
            "question_type_rule": (
                "ROUND3_FRAMEB_ADDENDUM rule 5, applied mechanically from "
                "deterministic layout cues before execution"
            ),
        },
        "figure_text_contract": {
            "channel": "evidence.figure_text",
            "quotable_as_prose": False,
            "why": (
                "OCR of figure regions at confidence >= 90 still carries roughly "
                "one slip in ten on graphical strokes. The verbatim-quote gate "
                "reads evidence.text only."
            ),
            "calibration": "corpus/reports/FIGURE_OCR_CONFIDENCE_CALIBRATION.json",
        },
        "inputs": {
            "sections_input": str(SECTIONS_INPUT.relative_to(SANDBOX)),
            "sections_input_sha256": sha256_file(SECTIONS_INPUT),
            "sealed_frame_c": str(SEALED_C.relative_to(SANDBOX)),
            "sealed_frame_c_sha256": sha256_file(SEALED_C),
        },
        "question_type_counts": {
            q: sum(1 for p in packages_out if p["question_type"] == q)
            for q in sorted({p["question_type"] for p in packages_out})
        },
        "documents": len({p["doc_id"] for p in packages_out}),
        "redistribution": (
            "Section text and figure crops are copyright of the University of Law, "
            "Hue University and are held for internal research only. This manifest "
            "must not be published; the public release carries the metadata-only "
            "companion instead."
        ),
        "problems": problems,
        "packages": packages_out,
    }

    print(f"reading            {args.reading}")
    print(f"packages in        {len(packages_in)}")
    print(f"packages out       {n}")
    print(f"documents          {manifest['documents']}")
    print(f"question types      {manifest['question_type_counts']}")
    print(f"problems           {len(problems)}")
    for p in problems[:10]:
        print(f"  {p}")

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 1 if problems else 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = OUT_DIR / f"dataset_manifest_framed_{stamp}.json"
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(f"\nwrote {dest.relative_to(SANDBOX)}")
    print("sha256", sha256_file(dest))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
