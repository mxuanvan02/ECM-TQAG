#!/usr/bin/env python3
"""Audit duplicate provider calls in the round-2 census (read-only).

Question: the transport ledger holds 152 CALL_TERMINAL rows for 84 distinct
task_ids. For every duplicated task, load BOTH retained responses, re-apply the
round-2 gate to each, and report whether the two independent calls agree.

If they disagree, the recorded task outcome depends on which concurrent process
wrote last, i.e. the task was sampled twice and the surviving outcome may be the
luckier of two draws. That would contaminate the round-2 pass rates.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.official_outcomes import authoritative_frame
from ecm_tqag.v310_runner import build_packages
from ecm_tqag.v310_validation import decode_one_json_object, validate_judgement

from round2.round2_validation import validate_generation_round2

RUN = ROOT / "runs" / "round2_exploratory_census_20260815T020000Z"
STATE = RUN / "state"
LEDGER = STATE / "transport" / "CALL_LEDGER.jsonl"


def sha_of_task(task_id: str) -> str:
    import hashlib
    return hashlib.sha256(task_id.encode()).hexdigest()


def main() -> int:
    frame = authoritative_frame()
    ids = frame["full_chunk_ids"]
    assignments = frame["assignments"]
    manifest = json.loads((ROOT / "dataset" / "dataset_manifest.json").read_text(encoding="utf-8"))
    packages = build_packages(manifest, ids, assignments=assignments, root=ROOT)

    terminals: dict[str, list[dict]] = defaultdict(list)
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("record_type") != "CALL_TERMINAL":
            continue
        tid = row.get("task_id")
        if isinstance(tid, str):
            terminals[tid].append(row)

    dup = {t: rows for t, rows in terminals.items() if len(rows) > 1}
    print(f"distinct tasks with terminals : {len(terminals)}")
    print(f"tasks with >1 paid call       : {len(dup)}")
    print(f"total paid calls in ledger    : {sum(len(r) for r in terminals.values())}")

    gen_agree = Counter()
    disagree_detail = []
    judge_agree = Counter()
    recorded_vs_calls = Counter()

    for tid, rows in sorted(dup.items()):
        phase = rows[0].get("phase")
        chunk_id = rows[0].get("chunk_id")
        outcomes = []
        for row in rows:
            rpath = row.get("response_path")
            if not rpath:
                outcomes.append(("no_response", None))
                continue
            body_path = STATE / "transport" / rpath
            if not body_path.exists():
                outcomes.append(("missing_sidecar", None))
                continue
            body = json.loads(body_path.read_text(encoding="utf-8"))
            try:
                obj = decode_one_json_object(body["choices"][0]["message"]["content"])
            except Exception:
                outcomes.append(("undecodable", None))
                continue
            qtype = assignments[chunk_id]
            if phase == "generation":
                pkg = packages[chunk_id]
                src = pkg["evidence"]["text"]
                hashes = {i["sha256"] for i in pkg["evidence"]["images"]}
                try:
                    out = validate_generation_round2(
                        obj, question_type=qtype, source_text=src, image_hashes=hashes
                    )
                    outcomes.append(("PASS", out["round2_quote_class"]))
                except ValueError as exc:
                    outcomes.append(("FAIL", str(exc).split(":")[-1]))
            else:
                try:
                    validate_judgement(obj, question_type=qtype)
                    outcomes.append(("PASS", None))
                except ValueError:
                    outcomes.append(("FAIL", None))

        verdicts = [o[0] for o in outcomes]
        key = "agree:" + verdicts[0] if len(set(verdicts)) == 1 else "DISAGREE:" + "/".join(verdicts)
        if phase == "generation":
            gen_agree[key] += 1
            if len(set(verdicts)) > 1:
                disagree_detail.append((tid, outcomes))
        else:
            judge_agree[key] += 1

        # what did the task record actually keep?
        tpath = STATE / "tasks" / (sha_of_task(tid) + ".json")
        if tpath.exists():
            rec = json.loads(tpath.read_text(encoding="utf-8"))
            recorded = rec.get("status")
            if len(set(verdicts)) > 1:
                recorded_vs_calls[f"{phase}:discordant_calls_recorded_{recorded}"] += 1
            else:
                recorded_vs_calls[f"{phase}:concordant_recorded_{recorded}"] += 1

    print("\n=== duplicated GENERATION tasks: do the two paid calls agree? ===")
    for k, v in gen_agree.most_common():
        print(f"  {v:3d}  {k}")
    print("\n=== duplicated JUDGE tasks ===")
    for k, v in judge_agree.most_common():
        print(f"  {v:3d}  {k}")
    print("\n=== recorded task status vs call concordance ===")
    for k, v in recorded_vs_calls.most_common():
        print(f"  {v:3d}  {k}")

    if disagree_detail:
        print("\n=== generation tasks where the two calls DISAGREED ===")
        for tid, outcomes in disagree_detail:
            print(f"  {tid}")
            for verdict, extra in outcomes:
                print(f"      {verdict}  {extra}")

    out = {
        "distinct_tasks": len(terminals),
        "tasks_with_duplicate_paid_calls": len(dup),
        "total_paid_calls": sum(len(r) for r in terminals.values()),
        "generation_duplicate_concordance": dict(gen_agree),
        "judge_duplicate_concordance": dict(judge_agree),
        "recorded_vs_calls": dict(recorded_vs_calls),
        "discordant_generation_tasks": [
            {"task_id": t, "call_outcomes": [list(o) for o in outs]} for t, outs in disagree_detail
        ],
    }
    (ROOT / "runs" / RUN.name / "DUPLICATE_CALL_AUDIT.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nwrote DUPLICATE_CALL_AUDIT.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
