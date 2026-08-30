#!/usr/bin/env python3
"""Frame F: Frame E's chunks and spans, plus the FIGURE ROLE the prompt needs.

WHAT CHANGES FROM FRAME E
-------------------------
Nothing about the sample, the unit, the evidence span, the images or rule 4.
Frame F is Frame E with one field added to `evidence.document_structure`:

    figure_role in {"table", "diagram", "pictorial"}

and one counts block recording the distribution. The chunk ids, the spans, the
image records and the figure_text channel are copied byte-for-byte from the
Frame-E manifest, so any difference measured between the two censuses cannot come
from the data.

WHY THE ROLE IS NEEDED
----------------------
The ECM-v2 arm asks for a question whose answer comes from the figure. What
question shape can do that depends on what the figure IS: a table answers a
row x column lookup, a diagram answers a relation, a picture answers a label or a
spatial fact. Without the role the generator has to guess, and the frame-D/E
evidence shows what it guesses: a prose-anchored question with a figure hash
attached.

WHERE THE ROLE COMES FROM
-------------------------
`regions[].kind` as recorded by the section builder, on the unit's own
figure-bearing pages. Nothing is re-detected here. The section builder's three
kinds map onto the three question shapes:

    table   -> table       (ruled, row x column)
    drawing -> diagram     (vector strokes: arrows, boxes, hierarchies)
    raster  -> pictorial   (embedded image: map, photograph, scanned figure)

A chunk whose figure pages carry more than one kind is assigned the kind of the
LARGEST region by area, and `figure_role_mixed` records that the choice was made.
Five of sixty chunks are mixed.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
EXPERIMENT = SANDBOX / "experiment"
SECTIONS = SANDBOX / "datasets_sections"
FRAME_E = (EXPERIMENT / "dataset_framee"
           / "dataset_manifest_framee_20260830T093119Z.json")
FRAME_E_SHA256 = "051db6ac66e09ece70d71391068f32893a76a1fd1186c563b3d24146e78dec52"
OUT_DIR = EXPERIMENT / "dataset_framef"

# section-builder region kind -> ECM-v2 figure role
KIND_TO_ROLE = {"table": "table", "drawing": "diagram", "raster": "pictorial"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def unit_record(doc_id: str, unit_id: str) -> dict:
    """The section builder's own record for this unit."""
    for candidate in SECTIONS.glob(f"{doc_id}/*/unit.json"):
        record = json.loads(candidate.read_text("utf-8"))
        if record["unit_id"] == unit_id:
            return record
    raise SystemExit(f"no unit record for {doc_id}::{unit_id}")


def role_of(unit: dict) -> tuple[str, dict]:
    """Figure role for a unit, from its recorded regions on figure pages.

    Largest region by area decides when a unit carries more than one kind, which
    is a choice and is recorded as one.
    """
    pages = set(unit.get("region_pages") or [])
    areas: dict[str, float] = {}
    counts: Counter = Counter()
    for region in unit.get("regions") or []:
        if region.get("page") not in pages:
            continue
        kind = region.get("kind")
        role = KIND_TO_ROLE.get(str(kind))
        if role is None:
            continue
        x0, y0, x1, y1 = region["rect_pt"]
        areas[role] = areas.get(role, 0.0) + abs((x1 - x0) * (y1 - y0))
        counts[role] += 1
    if not areas:
        raise SystemExit(f"no usable region kind for {unit['unit_id']}")
    role = max(areas.items(), key=lambda kv: kv[1])[0]
    return role, {
        "figure_role_counts": dict(counts),
        "figure_role_mixed": len(counts) > 1,
        "figure_role_rule": ("kind of the largest region by area on the unit's "
                             "figure-bearing pages"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    raw = FRAME_E.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != FRAME_E_SHA256:
        raise SystemExit(f"frame E manifest changed: {digest}")
    source = json.loads(raw.decode("utf-8"))

    packages_out: list[dict] = []
    roles: Counter = Counter()
    mixed = 0
    problems: list[str] = []

    for pkg in source["packages"]:
        chunk_id = pkg["chunk_id"]
        doc_id = pkg["doc_id"]
        unit_id = chunk_id.split("::", 1)[1]
        unit = unit_record(doc_id, unit_id)
        role, meta = role_of(unit)
        roles[role] += 1
        mixed += 1 if meta["figure_role_mixed"] else 0

        row = deepcopy(pkg)
        row["chunk_id"] = chunk_id.replace("frameE::", "frameF::", 1)
        row["item_id"] = row["chunk_id"]
        structure = row["evidence"]["document_structure"]
        structure["figure_role"] = role
        structure["figure_role_provenance"] = meta
        packages_out.append(row)

        # the evidence the gate reads must be untouched
        if row["evidence"]["text"] != pkg["evidence"]["text"]:
            problems.append("text_changed:" + chunk_id)
        if row["evidence"]["images"] != pkg["evidence"]["images"]:
            problems.append("images_changed:" + chunk_id)

    n = len(packages_out)
    manifest = {
        "schema": "ecm-tqag.multimodal-inputs.v4-work24",
        "schema_note": source["schema_note"],
        "frame": "F_hul_law_textbook_sections_role_conditioned",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunk_count": n,
        "granularity": "section",
        "unit_of_analysis_note": source["unit_of_analysis_note"],
        "what_changed_from_frame_e": {
            "added_field": "evidence.document_structure.figure_role",
            "values": sorted(KIND_TO_ROLE.values()),
            "derived_from": ("regions[].kind recorded by the section builder on "
                             "the unit's figure-bearing pages; nothing re-detected"),
            "mapping": dict(KIND_TO_ROLE),
            "tie_rule": "kind of the largest region by area",
            "unchanged": ("chunk membership, evidence.text, images, figure_text, "
                          "question_type, rule 4, the unit of analysis"),
            "why": ("The ECM-v2 arm must ask for an answer the figure supplies, and "
                    "which question shape can do that depends on what the figure is. "
                    "Frame E gave the generator no way to know."),
        },
        "figure_role_counts": dict(roles),
        "figure_role_mixed_chunks": mixed,
        "figure_text_contract": source["figure_text_contract"],
        "inputs": {
            "frame_e_manifest": str(FRAME_E.relative_to(SANDBOX)),
            "frame_e_manifest_sha256": digest,
            "section_dataset_root": str(SECTIONS.relative_to(SANDBOX)),
        },
        "question_type_counts": {
            q: sum(1 for p in packages_out if p["question_type"] == q)
            for q in sorted({p["question_type"] for p in packages_out})
        },
        "documents": len({p["doc_id"] for p in packages_out}),
        "redistribution": source["redistribution"],
        "problems": problems,
        "packages": packages_out,
    }

    print(f"frame F chunks     {n}")
    print(f"figure roles       {dict(roles)}")
    print(f"mixed-role chunks  {mixed}")
    print(f"question types     {manifest['question_type_counts']}")
    print(f"documents          {manifest['documents']}")
    print(f"problems           {len(problems)}")
    for p in problems[:10]:
        print("   ", p)

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = OUT_DIR / f"dataset_manifest_framef_{stamp}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"\nwrote {out.relative_to(SANDBOX)}")
    print("sha256", sha256_file(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
