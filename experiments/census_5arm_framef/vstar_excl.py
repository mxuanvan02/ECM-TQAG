"""Locate the 2 declared-exclusion items, assign their stratum, redo the
non-mechanical contrast on the exact 225-item denominator the paper uses."""
import json
from math import comb

ad = json.load(open("records/admission_decisions.json"))["rows"]
ab = json.load(open("records/ablation_generator_answerer.json"))
ab2 = json.load(open("records/ablation_independent_answerer.json"))

adm = {}
for r in (ad.values() if isinstance(ad, dict) else ad):
    adm[f"{r['chunk_id']}::{r['arm']}"] = r

def fisher(a, b, c, d):
    n = a + b + c + d; r1, r2, c1 = a + b, c + d, a + c
    def p(x): return comb(r1, x) * comb(r2, c1 - x) / comb(n, c1)
    po = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1)
                        if p(x) <= po * (1 + 1e-9)))

def vstar(row):
    to = row["text_only"]
    return None if to.get("status") != "COMPLETE" else (0 if to["correct_at_primary_threshold"] else 1)

# find rows the paper excludes: n_items field 227 but reported denom 225.
# exclusion rule: gold answer folds to <=2 chars. Detect via grading metadata if present.
print("ablation grading meta:", json.dumps(ab.get("grading"), ensure_ascii=False)[:300])
print("thresholds_source:", str(ab.get("thresholds_source"))[:160])
print("why:", str(ab.get("why"))[:200])
print()

# Reconstruct the 225 set the same way the verifier does: drop rows whose
# recorded exclusion flag is set. Inspect a row for such a flag.
sample = next(iter(ab["rows"].values()))
print("row keys:", list(sample.keys()))
print("has exclusion flag?", [k for k in sample if "excl" in k.lower()])
print()

# The verifier reproduces 33/57 and 64/168. Reconstruct by matching totals.
def strat(rows, drop_v1_rejected=0):
    g = {"all8": [], "g6pass_g78fail": [], "g6fail": []}
    for iid, row in rows.items():
        a = adm.get(iid); v = vstar(row)
        if a is None or v is None: continue
        fc = set(a["failed_conditions"])
        key = "all8" if not fc else ("g6fail" if "g6_answer_not_in_quote" in fc else "g6pass_g78fail")
        g[key].append((v, iid))
    return g

g = strat(ab["rows"])
for k in g: print(f"{k}: n={len(g[k])} V*=1:{sum(v for v,_ in g[k])}")
tot = sum(len(v) for v in g.values()); print("total joined:", tot, "(paper 227 -> 225 after excl. 2)")
print()
# paper: admitted 57 (matches all8=57). rejected 168 = g6fail+g6pass_g78fail - 2.
rej = len(g["g6fail"]) + len(g["g6pass_g78fail"])
print(f"rejected joined = {rej} (paper reports 168) -> excluded {rej-168} from rejected pool")
print(f"admitted joined = {len(g['all8'])} (paper 57) -> excluded 0 from admitted pool")
print()
print("=> the 2 excluded items are BOTH in the rejected pool, 0 in the admitted pool.")
print("=> the non-mechanical stratum (all8 vs g6pass_g78fail) is unaffected by the exclusion")
print("   because all8=57 matches the paper exactly and g6pass_g78fail loses at most 2 rows.")
print()
# redo non-mechanical contrast excluding up-to-2 from g6pass_g78fail worst case
a = g["all8"]; b = g["g6pass_g78fail"]
sa = sum(v for v, _ in a); sb = sum(v for v, _ in b)
tab = (sa, len(a) - sa, sb, len(b) - sb)
print(f"all8 vs g6pass_g78fail (all 25): {tab} Fisher p={fisher(*tab):.3f}")
# worst case: drop 2 from g6pass_g78fail that had V*=1 (most favourable to paper)
sb2 = max(0, sb - 2); nb2 = len(b) - 2
tab2 = (sa, len(a) - sa, sb2, nb2 - sb2)
print(f"  if both excl. were V*=1 here: {tab2} Fisher p={fisher(*tab2):.3f}")
# worst case other direction
tab3 = (sa, len(a) - sa, sb, len(b) - 2 - sb)
print(f"  if both excl. were V*=0 here: {tab3} Fisher p={fisher(*tab3):.3f}")
