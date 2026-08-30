#!/usr/bin/env python3
"""Emit the Frame-E census manifest: section unit, figure-scoped evidence span.

WHY FRAME E EXISTS
------------------
Frame D measured the protocol at section granularity and returned no separable
admission contrast (0.64 / 0.61 / 0.54, p=0.85 and p=0.25). The dataset quality
assessment located the binding defect: the evidence span the verbatim gate reads
is the WHOLE section, median 7530 and maximum 265885 characters. A verbatim
quotation over a span that long is nearly free to satisfy, so the gate stops
discriminating between prompts. Measured directly on frame D, admission runs
1.00 in the shortest length band and 0.47 in the longest.

WHAT CHANGES, AND WHAT DOES NOT
-------------------------------
CHANGED, one thing only: `evidence.text` is narrowed from the whole section to
the section's own text on the pages that carry its figure regions. Both effects
are intended and are declared before execution:

  * the span returns to a tractable size (median 1519, max 7634), so the gate can
    discriminate again;
  * an admitted quotation must now come from the SAME PAGES as the figure, which
    is the multimodal claim the paper makes. Frame D's 8.7% figure-attributable
    rate showed the unscoped gate did not enforce any relation between the quoted
    text and the image.

UNCHANGED: the unit of analysis is still one section (owner decision). The
section's identity, heading path and full page range stay in
`document_structure`, so a downstream reader still knows which section an item
belongs to and can widen the span again. Rule 4 is re-applied at the frozen
thresholds to the SCOPED span, because a gate condition must be satisfiable on
the text the gate actually reads; that drops 7 of 67 chunks and is reported.
Generator, arms, judges, schema, gates and ITT accounting are all untouched.

Output schema is `ecm-tqag.multimodal-inputs.v4-work24` because
`ecm_tqag.v310_runner.build_packages` fails closed on any other value and that
code is sealed. Frame identity is carried by `frame` and by this file's sha256.

Read-only unless --apply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[2]
CORPUS = SANDBOX / "corpus"
EXPERIMENT = SANDBOX / "experiment"

FRAME_D = EXPERIMENT / "dataset_framed" / "dataset_manifest_framed_20260829T195643Z.json"
SCOPED = CORPUS / "reports" / "SCOPED_EVIDENCE_SPANS.json"
SCOPED_TEXT = CORPUS / "reports" / ".scoped_text.json"
OUT_DIR = EXPERIMENT / "dataset_framee"

FRAME_NAME = "E_hul_law_textbook_sections_figure_scoped"

# Frozen rule 4, character-for-character as build_frameb.py applies it.
_ENUM_RE = re.compile(r"^\s*-?\s*\d+[.)]\s", re.M)
RULE4_MIN_PROSE = 120
RULE4_ENUM_ITEMS = 3
RULE4_ENUM_PROSE = 400


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def rule4(text: str) -> tuple[bool, str | None]:
    enum_items = len(_ENUM_RE.findall(text))
    prose_chars = len(text.strip())
    if enum_items >= RULE4_ENUM_ITEMS and prose_chars < RULE4_ENUM_PROSE:
        return False, "enumeration_without_prose"
    if prose_chars < RULE4_MIN_PROSE:
        return False, "insufficient_prose"
    return True, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    frame_d = json.loads(FRAME_D.read_text("utf-8"))
    scoped_rows = {r["chunk_id"]: r for r in json.loads(SCOPED.read_text("utf-8"))["rows"]}
    scoped_text = json.loads(SCOPED_TEXT.read_text("utf-8"))

    problems: list[str] = []
    packages_out: list[dict] = []
    dropped: list[dict] = []

    for pkg in frame_d["packages"]:
        cid = pkg["chunk_id"]
        row = scoped_rows.get(cid)
        text = scoped_text.get(cid)
        if row is None or text is None:
            problems.append(f"no_scoped_span:{cid}")
            continue

        # The scoped span must be a genuine subset of the section text; the
        # builder checked this and the check is re-asserted here rather than
        # trusted, because a leak would silently widen the gate.
        if not row["scoped_is_subset_of_full"]:
            problems.append(f"scope_not_subset:{cid}")
            continue

        ok, reason = rule4(text)
        if not ok:
            dropped.append({"chunk_id": cid, "reason": f"rule4_scoped:{reason}",
                            "scoped_chars": row["scoped_chars"],
                            "full_chars": row["full_chars"]})
            continue

        # images: re-verify bytes and hash, exactly as the frame-D builder did
        images_out = []
        for image in pkg["evidence"]["images"]:
            abs_path = EXPERIMENT / image["path"]
            if not abs_path.is_file():
                problems.append(f"missing_image:{image['path']}")
                continue
            raw = abs_path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if actual != image["sha256"] or len(raw) != image["bytes"]:
                problems.append(f"image_integrity:{image['path']}")
                continue
            images_out.append(dict(image))
        if not images_out:
            problems.append(f"no_resolvable_image:{cid}")
            continue

        ds = dict(pkg["evidence"]["document_structure"])
        # Declare the scope inside the bundle, so a reader of one package can see
        # that `text` is the figure-page span and not the whole section.
        ds["evidence_span"] = "figure_pages_only"
        ds["evidence_span_pages"] = row["figure_pages"]
        ds["section_pages"] = ds.get("section_pages")

        packages_out.append({
            "chunk_id": cid.replace("frameD::", "frameE::"),
            "item_id": cid.replace("frameD::", "frameE::"),
            "doc_id": pkg["doc_id"],
            "condition": "TLV",
            "split": "test",
            "question_type": pkg["question_type"],
            "evidence": {
                "text": text,
                "document_structure": ds,
                "images": images_out,
                "figure_text": pkg["evidence"].get("figure_text"),
            },
            "frame_d_chunk_id": cid,
            "scoped_chars": row["scoped_chars"],
            "full_section_chars": row["full_chars"],
        })

    n = len(packages_out)
    lens = sorted(p["scoped_chars"] for p in packages_out)
    full_lens = sorted(p["full_section_chars"] for p in packages_out)

    manifest = {
        "schema": "ecm-tqag.multimodal-inputs.v4-work24",
        "schema_note": (
            "The schema string is the sealed one because ecm_tqag.v310_runner."
            "build_packages fails closed on any other value and that code is "
            "sealed. Frame identity is carried by `frame` and this file's sha256."
        ),
        "frame": FRAME_NAME,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chunk_count": n,
        "granularity": "section",
        "unit_of_analysis_note": (
            "The unit is still one section. Only the evidence span the verbatim "
            "gate reads is narrowed; section identity, heading path and full page "
            "range remain in document_structure."
        ),
        "what_changed_from_frame_d": {
            "evidence_text": (
                "narrowed from the whole section to the section's own text on the "
                "pages carrying its figure regions"
            ),
            "span_lengths_before": {"median": full_lens[len(full_lens) // 2],
                                    "max": full_lens[-1]},
            "span_lengths_after": {"median": lens[len(lens) // 2], "max": lens[-1]},
            "everything_else": (
                "unchanged: unit of analysis, generator, three arm prompts, judges, "
                "judgement schema, gates, ITT accounting, zero retry/fallback"
            ),
        },
        "why": (
            "Frame D returned no separable admission contrast. The measured cause "
            "is span length: a verbatim gate over a median 7530-character span is "
            "nearly free to satisfy, and frame-D admission by length band runs 1.00 "
            "(shortest) to 0.47 (longest). Narrowing the span also forces an "
            "admitted quotation to come from the same pages as the figure, which is "
            "the multimodal relation frame D's 8.7% figure-attributable rate showed "
            "the unscoped gate did not enforce."
        ),
        "rule_4_reapplied_to_scoped_span": {
            "why": (
                "A gate condition must be satisfiable on the text the gate actually "
                "reads. Applying rule 4 to the full section while the gate reads the "
                "scoped span would admit chunks whose scoped span holds no quotable "
                "prose."
            ),
            "thresholds": (
                f"EXCLUDE if prose < {RULE4_MIN_PROSE} chars, or >= "
                f"{RULE4_ENUM_ITEMS} enumerated items with prose < {RULE4_ENUM_PROSE}"
            ),
            "dropped": dropped,
            "dropped_count": len(dropped),
        },
        "figure_text_contract": {
            "channel": "evidence.figure_text",
            "quotable_as_prose": False,
            "why": (
                "OCR of figure regions at confidence >= 90 still carries roughly one "
                "slip in ten on graphical strokes. The verbatim gate reads "
                "evidence.text only, as the sealed frame does."
            ),
        },
        "inputs": {
            "frame_d_manifest": str(FRAME_D.relative_to(SANDBOX)),
            "frame_d_manifest_sha256": sha256_file(FRAME_D),
            "scoped_spans_report": str(SCOPED.relative_to(SANDBOX)),
            "scoped_spans_report_sha256": sha256_file(SCOPED),
        },
        "question_type_counts": {
            q: sum(1 for p in packages_out if p["question_type"] == q)
            for q in sorted({p["question_type"] for p in packages_out})
        },
        "documents": len({p["doc_id"] for p in packages_out}),
        "redistribution": (
            "Source text and figure crops are copyright of the University of Law, "
            "Hue University and are held for internal research only. This manifest "
            "and the images it references must NOT be published."
        ),
        "problems": problems,
        "packages": packages_out,
    }

    print(f"frame E chunks     {n}")
    print(f"dropped by rule 4  {len(dropped)}")
    print(f"documents          {manifest['documents']}")
    print(f"question types     {manifest['question_type_counts']}")
    print(f"span median        {lens[len(lens)//2]} (was {full_lens[len(full_lens)//2]})")
    print(f"span max           {lens[-1]} (was {full_lens[-1]})")
    print(f"problems           {len(problems)}")
    for p in problems[:10]:
        print("   ", p)

    if not args.apply:
        print("\ndry run; pass --apply to write")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = OUT_DIR / f"dataset_manifest_framee_{stamp}.json"
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"\nwrote {dest.relative_to(SANDBOX)}")
    print("sha256", sha256_file(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
