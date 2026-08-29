#!/usr/bin/env python3
"""Apply the owner's dataset scope: law textbooks (giáo trình luật) only.

The section dataset was built from 20 textbook PDFs held by the University of
Law, Hue University (HUL) catalogue. One contributing document is not a law
textbook:

  T11_r12_p1_03 = "Giáo trình Hải quan cơ bản", Nguyễn Thị Thương Huyền,
  Học viện Tài chính, NXB Tài chính — a customs textbook from a finance
  academy, resolved from its own title pages.

Per the owner's decision the scope is law textbooks. T11 is NOT deleted and NOT
recorded as an exclusion: its units are relocated intact, with their hashes
re-verified after the move, to a sibling root that is documented as
out-of-scope-but-retained.

Nothing sha256-bound is touched. `datasets_sections/MANIFEST.json` is not bound
by any record (checked), so its totals are recomputed to match what is on disk;
the relocated counts are preserved in the doc record rather than dropped.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import unicodedata
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
SECTIONS = SANDBOX / "datasets_sections"
OTHER = SANDBOX / "datasets_sections_other"
ELIGIBLE = SECTIONS / "ELIGIBLE_UNITS.json"
LEDGER = SANDBOX / "corpus/reports/SECTION_DATASET_RIGHTS_RECONCILIATION.json"
SCOPE_RECORD = SANDBOX / "corpus/reports/DATASET_SCOPE_LAW_TEXTBOOKS.json"

# Resolved from each PDF's own title pages, not from the filename.
OUT_OF_SCOPE = {
    "T11_r12_p1_03": {
        "title": "Giáo trình Hải quan cơ bản",
        "author": "PGS.TS. Nguyễn Thị Thương Huyền",
        "institution": "Học viện Tài chính",
        "publisher": "Nhà xuất bản Tài chính",
        "why_out_of_scope": (
            "subject is customs administration, not law, and the issuing "
            "institution is Học viện Tài chính rather than a law faculty; "
            "resolved from the book's own title and foreword pages"
        ),
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def norm(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def unit_dirs(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.glob("*/*/unit.json"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    manifest = json.loads((SECTIONS / "MANIFEST.json").read_text("utf-8"))
    eligible = json.loads(ELIGIBLE.read_text("utf-8"))
    by_doc = {d["doc_id"]: d for d in manifest["docs"]}

    for doc_id in OUT_OF_SCOPE:
        if doc_id not in by_doc:
            raise SystemExit(f"{doc_id} absent from MANIFEST.docs")

    print("scope decision: law textbooks (giáo trình luật) only")
    print(f"  documents scanned            {manifest['totals']['docs_scanned']}")
    print(f"  documents contributing units {manifest['totals']['docs_contributing']}")
    print()

    moved_units: dict[str, list[str]] = {}
    for doc_id, meta in OUT_OF_SCOPE.items():
        rec = by_doc[doc_id]
        dirs = sorted((SECTIONS / doc_id).glob("*/unit.json"))
        moved_units[doc_id] = [json.loads(p.read_text("utf-8"))["unit_id"] for p in dirs]
        print(f"  out of scope: {doc_id}")
        print(f"    {meta['title']} — {meta['institution']}")
        print(f"    units {rec['units']}, on disk {len(dirs)}, pages {rec['pages']}")
        print(f"    reason: {meta['why_out_of_scope']}")

    in_scope_docs = [d for d in manifest["docs"] if d["doc_id"] not in OUT_OF_SCOPE]
    kept_units = sum(d["units"] for d in in_scope_docs)
    kept_regions = manifest["totals"]["regions_assigned"] - sum(
        len(json.loads(p.read_text("utf-8"))["regions"])
        for doc_id in OUT_OF_SCOPE
        for p in (SECTIONS / doc_id).glob("*/unit.json")
    )
    kept_eligible = [u for u in eligible["unit_ids"]
                     if u.split("::", 1)[0] not in OUT_OF_SCOPE]

    print()
    print("               before   after")
    print(f"  units          {manifest['totals']['units']:5d}   {kept_units:5d}")
    print(f"  eligible       {eligible['count']:5d}   {len(kept_eligible):5d}")
    print(f"  contributing   {manifest['totals']['docs_contributing']:5d}"
          f"   {sum(1 for d in in_scope_docs if d['units']):5d}")

    if not args.apply:
        print("\ndry run; pass --apply to relocate")
        return 0

    # ---- relocate, hashing before and after so the move is provably lossless
    OTHER.mkdir(exist_ok=True)
    relocations = []
    for doc_id in OUT_OF_SCOPE:
        src = SECTIONS / doc_id
        dst = OTHER / doc_id
        if dst.exists():
            raise SystemExit(f"refusing to overwrite {dst}")
        before = {str(p.relative_to(src)): sha256_file(p)
                  for p in sorted(src.rglob("*")) if p.is_file()}
        shutil.move(str(src), str(dst))
        after = {str(p.relative_to(dst)): sha256_file(p)
                 for p in sorted(dst.rglob("*")) if p.is_file()}
        if before != after:
            raise SystemExit(f"{doc_id}: file set or hashes changed across the move")
        relocations.append({
            "doc_id": doc_id,
            "from": str(src.relative_to(SANDBOX)),
            "to": str(dst.relative_to(SANDBOX)),
            "files": len(before),
            "unit_ids": moved_units[doc_id],
            "hashes_unchanged": True,
            **OUT_OF_SCOPE[doc_id],
        })
        print(f"\nmoved {doc_id}: {len(before)} files, all hashes unchanged")

    # ---- out-of-scope manifest carries the full doc records
    (OTHER / "MANIFEST.json").write_text(json.dumps({
        "schema": "ecm-tqag.section-dataset-out-of-scope.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "what_this_is": (
            "Section-level multimodal units built from documents that fall "
            "outside the dataset scope of law textbooks. Retained intact, not "
            "deleted and not recorded as a rules exclusion: the scope is a "
            "decision about what the dataset covers, so material outside it is "
            "relocated rather than discarded."
        ),
        "scope_of_the_main_dataset": "law textbooks (giáo trình luật)",
        "main_dataset": "datasets_sections/",
        "redistribution": manifest["redistribution"],
        "section_recovery": manifest["section_recovery"],
        "detection": manifest["detection"],
        "relocations": relocations,
        "docs": [by_doc[d] for d in OUT_OF_SCOPE],
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---- main manifest: recompute totals, keep the relocated counts visible
    for doc_id in OUT_OF_SCOPE:
        rec = by_doc[doc_id]
        rec["units_relocated"] = rec["units"]
        rec["unit_sections_relocated"] = rec["unit_sections"]
        rec["units"] = 0
        rec["unit_sections"] = []
        rec["in_scope"] = False
        rec["relocated_to"] = f"datasets_sections_other/{doc_id}"
        rec["why_out_of_scope"] = OUT_OF_SCOPE[doc_id]["why_out_of_scope"]

    manifest["scope"] = {
        "decision": "law textbooks (giáo trình luật) only",
        "decided_by": "owner",
        "decided_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frame": (
            "textbooks held by the University of Law, Hue University catalogue; "
            "library holding rather than HUL authorship, so a law textbook from "
            "another publisher stays in scope"
        ),
        "out_of_scope_relocated_to": "datasets_sections_other/",
        "record": "corpus/reports/DATASET_SCOPE_LAW_TEXTBOOKS.json",
        "note": (
            "Documents outside the scope are relocated intact, not excluded. "
            "Documents that were scanned but yielded no unit stay listed here "
            "with units 0, since the scan is part of the build record."
        ),
    }
    manifest["totals"]["units"] = kept_units
    manifest["totals"]["regions_assigned"] = kept_regions
    manifest["totals"]["units_rule4_ok"] = kept_units
    manifest["totals"]["docs_contributing"] = sum(1 for d in in_scope_docs if d["units"])
    manifest["totals"]["docs_out_of_scope_relocated"] = len(OUT_OF_SCOPE)
    (SECTIONS / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    eligible["count"] = len(kept_eligible)
    eligible["unit_ids"] = kept_eligible
    eligible["scope"] = "law textbooks (giáo trình luật) only"
    eligible["relocated_out_of_scope"] = {
        d: moved_units[d] for d in OUT_OF_SCOPE}
    ELIGIBLE.write_text(json.dumps(eligible, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    SCOPE_RECORD.write_text(json.dumps({
        "schema": "ecm-tqag.dataset-scope.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "decision": "The multimodal dataset covers law textbooks (giáo trình luật).",
        "decided_by": "owner",
        "how_scope_was_applied": (
            "Every contributing document's subject and issuing institution were "
            "resolved from its own title and foreword pages, not from its "
            "filename or catalogue row. One document is not a law textbook and "
            "was relocated intact."
        ),
        "relocations": relocations,
        "counts": {
            "documents_scanned": manifest["totals"]["docs_scanned"],
            "units_in_scope": kept_units,
            "units_relocated": sum(len(v) for v in moved_units.values()),
            "rights_eligible_in_scope": len(kept_eligible),
            "documents_contributing_in_scope": manifest["totals"]["docs_contributing"],
        },
        "not_an_exclusion": (
            "Relocation is not a rights or rules exclusion. The rights ledger "
            "at corpus/reports/SECTION_DATASET_RIGHTS_RECONCILIATION.json is "
            "unchanged and still records its own verdicts for every unit it "
            "assessed, including the relocated ones."
        ),
        "inputs_unchanged": {
            "rights_ledger": str(LEDGER.relative_to(SANDBOX)),
            "rights_ledger_sha256": sha256_file(LEDGER),
        },
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"\nwrote {SCOPE_RECORD.relative_to(SANDBOX)}")
    print(f"wrote {(OTHER / 'MANIFEST.json').relative_to(SANDBOX)}")
    print(f"updated {(SECTIONS / 'MANIFEST.json').relative_to(SANDBOX)}")
    print(f"updated {ELIGIBLE.relative_to(SANDBOX)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
