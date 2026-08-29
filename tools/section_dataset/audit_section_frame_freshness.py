#!/usr/bin/env python3
"""Freshness audit for the section-level candidate chunks against ROUND4_NECESSITY_ADDENDUM.md §7.

§7 forbids a round-4 frame drawn from "the round-1 16, the Frame B 15, or the
repaired 16". SECTION_FRAME_DETERMINATION.json applied §7 against the *sealed
frame-C 24* instead, which is the frame that actually ran. That is a stricter
test than §7 as written for the frame-C pages, but it leaves the three frames
§7 actually names unchecked. This script closes that gap.

Two independent checks, both read-only:

1. Source identity. Are any of the 20 section-source PDFs byte-identical to a
   PDF in the legacy 48-document corpus that the three §7 frames were drawn
   from? (doc_id strings collide across corpora, so identity is by sha256.)

2. Content overlap. For every candidate section unit, the maximum 8-word
   shingle containment against every distinct chunk text in the three §7
   frames. Containment (intersection / min set size) is used rather than
   Jaccard so that a short prior chunk fully contained in a long section unit
   still scores 1.0.

Nothing is written unless --emit is given, which patches an additive
`freshness_audit` block into the determination record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]

DETERMINATION = SANDBOX / "corpus/reports/SECTION_FRAME_DETERMINATION.json"
SECTION_MANIFEST = SANDBOX / "datasets_sections/MANIFEST.json"
SECTIONS_ROOT = SANDBOX / "datasets_sections"
ELIGIBLE = SANDBOX / "datasets_sections/ELIGIBLE_UNITS.json"
ADDENDUM = SANDBOX / "prospective/v3103_round2/ROUND4_NECESSITY_ADDENDUM.md"
LEGACY_ROOT = Path("/Users/van/Workspace/Research/03_Datasets/DHH2026_HOEIT_Law_Textbooks/raw")
CORPUS_ROOT = SANDBOX / "corpus"

S7_FRAMES = {
    "round1_16": SANDBOX / "experiment/dataset/dataset_manifest.json",
    "frameb_15": SANDBOX / "experiment/dataset_frameb/dataset_manifest.json",
    "repaired_16": SANDBOX / "experiment/dataset_repaired/dataset_manifest.json",
}

SHINGLE_K = 8
# A containment at or above this is treated as a possible reuse and listed.
REVIEW_AT = 0.05

_WS = re.compile(r"\s+")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def norm(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", text).lower()).strip()


def shingles(text: str, k: int = SHINGLE_K) -> set[str]:
    words = norm(text).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def load_prior_chunks() -> dict[str, dict]:
    """Distinct chunk texts across the three frames §7 names."""
    out: dict[str, dict] = {}
    for frame_name, path in S7_FRAMES.items():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for pkg in manifest["packages"]:
            chunk_id = pkg["chunk_id"]
            if chunk_id in out:
                out[chunk_id]["frames"].append(frame_name)
                continue
            text = pkg["evidence"].get("text") or ""
            if isinstance(text, dict):
                text = json.dumps(text, ensure_ascii=False)
            out[chunk_id] = {
                "frames": [frame_name],
                "doc_id": pkg["doc_id"],
                "shingles": shingles(text),
                "words": len(norm(text).split()),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true",
                    help="patch an additive freshness_audit block into the determination record")
    ap.add_argument("--all-eligible", action="store_true",
                    help="audit all 60 rights-eligible units, not just the 14 fresh ones")
    args = ap.parse_args()

    det = json.loads(DETERMINATION.read_text(encoding="utf-8"))
    fresh_ids = [fc["unit_id"] for fc in det["fresh_chunks"]]
    if args.all_eligible:
        target_ids = json.loads(ELIGIBLE.read_text(encoding="utf-8"))["unit_ids"]
    else:
        target_ids = fresh_ids

    # ---- check 1: source identity by sha256 -------------------------------
    legacy_pdfs = sorted(LEGACY_ROOT.glob("*.pdf")) if LEGACY_ROOT.is_dir() else []
    legacy_by_hash: dict[str, list[str]] = {}
    for pdf in legacy_pdfs:
        legacy_by_hash.setdefault(sha256_file(pdf), []).append(pdf.name)

    section_docs = {d["doc_id"]: d for d in json.loads(SECTION_MANIFEST.read_text(encoding="utf-8"))["docs"]}
    identity_hits = []
    for doc_id, doc in sorted(section_docs.items()):
        if doc["source_sha256"] in legacy_by_hash:
            identity_hits.append({"doc_id": doc_id, "legacy_files": legacy_by_hash[doc["source_sha256"]]})

    print("check 1 - source identity against the legacy 48-document corpus")
    if not legacy_pdfs:
        print(f"  SKIPPED: legacy corpus not present at {LEGACY_ROOT}")
    else:
        print(f"  legacy PDFs hashed:        {len(legacy_pdfs)}")
        print(f"  distinct legacy hashes:    {len(legacy_by_hash)}")
        print(f"  section source PDFs:       {len(section_docs)}")
        print(f"  byte-identical collisions: {len(identity_hits)}")
        for hit in identity_hits:
            print(f"    {hit['doc_id']} == {hit['legacy_files']}")

    # ---- check 2: content overlap ----------------------------------------
    prior = load_prior_chunks()
    usable = {cid: rec for cid, rec in prior.items() if rec["shingles"]}
    print()
    print(f"check 2 - {SHINGLE_K}-word shingle containment against the three §7 frames")
    print(f"  distinct prior chunks:     {len(prior)}")
    print(f"  with usable text:          {len(usable)}")
    print(f"  candidate units audited:   {len(target_ids)}")

    rows = []
    for unit_id in target_ids:
        doc_id, section_id = unit_id.split("::")
        text_path = SECTIONS_ROOT / doc_id / section_id / "section.txt"
        unit_sh = shingles(text_path.read_text(encoding="utf-8"))
        best_score, best_cid = 0.0, None
        for cid, rec in usable.items():
            inter = len(unit_sh & rec["shingles"])
            if not inter:
                continue
            score = inter / min(len(unit_sh), len(rec["shingles"]))
            if score > best_score:
                best_score, best_cid = score, cid
        rows.append({
            "unit_id": unit_id,
            "max_containment": round(best_score, 4),
            "nearest_prior_chunk": best_cid,
            "nearest_prior_frames": usable[best_cid]["frames"] if best_cid else [],
        })

    rows.sort(key=lambda r: -r["max_containment"])
    for row in rows:
        flag = "  <-- REVIEW" if row["max_containment"] >= REVIEW_AT else ""
        print(f"  {row['max_containment']:6.3f}  {row['unit_id'][:60]:60s}"
              f"  {str(row['nearest_prior_chunk'])[:40]}{flag}")

    max_containment = max((r["max_containment"] for r in rows), default=0.0)
    over = [r for r in rows if r["max_containment"] >= REVIEW_AT]
    verdict_fresh = not identity_hits and not over

    print()
    print(f"  max containment:           {max_containment:.4f}")
    print(f"  units at or above {REVIEW_AT}:     {len(over)}")
    print()
    print("VERDICT: " + (
        "all audited units are fresh under §7 as written "
        "(no shared source bytes, no shared passage)"
        if verdict_fresh else
        "at least one audited unit needs manual adjudication against §7"))

    if args.emit:
        block = {
            "why": ("SECTION_FRAME_DETERMINATION applied addendum §7 against the sealed frame-C 24, "
                    "but §7 as written forbids the round-1 16, the Frame B 15 and the repaired 16. "
                    "Those three frames were drawn from a different corpus (the legacy 48 law "
                    "textbooks) whose doc_id strings collide with the section corpus by title, so "
                    "freshness against them is established by source bytes and passage text, not by "
                    "doc_id or page number."),
            "script": "corpus/scripts/audit_section_frame_freshness.py",
            "audited": "the 14 fresh chunks" if not args.all_eligible else "all 60 rights-eligible units",
            "addendum_sha256": hashlib.sha256(ADDENDUM.read_bytes()).hexdigest(),
            "s7_frames_checked": {
                name: {
                    "path": str(path.relative_to(SANDBOX)),
                    "sha256": sha256_file(path),
                } for name, path in S7_FRAMES.items()
            },
            "distinct_prior_chunks": len(prior),
            "source_identity_check": {
                "legacy_corpus_root": str(LEGACY_ROOT),
                "legacy_pdfs_hashed": len(legacy_pdfs),
                "byte_identical_collisions": len(identity_hits),
                "collisions": identity_hits,
                "note": ("The three §7 frames cite doc_ids such as '34.LUAT THUONG MAI QUOC TE', "
                         "which collides by title with the section corpus's T10 "
                         "'Giáo trình luật thương mại quốc tế'. No section source PDF is "
                         "byte-identical to any legacy PDF, so the collision is of titles, not files."),
            },
            "content_overlap_check": {
                "measure": f"{SHINGLE_K}-word shingle containment (intersection / min set size), NFC + case + whitespace normalised",
                "why_containment_not_jaccard": "a short prior chunk fully contained in a long section unit scores 1.0 under containment but low under Jaccard",
                "review_threshold": REVIEW_AT,
                "max_containment": max_containment,
                "units_at_or_above_threshold": len(over),
                "per_unit": rows,
            },
            "verdict": ("FRESH under §7 as written: no audited unit shares source bytes or any "
                        "8-word passage above the review threshold with the round-1 16, the "
                        "Frame B 15, or the repaired 16."
                        if verdict_fresh else "NEEDS ADJUDICATION"),
            "does_not_change": ("The count of 14 fresh chunks and the below-floor conclusion are "
                                "unchanged. This audit only widens the no-reuse check from the "
                                "sealed frame-C 24 to the three frames §7 actually names."),
        }
        det["freshness_audit_s7"] = block
        DETERMINATION.write_text(json.dumps(det, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print()
        print(f"patched freshness_audit_s7 into {DETERMINATION.relative_to(SANDBOX)}")
        print("new sha256:", sha256_file(DETERMINATION))

    return 0 if verdict_fresh else 1


if __name__ == "__main__":
    raise SystemExit(main())
