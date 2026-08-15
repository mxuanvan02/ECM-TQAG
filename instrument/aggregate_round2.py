#!/usr/bin/env python3
"""Offline aggregation for the round-2 exploratory census.

Reads only sealed task records and the transport ledger. Performs no provider
call, reads no credential, and never modifies a task record.
"""
from __future__ import annotations

import hashlib
import json
import sys
from math import comb
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.official_outcomes import authoritative_frame
from ecm_tqag.stats.intervals import clopper_pearson
from ecm_tqag.v310_contracts import canonical_bytes
from ecm_tqag.v310_execution import JUDGE_MODELS, build_call_plan
from ecm_tqag.v310_runner import extract_reported_cost_usd

# Run directory is an explicit argument: the first round-2 attempt was
# quarantined for duplicate paid calls, so aggregation must never default to
# a run the caller did not name.
if len(sys.argv) < 2:
    raise SystemExit("usage: aggregate_round2.py <run_dir_name>")
RUN_DIR = ROOT / "runs" / sys.argv[1]
if (RUN_DIR / "QUARANTINE_SEAL.json").exists():
    raise SystemExit(f"refusing to aggregate quarantined run: {RUN_DIR.name}")
STATE = RUN_DIR / "state"
ARMS = ("ecm_full", "direct", "structured_no_contract")

# Rounds 2c and 2d substituted both judge families (protocol change, frozen
# before execution) and each uses its own task-id infix so records can never
# collide across runs. Derive both from the run directory name rather than
# assuming the round-1 constants.
if RUN_DIR.name.startswith("round2c"):
    from round2.round2c_routes import JUDGE_MODELS_R2C as JUDGE_MODELS  # noqa: F811

    USES_SUBSTITUTED_JUDGES = True
    TASK_INFIX = "::r2c::"
    REPORT_SCHEMA = "ecm-tqag.round2c.census-report.v1"
    REPORT_MODE = "exploratory_round2c_repaired_contract_substituted_judges"
elif RUN_DIR.name.startswith("round2d"):
    from round2.round2c_routes import JUDGE_MODELS_R2C as JUDGE_MODELS  # noqa: F811

    USES_SUBSTITUTED_JUDGES = True
    TASK_INFIX = "::r2d::"
    REPORT_SCHEMA = "ecm-tqag.round2d.census-report.v1"
    REPORT_MODE = "exploratory_round2d_prompt_convention_repair"
elif RUN_DIR.name.startswith("round2e"):
    from round2.round2c_routes import JUDGE_MODELS_R2C as JUDGE_MODELS  # noqa: F811

    USES_SUBSTITUTED_JUDGES = True
    TASK_INFIX = "::r2e::"
    REPORT_SCHEMA = "ecm-tqag.round2e.census-report.v1"
    REPORT_MODE = "exploratory_round2e_prompt_convention_repair_minimal"
else:
    USES_SUBSTITUTED_JUDGES = False
    TASK_INFIX = "::r2::"
    REPORT_SCHEMA = "ecm-tqag.round2.census-report.v1"
    REPORT_MODE = "exploratory_round2_repaired_contract"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def task_path(task_id: str) -> Path:
    return STATE / "tasks" / (sha256_bytes(task_id.encode()) + ".json")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def r2_id(task_id: str) -> str:
    return task_id.replace("::full::", TASK_INFIX, 1)


