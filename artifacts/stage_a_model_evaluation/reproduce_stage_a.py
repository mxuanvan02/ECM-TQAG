#!/usr/bin/env python3
"""Regenerate Stage A descriptive agreement from de-identified rating CSVs."""
import csv, json, pathlib, collections
HERE=pathlib.Path(__file__).resolve().parent
FAMILIES=("gpt","claude")
FIELDS=("correctness","evidence_sufficiency","question_clarity","choice_quality","required_modality","unscorable")
rows={}
for family in FAMILIES:
    with (HERE/f"{family}_stage_a_ratings.csv").open(encoding="utf-8-sig",newline="") as f:
        data=list(csv.DictReader(f))
    assert len(data)==24 and len({r["blind_id"] for r in data})==24
    rows[family]={r["blind_id"]:r for r in data}
assert set(rows["gpt"])==set(rows["claude"])
packet={r["packet_sha256"] for family in FAMILIES for r in rows[family].values()}
assert len(packet)==1
out={"schema":"ecm-tqag.stage-a-model-evaluation-summary.v1","evaluation_kind":"model_based_blinded_rating","item_count":24,"packet_sha256":packet.pop(),"model_families":["gpt","claude"],"status":"COMPLETE","human_or_expert_evaluation":False,"metrics":{}}
for field in FIELDS:
    pairs=[(rows["gpt"][i][field],rows["claude"][i][field]) for i in sorted(rows["gpt"])]
    agree=sum(a==b for a,b in pairs)
    d={"exact_agreement_count":agree,"item_count":24,"exact_agreement_rate":round(agree/24,4),"gpt_distribution":dict(collections.Counter(a for a,b in pairs)),"claude_distribution":dict(collections.Counter(b for a,b in pairs))}
    if field in ("evidence_sufficiency","question_clarity","choice_quality"):
        d["within_one_count"]=sum(abs(int(a)-int(b))<=1 for a,b in pairs)
        d["within_one_rate"]=round(d["within_one_count"]/24,4)
    out["metrics"][field]=d
out["interpretation"]="Exact agreement is descriptive model-family agreement, not human reliability, semantic validity, factual/legal accuracy, or expert adjudication."
text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
assert json.loads((HERE/"summary.json").read_text(encoding="utf-8"))==out
print(text,end="")
