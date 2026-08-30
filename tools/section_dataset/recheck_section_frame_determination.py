#!/usr/bin/env python3
"""Recompute every count in corpus/reports/SECTION_FRAME_DETERMINATION.json from
the unit records on disk, and assert the record matches.

This is a check, not a builder: it writes nothing and re-derives the numbers
independently of the script that produced the determination.

Two things are deliberately done differently from the original derivation, so
that agreement is evidence rather than a restatement:

  * sealed-frame overlap is resolved by (source pdf sha256, page) using
    corpus/DATASET_INDEX.json `frame_doc_ids`, not by matching doc_id strings.
    Two unrelated files can share one short doc_id across acquisition rounds.
  * each claimed overlap is additionally confirmed by crop sha256 against the
    sealed package images.

Exits non-zero on any mismatch.

    .venv/bin/python corpus/scripts/recheck_section_frame_determination.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DETERMINATION = ROOT / "corpus/reports/SECTION_FRAME_DETERMINATION.json"
ELIGIBLE = ROOT / "datasets_sections/ELIGIBLE_UNITS.json"
# The determination was computed before the owner narrowed the dataset scope to
# law textbooks, which relocated one contributing document intact to a sibling
# root. Its units still exist and are still what the record measured, so both
# roots are searched. The record's counts are dated evidence and are NOT
# rewritten to match the narrowed scope.
SECTION_ROOTS = (ROOT / "datasets_sections", ROOT / "datasets_sections_other")
DATASET_INDEX = ROOT / "corpus/DATASET_INDEX.json"
SEALED = ROOT / "experiment/dataset_framec/dataset_manifest_rule4_20260816T105100Z.json"

# frozen operationalisation of ROUND3_FRAMEB_ADDENDUM rule 3
CROP_FLOOR_PX = 203

# Sources acquired AFTER this determination was written. A unit whose source_pdf
# matches was not in the measured population and must not enter the recheck.
POST_RECORD_SOURCE_RE = re.compile(r"round(?:19|[2-9]\d)_staging/")

failures: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {label:44s} got={got!r:>8} record={want!r}")
    if not ok:
        failures.append(f"{label}: recomputed {got!r}, record says {want!r}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def qualifying_pages(unit: dict, *, embedded_only: bool) -> list[int]:
    """Pages carrying a crop that passes rule 3 under the given reading."""
    pages = set()
    for img in unit.get("images", []):
        if embedded_only and img.get("source") != "embedded_raster":
            continue
        if min(img["width"], img["height"]) >= CROP_FLOOR_PX:
            pages.add(img["page"])
    return sorted(pages)


def main() -> int:
    record = json.loads(DETERMINATION.read_text())
    counts = record["counts"]
    recheck = record["binding_constraint"]["counterfactual_not_adopted"]["independent_recheck"]
    claimed = recheck["reproduces"]
    r3_split = recheck["of_the_43_rule3_failures"]

    # ---- sealed frame: (source pdf sha256, page) and the crop hashes ----
    index = json.loads(DATASET_INDEX.read_text())
    doc_sha = {}
    for f in index["files"]:
        for did in f.get("frame_doc_ids") or []:
            doc_sha[did] = f["sha256"]

    sealed = json.loads(SEALED.read_text())
    sealed_pairs: set[tuple[str, int]] = set()
    sealed_crops: dict[tuple[str, int], set[str]] = {}
    for pkg in sealed["packages"]:
        ds = pkg["evidence"]["document_structure"]
        sha = doc_sha.get(ds["source_id"])
        if sha is None:
            failures.append(f"sealed source_id {ds['source_id']} unresolved in DATASET_INDEX")
            continue
        key = (sha, ds["page"])
        sealed_pairs.add(key)
        sealed_crops.setdefault(key, set()).update(
            img["sha256"] for img in pkg["evidence"].get("images", [])
        )

    print(f"sealed frame: {sealed['chunk_count']} chunks, "
          f"{len(sealed_pairs)} distinct (sha256,page) pairs")
    check("sealed_frame_n", sealed["chunk_count"], counts["sealed_frame_n"])

    # ---- load the rights-eligible units ----
    #
    # The determination measured a population that has since GROWN: round-19
    # acquisition added six textbooks after the record was written. Its counts
    # are dated evidence and are not rewritten, so the recheck must reconstruct
    # the population AS MEASURED rather than read whatever is live today:
    #
    #   * units relocated out of scope (T11, a customs textbook) were part of
    #     what the record measured, so they are folded back in;
    #   * units built from round-19 sources were NOT, so they are excluded.
    #
    # Round-19 membership is derived from each unit's own recorded source_pdf
    # path, not from a hardcoded doc-id list, so a later acquisition round under
    # the same staging convention is excluded automatically instead of silently
    # inflating the population and failing this guard.
    elig_doc = json.loads(ELIGIBLE.read_text())
    eligible = list(elig_doc["unit_ids"])
    for ids in (elig_doc.get("relocated_out_of_scope") or {}).values():
        eligible.extend(ids)
    eligible = sorted(set(eligible))

    units = []
    excluded_later_acquisition = 0
    for uid in eligible:
        doc, sec = uid.split("::")
        for root in SECTION_ROOTS:
            path = root / doc / sec / "unit.json"
            if path.exists():
                unit = json.loads(path.read_text())
                if POST_RECORD_SOURCE_RE.search(str(unit.get("source_pdf") or "")):
                    excluded_later_acquisition += 1
                else:
                    units.append(unit)
                break
        else:
            failures.append(f"missing unit record for {uid} under "
                            + " or ".join(str(r.relative_to(ROOT)) for r in SECTION_ROOTS))

    print(f"eligible units loaded: {len(units)} of {len(eligible)} "
          f"({excluded_later_acquisition} excluded as post-record acquisition)")
    check("rights_eligible_units", len(units), counts["rights_eligible_units"])

    # ---- rule 3 / rule 4 / no-reuse, under both readings ----
    results = {}
    for reading, embedded_only in (("frozen", True), ("literal", False)):
        gross, overlap, fresh = [], [], []
        for u in units:
            pages = qualifying_pages(u, embedded_only=embedded_only)
            if not pages:
                continue
            if not u["rule4_text_sufficient"]:
                continue
            gross.append(u)
            hit = [p for p in pages if (u["source_sha256"], p) in sealed_pairs]
            (overlap if hit else fresh).append((u, pages, hit))
        results[reading] = {"gross": gross, "overlap": overlap, "fresh": fresh}

    frozen = results["frozen"]
    print("\nfrozen reading (embedded rasters only, min-dim >= 203 px)")
    check("pass_rule3_and_rule4", len(frozen["gross"]), counts["pass_rule3_and_rule4"])
    check("fail_rule3", len(units) - len(frozen["gross"]), counts["fail_rule3"])
    check("overlap_with_sealed_frame", len(frozen["overlap"]), counts["overlap_with_sealed_frame"])
    check("fresh_chunks", len(frozen["fresh"]), counts["fresh_chunks"])
    check("below_floor", len(frozen["fresh"]) < counts["pre_registered_floor"],
          counts["below_floor"])

    # rule 4 must exclude nothing among rule-3 passes: verify directly
    r4_fail = sum(
        1 for u in units
        if qualifying_pages(u, embedded_only=True) and not u["rule4_text_sufficient"]
    )
    check("fail_rule4_among_rule3_ok", r4_fail, counts["fail_rule4_among_rule3_ok"])

    # ---- each overlap confirmed by crop sha256 ----
    print("\noverlap confirmation by crop sha256")
    all_confirmed = True
    for u, pages, hit in frozen["overlap"]:
        unit_hashes = {img["sha256"] for img in u["images"]}
        sealed_hashes: set[str] = set()
        for p in hit:
            sealed_hashes |= sealed_crops[(u["source_sha256"], p)]
        shared = unit_hashes & sealed_hashes
        all_confirmed &= bool(shared)
        print(f"  {'ok  ' if shared else 'FAIL'} {u['unit_id']} pages={hit} "
              f"shared_crops={len(shared)}")
    check("all_three_overlaps_confirmed_by_crop_sha256", all_confirmed,
          recheck["all_three_overlaps_confirmed_by_crop_sha256"])

    # ---- the counterfactual literal reading ----
    literal = results["literal"]
    cf = record["binding_constraint"]["counterfactual_not_adopted"]
    print("\nliteral reading (any crop on disk, min-dim >= 203 px)")
    check("would_yield_gross", len(literal["gross"]), cf["would_yield_gross"])
    check("would_yield_fresh_after_s7", len(literal["fresh"]),
          cf["would_yield_fresh_after_s7_no_reuse"])
    check("still_below_floor", len(literal["fresh"]) < counts["pre_registered_floor"],
          cf["still_below_floor"])

    # ---- how the 43 rule-3 failures split ----
    frozen_pass_ids = {u["unit_id"] for u in frozen["gross"]}
    with_render, without_render, strip_dims = 0, 0, []
    for u in units:
        if u["unit_id"] in frozen_pass_ids:
            continue
        if qualifying_pages(u, embedded_only=False):
            with_render += 1
        else:
            without_render += 1
            dims = [min(i["width"], i["height"]) for i in u["images"]]
            if dims:
                strip_dims.append(max(dims))
    print("\nsplit of the rule-3 failures")
    check("with_vector_render_ge_203px", with_render, r3_split["with_vector_render_ge_203px"])
    check("without_any_render_ge_203px", without_render, r3_split["without_any_render_ge_203px"])
    if strip_dims:
        print(f"       largest min-dimension among the {len(strip_dims)} strip-only units: "
              f"{min(strip_dims)}-{max(strip_dims)} px")

    # ---- sealed inputs unchanged ----
    print("\nsealed inputs")
    got = sha256_file(SEALED)
    check("sealed_frame_sha256", got, record["inputs"]["sealed_frame_sha256"])

    print()
    if failures:
        print(f"MISMATCH ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SECTION_FRAME_DETERMINATION.json reproduces exactly. "
          f"Frozen reading: {len(frozen['fresh'])} fresh vs floor "
          f"{counts['pre_registered_floor']}. Literal reading: "
          f"{len(literal['fresh'])} fresh, also below floor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
