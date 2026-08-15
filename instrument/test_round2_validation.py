"""Phase 0 offline unit tests for the round-2 repaired contract.

No provider calls. Uses retained round-1 raw responses plus synthetic cases.
Run: uv run python round2/test_round2_validation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.v310_runner import build_packages
from ecm_tqag.v310_validation import decode_one_json_object, validate_generation
from ecm_tqag.official_outcomes import authoritative_frame
from round2.round2_validation import classify_quote, validate_generation_round2

RUN = ROOT / "runs" / "successor_full_census_20260814T213500Z"
MANIFEST = ROOT / "dataset" / "dataset_manifest.json"


def load_ledger_generation():
    recs = {}
    ledger = RUN / "state" / "transport" / "CALL_LEDGER.jsonl"
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if o.get("phase") != "generation":
            continue
        recs.setdefault(o["task_id"], {}).update(o)
    return recs


def main() -> int:
    frame = authoritative_frame()
    ids = frame["full_chunk_ids"]
    assignments = frame["assignments"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    packages = build_packages(manifest, ids, assignments=assignments, root=ROOT)

    ledger = load_ledger_generation()
    tasks = {}
    for f in (RUN / "state" / "tasks").glob("*.json"):
        t = json.loads(f.read_text(encoding="utf-8"))
        if t["task_id"].startswith("generation::"):
            tasks[t["task_id"]] = t

    regress_pass = regress_fail = 0
    class_counts = {}
    for tid, task in sorted(tasks.items()):
        rec = ledger[tid]
        chunk_id = rec["chunk_id"]
        arm = rec["arm"]
        pkg = packages[chunk_id]
        src = pkg["evidence"]["text"]
        hashes = {i["sha256"] for i in pkg["evidence"]["images"]}
        qtype = assignments[chunk_id]
        rpath = rec.get("response_path")
        if not rpath:
            continue
        body = json.loads((RUN / "state" / "transport" / rpath).read_text(encoding="utf-8"))
        try:
            obj = decode_one_json_object(body["choices"][0]["message"]["content"])
        except ValueError:
            continue
        r1_ok = task["status"] == "COMPLETE"
        # round-1 oracle
        try:
            validate_generation(obj, question_type=qtype, source_text=src, image_hashes=hashes)
            oracle_ok = True
        except ValueError:
            oracle_ok = False
        assert oracle_ok == r1_ok, (tid, oracle_ok, r1_ok)
        # round-2 gate
        try:
            out2 = validate_generation_round2(obj, question_type=qtype, source_text=src, image_hashes=hashes)
            r2_ok = True
            cls = out2["round2_quote_class"]
        except ValueError:
            r2_ok = False
            cls = classify_quote(obj.get("text_evidence_quote"), src)
        if r1_ok:
            regress_pass += int(r2_ok)
        else:
            regress_fail += int(r2_ok)
            class_counts[cls] = class_counts.get(cls, 0) + 1

    print(f"regression: round-1 passing still pass under round-2: {regress_pass}/14")
    print(f"round-1 failures that now pass: {regress_fail} (expected 3: two normalized, one elided; the fourth quote-recoverable attempt is MCQ-inconsistent and must stay failing)")
    print(f"quote classes among still-failing: {class_counts}")

    # synthetic edge cases
    src = "Bộ máy nhà nước gồm các cơ quan: Quốc hội, Chính phủ, Tòa án."
    hashes = {"h1"}
    base = {
        "question": "Q?", "answer": "A.", "question_type": "short_answer",
        "visual_evidence": {"image_sha256": "h1", "description": "d", "necessity_rationale": "r"},
    }
    ok = lambda o, **kw: validate_generation_round2({**base, **o}, question_type="short_answer", source_text=src, image_hashes=hashes)
    # exact
    ok({"text_evidence_quote": "Quốc hội, Chính phủ"})
    # whitespace/unicode variant
    ok({"text_evidence_quote": "Quốc  hội,\nChính phủ"})
    # elision in order (fragments >= 8 chars, present in source order)
    ok({"text_evidence_quote": "Bộ máy nhà nước gồm các cơ quan: Quốc hội... Chính phủ, Tòa án."})
    # absent quote must fail
    try:
        ok({"text_evidence_quote": "không có trong nguồn"}); raise SystemExit("FAIL: absent quote passed")
    except ValueError:
        pass
    # MCQ letter label must still fail
    mcq = {**base, "text_evidence_quote": "Quốc hội, Chính phủ", "question_type": "multiple_choice", "options": ["A.", "B.", "C.", "D."], "correct_option": 1, "answer": "B"}
    try:
        validate_generation_round2(mcq, question_type="multiple_choice", source_text=src, image_hashes=hashes)
        raise SystemExit("FAIL: letter-label MCQ passed")
    except ValueError:
        pass
    # MCQ full option text passes
    mcq2 = {**mcq, "answer": "B."}
    validate_generation_round2(mcq2, question_type="multiple_choice", source_text=src, image_hashes=hashes)
    print("synthetic edge cases: all behave as specified")

    assert regress_pass == 14, "regression broken"
    assert regress_fail == 3, "expected exactly 3 recovered failures"
    print("PHASE 0 UNIT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
