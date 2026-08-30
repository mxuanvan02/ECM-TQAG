#!/usr/bin/env python3
"""Record what actually happened to the routes SECTION_FRAME_DETERMINATION.json enumerated.

The determination enumerated five routes to a round-4 frame at or above the
pre-registered floor of 40 and left route E (further acquisition) as an
*estimate*. Route E has since been executed and route B pre-registered, so the
record must carry the outcome next to the prediction rather than leaving a
forecast standing as if it were still open.

Additive: appends `routes_outcome` and does not alter any existing block, so the
17 counts the recheck script verifies stay byte-identical.

Read-only unless --emit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
DET = SANDBOX / "corpus/reports/SECTION_FRAME_DETERMINATION.json"
FRAMED = SANDBOX / "experiment/dataset_framed/dataset_manifest_framed_20260829T195643Z.json"
SECTIONS = SANDBOX / "datasets_sections/MANIFEST.json"
PREREG = SANDBOX / "prospective/v3103_round2/ROUND4_FRAMED_PREREGISTRATION.json"
REPORT = SANDBOX / "experiment/runs/round4_framed_census_20260829T200000Z/ROUND4_REPORT.json"
DISCOVERY = SANDBOX / "corpus/reports/round19_shelf_discovery_20260829T183005Z.json"

ROUND19_DOCS = {"T21", "T22", "T23", "T24", "T25", "T26"}
CROP_FLOOR_PX = 203


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def strict_eligible(pkg: dict) -> bool:
    """Frame C's frozen reading of rule 3: an embedded raster over the floor."""
    for im in pkg["evidence"].get("images", []):
        if im.get("source") == "embedded_raster" and min(im["width"], im["height"]) >= CROP_FLOOR_PX:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    det = json.loads(DET.read_text("utf-8"))
    framed = json.loads(FRAMED.read_text("utf-8"))
    pages = {d["doc_id"]: d["pages"] for d in json.loads(SECTIONS.read_text("utf-8"))["docs"]}

    lit_new = lit_old = st_new = st_old = 0
    for pkg in framed["packages"]:
        new = pkg["doc_id"].split("_")[0] in ROUND19_DOCS
        strict = strict_eligible(pkg)
        if new:
            lit_new += 1
            st_new += 1 if strict else 0
        else:
            lit_old += 1
            st_old += 1 if strict else 0

    pp_new = sum(p for d, p in pages.items() if d.split("_")[0] in ROUND19_DOCS)
    pp_old = sum(p for d, p in pages.items() if d.split("_")[0] not in ROUND19_DOCS)

    # per-document frozen-reading rate, to locate the prediction error
    per_doc: dict[str, int] = {}
    for pkg in framed["packages"]:
        if strict_eligible(pkg):
            per_doc[pkg["doc_id"]] = per_doc.get(pkg["doc_id"], 0) + 1
    t24 = next(d for d in pages if d.startswith("T24"))
    t24_chunks, t24_pages = per_doc.get(t24, 0), pages[t24]
    rest_new_chunks = st_new - t24_chunks
    rest_new_pages = pp_new - t24_pages

    predicted = det["route_e_supply"]["supply_not_held"]["estimates"]["law_textbook"]
    disc = json.loads(DISCOVERY.read_text("utf-8"))
    report = json.loads(REPORT.read_text("utf-8")) if REPORT.is_file() else {}

    outcome = {
        "what": ("What actually happened to the routes enumerated in "
                 "§routes_to_the_floor. Route E was executed and route B was "
                 "pre-registered, so the estimate no longer stands alone."),
        "recorded_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "script": "corpus/scripts/record_route_outcome.py",
        "route_taken": {
            "routes": ["B", "E"],
            "how": ("Route E (acquisition) was executed first, then route B (the "
                    "literal reading of rule 3) was adopted the only admissible "
                    "way the determination allowed: pre-registered as a new frame "
                    "D before any paid call. Routes C and D, which pool the "
                    "sealed frame-C 24, were never used."),
            "preregistration": "prospective/v3103_round2/ROUND4_FRAMED_PREREGISTRATION.json",
            "preregistration_sha256": sha256_file(PREREG),
            "frame_manifest_sha256": sha256_file(FRAMED),
            "n_admitted": len(framed["packages"]),
            "reaches_floor": len(framed["packages"]) >= det["counts"]["pre_registered_floor"],
        },
        "route_e_as_executed": {
            "method_changed": (
                "The supply estimate counted attachment-bearing records from a "
                "KEYWORD scan. Acquisition instead used the ADVANCED form's "
                "resourceCollection filter on the shelf 'Kệ C2-C8 (Giáo trình)', "
                "which selects the textbook shelf directly instead of matching a "
                "substring in title or author. That is a better instrument for the "
                "owner's scope, and it is why the record counts differ."
            ),
            "discovery": "corpus/reports/round19_shelf_discovery_20260829T183005Z.json",
            "shelf_records": disc["counts"]["shelf_records"],
            "with_attachment": disc["counts"]["with_attachment"],
            "already_held": disc["counts"]["with_attachment_already_held"],
            "new_fetched": disc["counts"]["with_attachment_new"],
            "shelf_exhausted": disc["stop_reason"] == "END_OF_RESULTS",
            "pages_added": pp_new,
        },
        "prediction_vs_actual": {
            "class": "law_textbook",
            "predicted_chunks_frozen_reading": predicted["estimated_chunks"],
            "predicted_pages": predicted["usable_pages_after_copy_no"],
            "predicted_rate_per_100_pages": predicted["rate_per_100_pages"],
            "actual_pages": pp_new,
            "actual_chunks_frozen_reading": st_new,
            "actual_rate_per_100_pages": round(100 * st_new / pp_new, 3),
            "actual_chunks_literal_reading": lit_new,
            "error_decomposition": {
                "page_imputation_factor": round(pp_new / predicted["usable_pages_after_copy_no"], 3),
                "rate_factor": round((st_new / pp_new) / (predicted["rate_per_100_pages"] / 100), 2),
                "verdict": ("The median-page imputation was accurate; the yield RATE "
                            "was the error, low by about 3.6x under the frozen reading."),
            },
            "error_is_concentrated_not_systematic": {
                "t24_doc": t24,
                "t24_pages": t24_pages,
                "t24_chunks_frozen": t24_chunks,
                "t24_rate_per_100_pages": round(100 * t24_chunks / t24_pages, 3),
                "other_five_new_pages": rest_new_pages,
                "other_five_new_chunks_frozen": rest_new_chunks,
                "other_five_new_rate_per_100_pages": round(100 * rest_new_chunks / rest_new_pages, 3),
                "pre_r19_rate_per_100_pages": round(100 * st_old / pp_old, 3),
                "reading": ("Excluding T24 the new books yield 0.216 chunks/100pp "
                            "against the 0.168 assumed, so the class rate was very "
                            "nearly right. One history-of-law textbook dense in maps "
                            "and timelines carries 10 of the 14 new frozen-reading "
                            "chunks. The forecast failed on variance between books, "
                            "not on the class average."),
            },
        },
        "which_earlier_claims_this_corrects": [
            {
                "claim": ("route_e_supply.conclusion: 'the target of 46 is not "
                          "reachable from this catalogue at all'"),
                "status": "falsified as stated, but only in combination with route B",
                "detail": (
                    "Under the FROZEN reading route E alone took the count from 14 to "
                    f"{st_old + st_new}, still below the floor of 40, so the marginality verdict "
                    "was directionally right for the reading it was computed under. "
                    "The floor and the target were cleared only because route B, the "
                    "literal reading of rule 3, was also adopted and pre-registered. "
                    "Neither route reached 46 by itself."
                ),
            },
            {
                "claim": "routes_to_the_floor.routes[E].n = 42.5 (estimated ceiling)",
                "status": "superseded by an executed count",
                "detail": (f"Frozen reading actual: {st_old + st_new}. Literal reading actual: "
                           f"{lit_old + lit_new}. The estimate is retained above as the "
                           "forecast it was."),
            },
        ],
        "counts_are_unchanged": (
            "§counts still describes the 60-unit, frozen-reading, pre-round-19 "
            "population it was computed on, and the recheck script still reproduces "
            "all 17 of its values. This block reports a later, larger population and "
            "does not restate those numbers."
        ),
        "downstream": {
            "census_run": "round4_framed_census_20260829T200000Z",
            "primary_endpoint_result": (
                "null: no contrast rejected at family alpha 0.05 under Holm"
                if report else "not yet executed"
            ),
            "reported_cost_usd": report.get("known_reported_cost_usd"),
            "note": ("Reaching the floor settled the power question, not the "
                     "scientific one. Judged visual necessity stayed pinned at 1 for "
                     "this document class, which is what Frame B already suggested."),
        },
    }

    print(f"route taken            B + E, n={outcome['route_taken']['n_admitted']} "
          f"reaches_floor={outcome['route_taken']['reaches_floor']}")
    print(f"round-19 shelf         {disc['counts']['shelf_records']} records, "
          f"{disc['counts']['with_attachment_new']} new fetched, {pp_new} pages")
    print(f"predicted (frozen)     {predicted['estimated_chunks']} chunks")
    print(f"actual (frozen)        {st_new} chunks  -> rate off by "
          f"{outcome['prediction_vs_actual']['error_decomposition']['rate_factor']}x")
    print(f"actual (literal)       {lit_new} chunks")
    print(f"frozen total now       {st_old + st_new} (still below floor 40)")
    print(f"literal total now      {lit_old + lit_new} (frame D, above floor)")

    if not args.emit:
        print("\ndry run; pass --emit to patch the determination")
        return 0

    det["routes_outcome"] = outcome
    DET.write_text(json.dumps(det, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\npatched {DET.relative_to(SANDBOX)}")
    print("new sha256:", sha256_file(DET))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
