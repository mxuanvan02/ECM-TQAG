#!/usr/bin/env python3
r"""Round-19 discovery: enumerate the textbook shelf, not a keyword match.

WHY THIS SUPERSEDES ROUNDS 16-18
--------------------------------
Rounds 16, 17 and 18 searched the OPAC in BASIC/KEYWORD mode for the string
"giao trinh". The owner identified the defect: that mode matches only the
catalogue's author and title indexes, so it finds a textbook when the words
"Giáo trình" happen to appear in its NAME, and misses every textbook titled
otherwise. It also returns any article whose title mentions teaching, which is
why the round-18 pool of 391 was mostly not textbooks at all.

The catalogue already classifies its own holdings by physical shelf. The
ADVANCED form exposes a `resourceCollection` select whose options are the
shelves, one of which is:

    Kệ C2-C8 (Giáo trình)        # the textbook shelves

Selecting that shelf with an EMPTY query term enumerates the textbook holding
as the library itself defines it. That is a membership filter over a curated
collection, not a substring test over two indexes, so it is the correct frame
for the question "how many textbooks does this library hold".

Measured difference: keyword "giao trinh" reported 319 rows, of which 278 had
textbook-looking titles; the shelf reports 49. The two are answering different
questions and the shelf is the one that matches the owner's scope.

Read-only by contract: drives an already-open authenticated tab, reads rows,
writes one JSON report. No download, no staging, no promotion, no mutation of
sources.csv, acquisition_manifest.csv, any register, the bundle manifest or the
rights attestation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_probe import Tab  # noqa: E402

SANDBOX = Path(__file__).resolve().parents[2]
INDEX = SANDBOX / "corpus/DATASET_INDEX.json"

ADVANCED = ("https://library.hul.edu.vn/liberty/opac/search.do"
            "?corporation=Liberty&mode=ADVANCED")

# The shelf whose label the library uses for textbooks.
SHELF_LABEL = "Kệ C2-C8 (Giáo trình)"

STATE_JS = r"""
(() => {
  const c=document.querySelector('#opacSearchResults');
  const txt=c?(c.innerText||''):'';
  const msg=(document.querySelector('#navigationMessage')?.innerText||'');
  const m=(msg+' '+txt).match(/([\d.,]+)\s*-\s*([\d.,]+)\s+of\s+([\d.,]+)/i);
  const num=s=>s===undefined?null:parseInt(String(s).replace(/[.,\s]/g,''),10);
  return {loading:/vui l\u00F2ng \u0111\u1EE3i|please wait/i.test(txt),
          rows:document.querySelectorAll('tr.opacResultRow').length,
          from:m?num(m[1]):null, to:m?num(m[2]):null, total:m?num(m[3]):null,
          navmsg:msg.replace(/\s+/g,' ').trim().slice(0,120)};
})()
"""

SCAN_JS = r"""
(() => Array.from(document.querySelectorAll('tr.opacResultRow')).map(row => {
  const a=row.querySelector('a.opac[onclick*="openDetail"]');
  const oc=a?(a.getAttribute('onclick')||''):'';
  const um=oc.match(/openDetail\(['"]([^'"]+)/);
  const files=Array.from(row.querySelectorAll('button[onclick*="FileServlet"]')).map(b=>{
    const h=b.getAttribute('onclick')||'';
    const mm=h.match(/['"]([^'"]*FileServlet[^'"]*)['"]/);
    return mm?mm[1].replace(/&amp;/g,'&'):'';
  }).filter(u=>u&&u.includes('originType=file'));
  return {title:(a?a.innerText:'').replace(/\s+/g,' ').trim(),
          record_uuid:um?um[1]:'',
          attachment_urls:Array.from(new Set(files)),
          row_text:(row.innerText||'').replace(/\s+/g,' ').trim().slice(0,300)};
}))()
"""

NEXT_JS = r"""
(() => {
  const bs=Array.from(document.querySelectorAll('button[onclick*="navigateList"]'));
  const nx=bs.find(b=>/Trang ti\u1EBFp theo|Next page/i.test(b.getAttribute('title')||''));
  if(!nx) return 'NO_NEXT';
  if(nx.disabled===true||nx.classList.contains('disabled')) return 'DISABLED';
  nx.click(); return 'CLICKED';
})()
"""

AUTH_JS = r"""
(() => {const t=document.body?(document.body.innerText||''):'';
  return {logout:/\u0110\u0103ng xu\u1EA5t|Log ?out/i.test(t),
          login:/\u0110\u0103ng nh\u1EADp|Log ?in/i.test(t)};})()
"""

SHELVES_JS = r"""
(() => {const s=document.querySelector('[name=resourceCollection]');
  return s?Array.from(s.options).map(o=>(o.textContent||'').trim()):[];})()
"""

SET_SHELF_JS = r"""
((label) => {
  const sel=document.querySelector('[name=resourceCollection]');
  if(!sel) return 'NO_SELECT';
  let hit=null;
  for(const o of sel.options){ if((o.textContent||'').trim()===label){ hit=o; break; } }
  if(!hit) return 'NO_OPTION';
  sel.value=hit.value;
  sel.dispatchEvent(new Event('change',{bubbles:true}));
  const q=document.querySelector('#searchForm [name=queryTerm]');
  if(q) q.value='';           // empty query: the shelf IS the filter
  return {set:hit.value};
})(%s)
"""

SUBMIT_JS = r"""
(() => {
  const f=document.querySelector('#searchForm');
  if(!f) return 'NO_FORM';
  const a=f.querySelector('[name=action]'); if(a) a.value='search';
  const b=document.querySelector('#submitSearchButton');
  if(b){ b.click(); return 'CLICKED'; }
  f.submit(); return 'SUBMITTED';
})()
"""


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s.replace("đ", "d")).strip()


def settle(t: Tab, deadline: float = 30.0) -> dict:
    end = time.time() + deadline
    last: dict = {}
    while time.time() < end:
        st = t.js(STATE_JS) or {}
        last = st
        if not st.get("loading") and st.get("rows"):
            return st
        time.sleep(0.4)
    return last


def advance(t: Tab, prev_from, deadline: float = 30.0) -> tuple[str, dict]:
    r = t.js(NEXT_JS)
    if r != "CLICKED":
        return r, {}
    end = time.time() + deadline
    while time.time() < end:
        time.sleep(0.35)
        st = t.js(STATE_JS) or {}
        if st.get("loading") or not st.get("rows"):
            continue
        if st.get("from") != prev_from:
            return "MOVED", st
    return "STALLED", (t.js(STATE_JS) or {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shelf", default=SHELF_LABEL)
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    t = Tab().connect()
    t.navigate(ADVANCED, settle=2.5)
    t.js("(()=>{const x=document.querySelector('#searchmode_ADVANCED'); if(x) x.click(); return 1;})()")
    time.sleep(1.5)

    auth = t.js(AUTH_JS) or {}
    shelves = t.js(SHELVES_JS) or []
    if a.shelf not in shelves:
        raise SystemExit(f"shelf {a.shelf!r} not offered; available: {shelves}")

    set_res = t.js(SET_SHELF_JS % json.dumps(a.shelf, ensure_ascii=False))
    if not isinstance(set_res, dict):
        raise SystemExit(f"could not select the shelf: {set_res}")
    submit = t.js(SUBMIT_JS)
    time.sleep(2.0)
    st = settle(t)
    if not st.get("rows"):
        raise SystemExit(f"shelf query returned no rows: {st}")

    seen: dict[str, dict] = {}
    pages = 0
    stop = None
    while pages < a.max_pages:
        for x in (t.js(SCAN_JS) or []):
            if x.get("record_uuid"):
                seen.setdefault(x["record_uuid"], x)
        pages += 1
        now = t.js(STATE_JS) or {}
        to, total = now.get("to"), now.get("total")
        print(f"  page {pages:2d}  rows={len(seen):3d}  {now.get('navmsg','')}",
              flush=True)
        if to is not None and total is not None and to >= total:
            stop = "END_OF_RESULTS"
            break
        verdict, _ = advance(t, now.get("from"))
        if verdict != "MOVED":
            stop = verdict
            break
    else:
        stop = "PAGE_CAP"

    reported_total = (t.js(STATE_JS) or {}).get("total")
    t.close()

    for v in seen.values():
        v["attachment_count"] = len(v.get("attachment_urls") or [])
        v["is_giao_trinh_title"] = "giao trinh" in fold(v["title"])

    # ---- compare against what is already held --------------------------
    index = json.loads(INDEX.read_text("utf-8"))
    held_uuids: set[str] = set()
    held_titles: list[set[str]] = []
    for f in index["files"]:
        for url in f.get("source_urls") or []:
            for m in re.finditer(r"[?&](?:originUuid|fileUuid)=([0-9a-f]{32})", url):
                held_uuids.add(m.group(1))
        for rec in f.get("fetch_records") or []:
            for m in re.finditer(r"([0-9a-f]{32})", json.dumps(rec)):
                held_uuids.add(m.group(1))
        if f.get("title"):
            held_titles.append(set(fold(f["title"]).split()))

    def title_dupe(title: str) -> bool:
        toks = set(fold(title).split())
        if not toks:
            return False
        return any(len(toks & h) / max(1, min(len(toks), len(h))) >= 0.8
                   for h in held_titles if h)

    for v in seen.values():
        uuids = {v["record_uuid"]} | {
            m.group(1) for u in (v.get("attachment_urls") or [])
            for m in re.finditer(r"[?&](?:originUuid|fileUuid)=([0-9a-f]{32})", u)}
        v["already_held_by_uuid"] = bool(uuids & held_uuids)
        v["title_duplicate_of_held"] = title_dupe(v["title"])
        v["is_new"] = not (v["already_held_by_uuid"] or v["title_duplicate_of_held"])

    pool = list(seen.values())
    with_att = [v for v in pool if v["attachment_count"]]
    new_with_att = [v for v in with_att if v["is_new"]]

    rep = {
        "schema": "ecm-tqag.framec-round19-shelf-discovery.v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": ("READ-ONLY paginated enumeration of one catalogue SHELF. No "
                  "download, staging, promotion, or manifest mutation."),
        "supersedes": {
            "paths": [
                "corpus/reports/round17_paginated_discovery_20260828T085139Z.json",
                "corpus/reports/round18_wide_discovery.json",
            ],
            "reason": (
                "Those rounds searched BASIC/KEYWORD for the string 'giao trinh'. "
                "That mode matches the author and title indexes only, so it finds "
                "a textbook only when 'Giáo trình' appears in its name and returns "
                "unrelated articles whose titles mention teaching. Membership of "
                "the library's own textbook shelf is the correct filter for a "
                "textbook-scoped dataset."
            ),
        },
        "method": {
            "mode": "ADVANCED",
            "filter": {"resourceCollection": a.shelf, "queryTerm": ""},
            "why_empty_query": (
                "the shelf is the filter; any query term would re-impose the "
                "author/title substring test this round exists to avoid"),
            "pagination": ("in-page click on the pager's own next button, "
                           "re-queried each exchange, waiting for the `from` "
                           "counter to advance"),
            "page_size": 10,
            "max_pages": a.max_pages,
            "submit": submit,
        },
        "session": {"authenticated": bool(auth.get("logout"))},
        "shelves_offered": shelves,
        "reported_total": reported_total,
        "pages_read": pages,
        "rows_read": len(pool),
        "stop_reason": stop,
        "holdings_compared_against": {
            "path": "corpus/DATASET_INDEX.json",
            "distinct_files": index["totals"]["distinct_files"],
        },
        "counts": {
            "shelf_records": len(pool),
            "with_attachment": len(with_att),
            "with_attachment_already_held": len(with_att) - len(new_with_att),
            "with_attachment_new": len(new_with_att),
            "titles_containing_giao_trinh": sum(1 for v in pool if v["is_giao_trinh_title"]),
        },
        "new_with_attachment": sorted(
            ({"title": v["title"], "record_uuid": v["record_uuid"],
              "attachment_count": v["attachment_count"],
              "attachment_urls": v["attachment_urls"]}
             for v in new_with_att), key=lambda x: x["title"]),
        "pool": pool,
    }

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = SANDBOX / (a.out or f"corpus/reports/round19_shelf_discovery_{ts}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

    c = rep["counts"]
    print()
    print(f"shelf                      {a.shelf}")
    print(f"reported total             {reported_total}")
    print(f"rows enumerated            {c['shelf_records']}  (stop: {stop})")
    print(f"with a downloadable file   {c['with_attachment']}")
    print(f"  already held             {c['with_attachment_already_held']}")
    print(f"  NEW                      {c['with_attachment_new']}")
    print(f"titles saying 'giáo trình' {c['titles_containing_giao_trinh']} "
          f"of {c['shelf_records']}")
    print()
    print(f"report: {out.relative_to(SANDBOX)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