def known_cost() -> tuple[float, int]:
    ledger = STATE / "transport" / "CALL_LEDGER.jsonl"
    known, unknown = 0.0, 0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("record_type") != "CALL_TERMINAL":
            continue
        usage = row.get("usage")
        cost = extract_reported_cost_usd(usage) if isinstance(usage, Mapping) else None
        if cost is None:
            unknown += 1
        else:
            known += float(cost)
    return known, unknown


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact binomial (sign) test on discordant pairs."""
    if b + c == 0:
        return 1.0
    n, k = b + c, min(b, c)
    return min(1.0, sum(comb(n, i) for i in range(0, k + 1)) * (0.5 ** (n - 1)))


def main() -> int:
    frame = authoritative_frame()
    ids = frame["full_chunk_ids"]
    plan = build_call_plan(mode="full", chunk_ids=ids)
    gen_tasks = [{**t, "task_id": r2_id(t["task_id"])} for t in plan["generation_tasks"]]
    # The frozen plan bakes the ROUND-1 judge names into every judge task_id and
    # model. Round 2c substituted both families, so the suffix must be remapped
    # positionally exactly as the round-2c harness did; otherwise judge_records
    # would be keyed with dead names and every hard-valid lookup would miss.
    def remap_judge(t: Mapping[str, Any]) -> dict[str, Any]:
        task_id = r2_id(t["task_id"])
        model = t["model"]
        if USES_SUBSTITUTED_JUDGES:
            from round2.round2c_routes import SUPERSEDED_JUDGE_MODELS

            index = SUPERSEDED_JUDGE_MODELS.index(model)
            model = JUDGE_MODELS[index]
            suffix = "::" + SUPERSEDED_JUDGE_MODELS[index]
            if not task_id.endswith(suffix):
                raise SystemExit("BLOCKED_AGG:JUDGE_SUFFIX:" + task_id)
            task_id = task_id[: -len(suffix)] + "::" + model
        return {
            **t,
            "task_id": task_id,
            "model": model,
            "source_task_id": r2_id(t["source_task_id"]),
        }

    judge_tasks = [remap_judge(t) for t in plan["judge_tasks"]]
    if len({t["task_id"] for t in judge_tasks}) != len(judge_tasks):
        raise SystemExit("BLOCKED_AGG:JUDGE_TASK_COLLISION")

    gen_records, judge_records = {}, {}
    for t in gen_tasks:
        p = task_path(t["task_id"])
        gen_records[t["task_id"]] = read_json(p) if p.exists() else None
    for t in judge_tasks:
        p = task_path(t["task_id"])
        judge_records[t["task_id"]] = read_json(p) if p.exists() else None

    gen_pass = {a: {c: False for c in ids} for a in ARMS}
    for t in gen_tasks:
        rec = gen_records[t["task_id"]]
        if rec and rec.get("status") == "COMPLETE":
            gen_pass[t["arm"]][t["chunk_id"]] = True

    hard_valid = {a: {c: False for c in ids} for a in ARMS}
    blockers: dict[str, int] = {}
    for t in gen_tasks:
        arm, cid = t["arm"], t["chunk_id"]
        if not gen_pass[arm][cid]:
            continue
        ok = True
        for judge in JUDGE_MODELS:
            jrec = judge_records.get(f"judge{TASK_INFIX}{cid}::{arm}::{judge}")
            if not (jrec and jrec.get("status") == "COMPLETE"):
                blockers["judge_record_missing_or_failed"] = blockers.get("judge_record_missing_or_failed", 0) + 1
                ok = False
                break
            o = jrec["object"]
            if o.get("critical_provenance_violation") is True:
                blockers["critical_provenance_violation"] = blockers.get("critical_provenance_violation", 0) + 1
                ok = False
                break
            for dim in ("evidence_correctness", "visual_necessity", "answerability"):
                if o.get(dim, 0) < 3:
                    blockers[f"{dim}_below_3"] = blockers.get(f"{dim}_below_3", 0) + 1
                    ok = False
            if not ok:
                break
        hard_valid[arm][cid] = ok

    contrasts = {}
    for left, right in (("ecm_full", "direct"), ("ecm_full", "structured_no_contract")):
        l_only = sum(1 for c in ids if hard_valid[left][c] and not hard_valid[right][c])
        r_only = sum(1 for c in ids if hard_valid[right][c] and not hard_valid[left][c])
        contrasts[f"{left}_vs_{right}"] = {
            "test": "mcnemar_exact_two_sided",
            "discordant_left_only": l_only,
            "discordant_right_only": r_only,
            "discordant": l_only + r_only,
            "p_two_sided_exact": exact_mcnemar(l_only, r_only),
            "min_unidirectional_discordance_required": 6,
        }
    ranked = sorted(contrasts.items(), key=lambda kv: kv[1]["p_two_sided_exact"])
    for rank, (name, row) in enumerate(ranked, start=1):
        row["holm"] = {"rank": rank, "holm_threshold": 0.05 / (len(ranked) - rank + 1)}
        row["holm"]["reject"] = row["p_two_sided_exact"] <= row["holm"]["holm_threshold"]

    status_counts: dict[str, dict[str, int]] = {"generation": {}, "judge": {}}
    for name, recs in (("generation", gen_records), ("judge", judge_records)):
        for rec in recs.values():
            key = rec.get("status") if rec else "MISSING"
            status_counts[name][key] = status_counts[name].get(key, 0) + 1

    quote_classes: dict[str, int] = {}
    fail_reasons: dict[str, int] = {}
    for rec in gen_records.values():
        if not rec:
            continue
        if rec.get("status") == "COMPLETE":
            k = str(rec.get("round2_quote_class"))
            quote_classes[k] = quote_classes.get(k, 0) + 1
        else:
            k = str(rec.get("reason", ""))[:70]
            fail_reasons[k] = fail_reasons.get(k, 0) + 1

    judge_means: dict[str, dict[str, float]] = {}
    cpv = 0
    n_judge = 0
    for tid, rec in judge_records.items():
        if not (rec and rec.get("status") == "COMPLETE"):
            continue
        n_judge += 1
        arm = tid.split("::")[3]
        o = rec["object"]
        if o.get("critical_provenance_violation") is True:
            cpv += 1
        for dim in ("evidence_correctness", "visual_necessity", "answerability",
                    "pedagogical_value", "vietnamese_language"):
            judge_means.setdefault(arm, {}).setdefault(dim, 0.0)
            judge_means[arm][dim] += o.get(dim, 0)
    counts_per_arm: dict[str, int] = {}
    for tid, rec in judge_records.items():
        if rec and rec.get("status") == "COMPLETE":
            arm = tid.split("::")[3]
            counts_per_arm[arm] = counts_per_arm.get(arm, 0) + 1
    for arm, dims in judge_means.items():
        for dim in dims:
            dims[dim] = round(dims[dim] / counts_per_arm[arm], 3)

    known_total, unknown_count = known_cost()
    report = {
        "schema": REPORT_SCHEMA,
        "run": RUN_DIR.name,
        "mode": REPORT_MODE,
        "judge_models": list(JUDGE_MODELS),
        "frame": "A_same_16_chunks",
        "denominator_per_arm": 16,
        "known_reported_cost_usd": round(known_total, 9),
        "unknown_cost_call_count": unknown_count,
        "status_counts": status_counts,
        "generation_pass_per_arm": {a: sum(gen_pass[a].values()) for a in ARMS},
        "hard_valid_per_arm": {a: sum(hard_valid[a].values()) for a in ARMS},
        "hard_valid_ci_per_arm": {
            a: clopper_pearson(sum(hard_valid[a].values()), 16, 0.05) for a in ARMS
        },
        "contrasts": contrasts,
        "hard_valid_blockers": blockers,
        "quote_classes_on_pass": quote_classes,
        "generation_failure_reasons": fail_reasons,
        "judge_records_complete": n_judge,
        "critical_provenance_violations": cpv,
        "judge_means_by_arm": judge_means,
        "judge_records_per_arm": counts_per_arm,
    }
    out = RUN_DIR / "ROUND2_REPORT.json"
    out.write_bytes(canonical_bytes(report))
    print(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
