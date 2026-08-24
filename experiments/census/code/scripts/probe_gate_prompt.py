#!/usr/bin/env python3
"""GATE-arm prompt probe: 6 paid calls, disposable, never cited as a result.

Purpose. The first 4-arm census attempt was VOIDED because the gate_disclosed
prompt induced schema-conformant but CONTENTLESS output (empty question/answer/
description). That is the same failure class the project already sealed as
invalid in round 2d (a long instruction block interacting with the decoder), so
reporting it as "GATE admits 0/24" would publish an artefact, not a measurement.

This probe spends 6 calls to establish, BEFORE committing 288, that the revised
prompt yields substantive items. It writes to its own run directory and its
records are explicitly marked non-citable.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.credentials import runtime_key_file
from ecm_tqag.frame_plan import load_framec
from ecm_tqag.gate import classify_quote, validate_generation_round2
from ecm_tqag.routes import build_transport_configs_r2c
from ecm_tqag.prompt_amendment import PROMPT_CLARIFICATION_V3, amend_generation_payload
from ecm_tqag.run.ledger import RunLedger
from ecm_tqag.run.transport import OpenAITransport, load_response_sidecar
from ecm_tqag.runner import build_generation_request, build_packages
from ecm_tqag.validation import decode_one_json_object

RUN_DIR = ROOT / "runs" / "gate_prompt_probe_20260824T113000Z"
CAP = 6
ARM = "gate_disclosed"


def main() -> int:
    ids, assignments, manifest = load_framec(ROOT)
    packages = build_packages(manifest, ids, assignments=assignments, root=ROOT)

    # Deterministic, type-balanced probe subset: 3 MCQ + 3 short answer, taken in
    # frame order so the choice cannot be tuned to a result.
    mcq = [c for c in ids if assignments[c] == "multiple_choice"][:3]
    sa = [c for c in ids if assignments[c] == "short_answer"][:3]
    subset = mcq + sa

    state = RUN_DIR / "state"
    state.mkdir(parents=True, exist_ok=True)
    os.chmod(RUN_DIR, 0o700)

    rows = []
    with runtime_key_file("OPENROUTER_API_KEY") as op, runtime_key_file("OMNIPROXY_API_KEY") as omni:
        configs = build_transport_configs_r2c(openrouter_key_file=op, omniproxy_key_file=omni)
        ledger = RunLedger(state / "transport" / "CALL_LEDGER.jsonl",
                           freeze_sha256="gate_prompt_probe", cap=CAP, retry_reserve=0)
        transport = OpenAITransport(ledger)

        for chunk_id in subset:
            qtype = assignments[chunk_id]
            built = build_generation_request(packages[chunk_id], arm=ARM, question_type=qtype)
            amend_generation_payload(built["payload"])
            config = configs[built["model"]]
            terminal = transport.call(config, built["payload"], metadata={
                "phase": "generation", "run": "gate_prompt_probe",
                "chunk_id": chunk_id, "arm": ARM, "question_type": qtype,
            })
            row = {"chunk_id": chunk_id, "question_type": qtype,
                   "outcome": terminal.get("outcome"), "http_status": terminal.get("http_status")}
            if terminal.get("outcome") == "OK" and terminal.get("http_status") == 200:
                body = load_response_sidecar(transport.ledger.path.parent, terminal)
                content = body["choices"][0]["message"]["content"]
                row["finish_reason"] = body["choices"][0].get("finish_reason")
                row["cost"] = (body.get("usage") or {}).get("cost")
                try:
                    obj = decode_one_json_object(content)
                except Exception as exc:
                    row["decode"] = "FAIL:" + str(exc)[:80]
                    rows.append(row); continue
                row["decode"] = "OK"
                # The defect being tested for: nonempty-but-vacuous fields.
                row["len_question"] = len(str(obj.get("question") or ""))
                row["len_answer"] = len(str(obj.get("answer") or ""))
                ve = obj.get("visual_evidence") or {}
                row["len_desc"] = len(str(ve.get("description") or ""))
                row["len_rat"] = len(str(ve.get("necessity_rationale") or ""))
                row["quote_class"] = classify_quote(obj.get("text_evidence_quote"),
                                                    built["source_text"])
                try:
                    validate_generation_round2(obj, question_type=qtype,
                                               source_text=built["source_text"],
                                               image_hashes=set(built["image_hashes"]))
                    row["gate"] = "ADMIT"
                except ValueError as exc:
                    row["gate"] = str(exc)
            rows.append(row)

    empty = [r for r in rows if r.get("decode") == "OK" and min(
        r.get("len_question", 0), r.get("len_answer", 0),
        r.get("len_desc", 0), r.get("len_rat", 0)) == 0]
    report = {
        "schema": "ecm-tqag.gate-prompt-probe.v1",
        "citable_as_result": False,
        "purpose": "verify the revised gate_disclosed prompt yields substantive items",
        "arm": ARM,
        "n_calls": len(rows),
        "contentless_responses": len(empty),
        "admitted": sum(1 for r in rows if r.get("gate") == "ADMIT"),
        "known_cost_usd": sum(float(r["cost"]) for r in rows if isinstance(r.get("cost"), (int, float))),
        "rows": rows,
    }
    out = RUN_DIR / "PROBE_REPORT.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.chmod(out, 0o600)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    for r in rows:
        print("  %-28s %-16s q=%-4s a=%-4s d=%-4s r=%-4s %-22s %s" % (
            r["chunk_id"][:28], r["question_type"], r.get("len_question"), r.get("len_answer"),
            r.get("len_desc"), r.get("len_rat"), str(r.get("quote_class")), str(r.get("gate"))[:40]))
    return 0 if report["contentless_responses"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
