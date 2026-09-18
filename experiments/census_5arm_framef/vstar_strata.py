"""Decompose the V* contrast by G6 stratum + account for the 2-item exclusion.
Key question: is 0.58-vs-0.38 partly tautological? G6-fail means the answer IS
a substring of the quotation, and the quotation is required to be a substring of
T_c -- which is exactly what the text-only answerer receives.
"""
import json
from math import comb

ad = json.load(open("records/admission_decisions.json"))["rows"]
ab = json.load(open("records/ablation_generator_answerer.json"))
ab2 = json.load(open("records/ablation_independent_answerer.json"))

adm = {}
for r in (ad.values() if isinstance(ad, dict) else ad):
    adm[f"{r['chunk_id']}::{r['arm']}"] = r

def fisher(a, b, c, d):
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c
    def p(x):
        return comb(r1, x) * comb(r2, c1 - x) / comb(n, c1)
    po = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1)
                        if p(x) <= po * (1 + 1e-9)))

def vstar(row):
    to = row["text_only"]
    return None if to.get("status") != "COMPLETE" else (0 if to["correct_at_primary_threshold"] else 1)

# ---- exclusion accounting ----
excl = [iid for iid in list(ab["rows"]) + list(ab2["rows"])
        if False]  # placeholder
print("declared exclusion: 227 -> 225 (gold answer folds to <=2 chars)")
print("ablation n_items field:", ab.get("n_items"), "| rows:", len(ab["rows"]))
print("task_status_counts:", ab.get("task_status_counts"))
print()

# ---- failed-condition composition of the rejected pool ----
from collections import Counter
cnt = Counter()
for iid, row in ab["rows"].items():
    a = adm.get(iid)
    if a is None or a["admitted"]:
        continue
    for f in a["failed_conditions"]:
        cnt[f] += 1
print("rejected pool (generator run), failed_conditions frequency:")
for k, v in cnt.most_common():
    print(f"  {k:34s} {v}")
tot_rej = sum(1 for iid in ab["rows"] if adm.get(iid) and not adm[iid]["admitted"])
print(f"total rejected rows joined: {tot_rej}")
print()

# ---- stratified contrast ----
def strat(rows, name):
    g = {"all8": [], "g6pass_g78fail": [], "g6fail": []}
    for iid, row in rows.items():
        a = adm.get(iid)
        v = vstar(row)
        if a is None or v is None:
            continue
        fc = set(a["failed_conditions"])
        if not fc:
            g["all8"].append(v)
        elif "g6_answer_not_in_quote" in fc:
            g["g6fail"].append(v)
        else:
            g["g6pass_g78fail"].append(v)
    print(f"--- {name} ---")
    for k, vs in g.items():
        if vs:
            print(f"  {k:18s} V*={sum(vs)/len(vs):.3f}  ({sum(vs)}/{len(vs)})")
    a1, b1 = g["all8"], g["g6pass_g78fail"]
    tab = (sum(a1), len(a1) - sum(a1), sum(b1), len(b1) - sum(b1))
    p1 = fisher(*tab)
    print(f"  contrast all8 vs g6pass_g78fail: {tab} Fisher p={p1:.3f}")
    a2, b2 = g["all8"], g["g6fail"]
    tab2 = (sum(a2), len(a2) - sum(a2), sum(b2), len(b2) - sum(b2))
    print(f"  contrast all8 vs g6fail:        {tab2} Fisher p={fisher(*tab2):.5f}")
    print()
    return g

strat(ab["rows"], "generator answerer")
strat(ab2["rows"], "independent answerer")

print("INTERPRETATION CHECK")
print("  paper's pooled contrast = all8 vs (g6fail + g6pass_g78fail)")
print("  g6fail share of rejected pool (generator):",
      f"{cnt['g6_answer_not_in_quote']}/{tot_rej} = {cnt['g6_answer_not_in_quote']/tot_rej:.2f}")
