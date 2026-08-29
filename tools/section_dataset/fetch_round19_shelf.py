#!/usr/bin/env python3
"""Round-19 STAGING-ONLY fetch of the law textbooks found on the Giáo trình shelf.

Input: corpus/reports/round19_shelf_discovery_*.json, whose `new_with_attachment`
list holds the shelf records that carry a downloadable file and are not already
in corpus/DATASET_INDEX.json by record uuid.

Staging only, by contract. Files land in corpus/round19_staging/pdf/ and are
described by their own report. This script does NOT touch sources.csv,
acquisition_manifest.csv, any screening register, the bundle manifest, or either
rights attestation — all five are bound by sha256 inside standing records.

Deduplication is by content, not by catalogue identity: every fetched file is
hashed and compared against every sha256 already in DATASET_INDEX.json, because
the same textbook can sit under two uuids across acquisition rounds.

Transport: the already-authenticated browser tab fetches the payload with its
own cookies and hands it back base64 in bounded slices, so no credential is
read, stored, or transmitted by this script.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_probe import Tab  # noqa: E402

SANDBOX = Path(__file__).resolve().parents[2]
CORPUS = SANDBOX / "corpus"
REPORTS = CORPUS / "reports"
INDEX = CORPUS / "DATASET_INDEX.json"
STAGING = CORPUS / "round19_staging"
ORIGIN = "https://library.hul.edu.vn"

SLICE = 1 << 20  # 1 MiB of raw bytes per CDP round trip

FETCH_JS = r"""
(async (u) => {
  try {
    const r = await fetch(u, {credentials:'include', redirect:'follow'});
    if (!r.ok) return {error:'HTTP ' + r.status};
    const b = new Uint8Array(await r.arrayBuffer());
    window.__dl = b;
    return {status:r.status, bytes:b.byteLength,
            ct:r.headers.get('content-type')||'',
            magic:Array.from(b.slice(0,8)).map(c=>String.fromCharCode(c)).join('')};
  } catch(e) { return {error:String(e)}; }
})(%s)
"""

SLICE_JS = r"""
(() => {
  const b = window.__dl.subarray(%d, %d);
  let s = '';
  const CH = 0x8000;
  for (let i = 0; i < b.length; i += CH)
    s += String.fromCharCode.apply(null, b.subarray(i, i + CH));
  return btoa(s);
})()
"""


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFD", title.lower())
    s = "".join(c for c in s if not unicodedata.combining(c)).replace("đ", "d")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:70] or "untitled"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def latest_discovery() -> Path:
    cands = sorted(REPORTS.glob("round19_shelf_discovery_*.json"))
    if not cands:
        raise SystemExit("no round-19 shelf discovery report found")
    return cands[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write files; else list only")
    ap.add_argument("--discovery", default=None)
    args = ap.parse_args()

    disc_path = Path(args.discovery) if args.discovery else latest_discovery()
    disc = json.loads(disc_path.read_text("utf-8"))
    targets = disc["new_with_attachment"]

    index = json.loads(INDEX.read_text("utf-8"))
    held_hashes = {f["sha256"]: f["primary_copy"] for f in index["files"]}

    print(f"discovery   {disc_path.relative_to(SANDBOX)}")
    print(f"shelf       {disc['method']['filter']['resourceCollection']}")
    print(f"candidates  {len(targets)} new records carrying a file")
    print(f"holdings    {len(held_hashes)} distinct sha256 to dedup against")
    for rec in targets:
        print(f"  - {rec['title'][:66]}  files={rec['attachment_count']}")

    if not args.apply:
        print("\ndry run; pass --apply to fetch into staging")
        return 0

    pdf_dir = STAGING / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    t = Tab().connect()

    records, staged, dupes, failed = [], 0, 0, 0
    for n, rec in enumerate(targets, 1):
        # Prefer the CatalogData attachment; it is the content file, while a
        # `source=File` sibling is the catalogue's own attachment record.
        urls = sorted(rec["attachment_urls"],
                      key=lambda u: 0 if "source=CatalogData" in u else 1)
        entry = {"title": rec["title"], "record_uuid": rec["record_uuid"],
                 "attachment_urls": urls, "outcome": None}
        got = None
        for url in urls:
            head = t.js(FETCH_JS % json.dumps(ORIGIN + url))
            if not isinstance(head, dict) or head.get("error"):
                entry.setdefault("errors", []).append(
                    {"url": url, "error": (head or {}).get("error", "no response")})
                continue
            if head.get("magic", "")[:4] != "%PDF":
                entry.setdefault("errors", []).append(
                    {"url": url, "error": f"not a PDF (magic {head.get('magic','')!r})"})
                continue
            total = head["bytes"]
            chunks = []
            for off in range(0, total, SLICE):
                b64 = t.js(SLICE_JS % (off, min(off + SLICE, total)))
                if not isinstance(b64, str):
                    chunks = []
                    break
                chunks.append(base64.b64decode(b64))
            data = b"".join(chunks)
            if len(data) != total:
                entry.setdefault("errors", []).append(
                    {"url": url, "error": f"short read {len(data)} of {total}"})
                continue
            got = (url, data, head)
            break

        if got is None:
            entry["outcome"] = "FETCH_FAILED"
            failed += 1
            print(f"  [{n}/{len(targets)}] FAILED  {rec['title'][:52]}")
            records.append(entry)
            continue

        url, data, head = got
        digest = sha256_bytes(data)
        entry.update({"fetched_from": url, "bytes": len(data), "sha256": digest,
                      "content_type": head.get("ct", ""),
                      "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

        if digest in held_hashes:
            entry["outcome"] = "DUPLICATE_NOT_STAGED"
            entry["identical_to"] = held_hashes[digest]
            dupes += 1
            print(f"  [{n}/{len(targets)}] dup     {rec['title'][:52]}")
            print(f"              == {held_hashes[digest]}")
            records.append(entry)
            continue

        name = f"R19_{n:03d}_{slugify(rec['title'])}.pdf"
        (pdf_dir / name).write_bytes(data)
        entry["outcome"] = "STAGED"
        entry["staged_path"] = f"round19_staging/pdf/{name}"
        try:
            import pymupdf
            with pymupdf.open(pdf_dir / name) as doc:
                entry["pages"] = doc.page_count
                entry["text_layer"] = any(
                    doc[i].get_text("text").strip() for i in range(min(6, doc.page_count)))
        except Exception as exc:  # pragma: no cover
            entry["pages_error"] = str(exc)
        staged += 1
        held_hashes[digest] = entry["staged_path"]
        print(f"  [{n}/{len(targets)}] staged  {rec['title'][:52]}")
        print(f"              {name}  {len(data):,}B  "
              f"{entry.get('pages','?')}pp  text={entry.get('text_layer')}")
        records.append(entry)

    t.close()

    report = {
        "schema": "ecm-tqag.framec-round19-shelf-staging-fetch.v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": ("STAGING-ONLY fetch into round19_staging/. No promotion; "
                  "sources.csv, acquisition_manifest.csv, every screening "
                  "register, the bundle manifest and both rights attestations "
                  "are untouched."),
        "owner_scope": "law textbooks (giáo trình luật) from the HUL catalogue",
        "discovery_basis": str(disc_path.relative_to(SANDBOX)),
        "shelf": disc["method"]["filter"]["resourceCollection"],
        "deduplication": ("by content sha256 against every file in "
                          "DATASET_INDEX.json, not by catalogue uuid, because "
                          "one textbook can sit under two uuids across rounds"),
        "counts": {"candidates": len(targets), "staged": staged,
                   "duplicates_not_staged": dupes, "failed": failed},
        "open_gates": [
            "rights: each staged file must be checked for the pdfinfo copy "
            "prohibition (rule 1) before any unit built from it is eligible",
            "screening: figure-region screening has not run on these files",
            "promotion: none are in sources.csv or the acquisition manifest",
        ],
        "records": records,
    }
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = REPORTS / f"round19_shelf_staging_fetch_{ts}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    print(f"\nstaged {staged}   duplicates {dupes}   failed {failed}")
    print(f"report: {out.relative_to(SANDBOX)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
