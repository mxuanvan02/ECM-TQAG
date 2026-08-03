#!/usr/bin/env python3
import csv,json
from pathlib import Path
from collections import Counter
root=Path(__file__).resolve().parent
def load(name):
    with (root/name).open(encoding="utf-8",newline="") as f:return {r["blind_id"]:r for r in csv.DictReader(f)}
a=load("gpt_stage_b_ratings.csv"); b=load("claude_stage_b_ratings.csv")
assert set(a)==set(b) and len(a)==8
ids=sorted(a); out={"schema":"ecm-tqag.stage-b-model-evaluation-summary.v1","evaluation_kind":"model_based_blinded_rating","item_count":8,"packet_sha256":next(iter(a.values()))["packet_sha256"],"model_families":["gpt","claude"],"status":"COMPLETE","human_or_expert_evaluation":False,"metrics":{}}
for field in ["source_fidelity","answer_support","trace_completeness"]:
    exact=sum(a[i][field]==b[i][field] for i in ids); within=sum(abs(int(a[i][field])-int(b[i][field]))<=1 for i in ids)
    out["metrics"][field]={"exact_agreement_count":exact,"item_count":8,"exact_agreement_rate":round(exact/8,4),"within_one_count":within,"within_one_rate":round(within/8,4),"gpt_distribution":dict(Counter(a[i][field] for i in ids)),"claude_distribution":dict(Counter(b[i][field] for i in ids))}
field="unscorable"; exact=sum(a[i][field]==b[i][field] for i in ids)
out["metrics"][field]={"exact_agreement_count":exact,"item_count":8,"exact_agreement_rate":round(exact/8,4),"gpt_distribution":dict(Counter(a[i][field] for i in ids)),"claude_distribution":dict(Counter(b[i][field] for i in ids))}
out["interpretation"]="Descriptive agreement between model-based evaluators; not human reliability, expert adjudication, semantic validity, or factual/legal accuracy."
print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
