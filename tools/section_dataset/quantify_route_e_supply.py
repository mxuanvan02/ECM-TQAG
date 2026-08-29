#!/usr/bin/env python3
"""Quantify route E: can further acquisition reach the round-4 floor of 40?

SECTION_FRAME_DETERMINATION.json left route E ("further acquisition from the
catalogue") with n=null, unenumerable. It is enumerable to an order of
magnitude, because round-18 paginated discovery read the catalogue to
END_OF_RESULTS on the three keyword families that carry attachments, so the
remaining *supply* is countable even though its page counts are not yet known.

Demand and supply are put on a per-PAGE basis, not per-document. A per-document
yield does not transfer between classes: frame C's 0.686 chunks/doc was measured
on documents averaging 193 pages, while the unheld article supply has a median
of 94 pages, so a per-doc rate overstates yield roughly twofold.

Read-only unless --emit, which patches an additive `route_e_supply` block into
the determination record and rewrites route E's verdict from "unknown" to the
measured estimate.

Inputs, all existing records:
  corpus/reports/round18_wide_discovery.json   catalogue supply, read to END_OF_RESULTS
  corpus/DATASET_INDEX.json                    what is already held, with page counts
  experiment/dataset_framec/dataset_manifest_rule4_20260816T105100Z.json
  corpus/reports/SECTION_FRAME_DETERMINATION.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import unicodedata
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]

DETERMINATION = SANDBOX / "corpus/reports/SECTION_FRAME_DETERMINATION.json"
DISCOVERY = SANDBOX / "corpus/reports/round18_wide_discovery.json"
INDEX = SANDBOX / "corpus/DATASET_INDEX.json"

# Measured, from sealed records.
FRAMEC_DOCS = 35          # documents screened for frame C
FRAMEC_PAGES = 6758       # their total pages
FRAMEC_CHUNKS = 24        # chunks the frozen rules admitted
SECTION_DOCS = 20         # law textbooks screened for the section dataset
SECTION_PAGES = 8358
SECTION_FRESH = 14        # fresh chunks under the frozen rule 3

FLOOR = 40
TARGET = 46
IN_HAND = 14              # route A, admissible and already materialised

# Rights rule 1 (pdfinfo copy:no) removed 1 of the 20 textbooks.
COPY_NO_RATE = 1 / 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def classify(title: str) -> str:
    t = fold(title)
    if t.startswith("gt ") or "giao trinh" in t:
        return "law_textbook"
    if "bai giang" in t or t.startswith("tbg") or t.startswith("bg "):
        return "lecture_pack"
    if "ky yeu" in t or "hoi thao" in t:
        return "proceedings"
    return "article_or_other"


def held_uuids(index: dict) -> set[str]:
    out: set[str] = set()
    for f in index["files"]:
        for url in f.get("source_urls") or []:
            for key in ("originUuid=", "fileUuid="):
                for tok in url.split(key)[1:]:
                    out.add(tok.split("&")[0])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--emit", action="store_true",
                    help="patch route_e_supply into the determination record")
    args = ap.parse_args()

    index = json.loads(INDEX.read_text("utf-8"))
    pool = json.loads(DISCOVERY.read_text("utf-8"))["pool"]
    held = held_uuids(index)

    pages_by_class: dict[str, list[int]] = collections.defaultdict(list)
    for f in index["files"]:
        if f.get("title") and f.get("pages"):
            pages_by_class[classify(f["title"])].append(int(f["pages"]))

    supply: collections.Counter = collections.Counter()
    for rec in pool:
        if not rec.get("attachment_urls"):
            continue
        if rec["record_uuid"] in held:
            continue
        supply[classify(rec["title"])] += 1

    rate_framec = FRAMEC_CHUNKS / FRAMEC_PAGES
    rate_textbook = SECTION_FRESH / SECTION_PAGES

    print("rates, measured per page (the size-invariant basis)")
    print(f"  frame C non-textbook : {FRAMEC_CHUNKS}/{FRAMEC_PAGES} pp"
          f" = {rate_framec*100:.3f} per 100 pp   ({FRAMEC_PAGES/FRAMEC_DOCS:.0f} pp/doc)")
    print(f"  law textbooks        : {SECTION_FRESH}/{SECTION_PAGES} pp"
          f" = {rate_textbook*100:.3f} per 100 pp   ({SECTION_PAGES/SECTION_DOCS:.0f} pp/doc)")
    print()

    print("remaining catalogue supply (attachment-bearing, not already held)")
    est: dict[str, dict] = {}
    for cls in sorted(supply, key=lambda c: -supply[c]):
        n = supply[cls]
        held_pages = pages_by_class.get(cls) or []
        median_pp = statistics.median(held_pages) if held_pages else None
        rate = rate_textbook if cls == "law_textbook" else rate_framec
        if median_pp is None:
            print(f"  {cls:18s} n={n:3d}   no held page counts for this class, not estimable")
            continue
        usable_pp = n * median_pp * (1 - COPY_NO_RATE)
        chunks = usable_pp * rate
        est[cls] = {
            "records_available": n,
            "median_pages_of_held_files_in_class": median_pp,
            "held_files_measured": len(held_pages),
            "usable_pages_after_copy_no": round(usable_pp),
            "rate_per_100_pages": round(rate * 100, 3),
            "estimated_chunks": round(chunks, 1),
        }
        print(f"  {cls:18s} n={n:3d}  median {median_pp:5.0f} pp"
              f"  ->  {usable_pp:7.0f} usable pp  ->  ~{chunks:5.1f} chunks")

    total = sum(v["estimated_chunks"] for v in est.values())
    print(f"  {'TOTAL':18s}                               "
          f"          ~{total:5.1f} chunks if the catalogue is exhausted")
    print()

    print(f"demand, on top of the {IN_HAND} admissible chunks already in hand")
    verdicts = {}
    for need_to, label in ((FLOOR, "floor"), (TARGET, "target")):
        need = need_to - IN_HAND
        reachable = total >= need
        margin = total - need
        verdicts[label] = {
            "n": need_to,
            "additional_chunks_needed": need,
            "estimated_available": round(total, 1),
            "reachable": bool(reachable),
            "margin_chunks": round(margin, 1),
        }
        print(f"  {label} {need_to}: need {need} more, ~{total:.1f} estimated available"
              f"  ->  {'reachable' if reachable else 'NOT reachable'}"
              f"  (margin {margin:+.1f})")
    print()

    caveats = [
        "Page counts of unfetched records are unknown; the class median of already-held "
        "files is imputed. Article page counts range 7-802 in the held sample, so the "
        "estimate is order-of-magnitude, not a projection.",
        "The frame-C rate of 0.355 chunks/100 pp is conditional on the screening that "
        "produced frame C: its 35 documents were themselves picked as figure-bearing "
        "candidates. Applied to an unscreened pool the rate is optimistic, so the "
        "article_or_other estimate is an upper bound.",
        "The copy:no deduction is 1 of 20 observed in one class; it is not a measured "
        "rate for the article class.",
        "Reaching the floor consumes essentially the whole remaining attachment-bearing "
        "catalogue, leaving nothing for a later round and no margin for rule-3 or rule-4 "
        "attrition.",
        "Yield is not the only gate: the round-4 addendum's own caution is that this "
        "document class has figures the text already restates, so admitted chunks may "
        "still not move judged visual necessity.",
    ]
    print("caveats")
    for c in caveats:
        print(f"  - {c}")
    print()

    conclusion = (
        f"Route E is quantifiable and it is marginal at best. Exhausting every "
        f"attachment-bearing catalogue record not already held ({sum(supply.values())} "
        f"records) yields an estimated ~{total:.0f} further chunks, against the {FLOOR - IN_HAND} "
        f"needed to reach the floor of {FLOOR} and the {TARGET - IN_HAND} needed to reach the "
        f"target of {TARGET}. The floor is therefore reachable only by consuming the entire "
        f"remaining catalogue with no margin, on an estimate whose dominant term "
        f"(article_or_other) is an acknowledged upper bound; the target of {TARGET} is not "
        f"reachable from this catalogue at all. This supersedes the earlier per-document "
        f"reading of the same records, which called the floor comfortably feasible."
    )
    print("conclusion")
    print(f"  {conclusion}")

    if args.emit:
        det = json.loads(DETERMINATION.read_text("utf-8"))
        det["route_e_supply"] = {
            "what": ("Quantification of route E (further acquisition), which the routes block "
                     "left as n=null. Demand and supply are compared per page, not per document."),
            "script": "corpus/scripts/quantify_route_e_supply.py",
            "inputs": {
                "catalogue_supply": "corpus/reports/round18_wide_discovery.json",
                "catalogue_supply_sha256": sha256_file(DISCOVERY),
                "supply_completeness": ("round-18 read all three attachment-bearing keyword "
                                        "families to END_OF_RESULTS (giao trinh 319, bai giang 76, "
                                        "tap bai giang 68; pool 391 distinct records)"),
                "holdings": "corpus/DATASET_INDEX.json",
                "holdings_sha256": sha256_file(INDEX),
            },
            "rates_measured_per_page": {
                "frame_c_non_textbook": {
                    "chunks": FRAMEC_CHUNKS, "pages": FRAMEC_PAGES,
                    "per_100_pages": round(rate_framec * 100, 3),
                    "pages_per_doc": round(FRAMEC_PAGES / FRAMEC_DOCS),
                },
                "law_textbook_section_corpus": {
                    "fresh_chunks": SECTION_FRESH, "pages": SECTION_PAGES,
                    "per_100_pages": round(rate_textbook * 100, 3),
                    "pages_per_doc": round(SECTION_PAGES / SECTION_DOCS),
                },
                "why_per_page": ("A per-document rate does not transfer between classes: frame C's "
                                 "0.686 chunks/doc was measured at ~193 pp/doc, while the unheld "
                                 "article supply has median 94 pp, so a per-doc rate overstates "
                                 "yield about twofold."),
            },
            "supply_not_held": {
                "attachment_bearing_records_not_held": sum(supply.values()),
                "by_class": dict(supply),
                "estimates": est,
                "estimated_total_chunks_if_exhausted": round(total, 1),
            },
            "demand": verdicts,
            "chunks_in_hand": IN_HAND,
            "caveats": caveats,
            "conclusion": conclusion,
            "supersedes_within_this_session": {
                "claim": ("an earlier per-document reading of these same records reported the floor "
                          "as FEASIBLE (38 documents required against 76 available)"),
                "why_wrong": ("it applied frame C's 0.686 chunks/doc to records whose median length "
                              "is half that of the documents the rate was measured on"),
                "corrected_to": "marginal, and only by exhausting the catalogue",
            },
        }
        routes = det.get("routes_to_the_floor", {}).get("routes", [])
        for r in routes:
            if r.get("id") == "E":
                r["n"] = round(IN_HAND + total, 1)
                r["n_note"] = (f"~{total:.0f} estimated further chunks if the entire remaining "
                               f"attachment-bearing catalogue is fetched and screened, plus the "
                               f"{IN_HAND} in hand; see route_e_supply for the derivation and its caveats")
                r["reaches_floor"] = "marginally, and only by exhausting the catalogue"
                r["verdict"] = (f"open but marginal: ~{total:.0f} further chunks available against "
                                f"{FLOOR - IN_HAND} needed for the floor and {TARGET - IN_HAND} for the "
                                f"target, on an estimate whose dominant term is an upper bound; the "
                                f"target of {TARGET} is not reachable from this catalogue")
        DETERMINATION.write_text(json.dumps(det, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print()
        print(f"patched route_e_supply into {DETERMINATION.relative_to(SANDBOX)}")
        print("new sha256:", sha256_file(DETERMINATION))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
