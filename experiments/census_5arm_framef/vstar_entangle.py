"""V*-entanglement: join admission_decisions (failed_conditions) with ablation rows.
Test: is the 0.58-vs-0.38 contrast partly mechanical because G6-fail puts the
answer verbatim inside the quotation, which the text-only answerer can copy?
"""
import json

ad = json.load(open("records/admission_decisions.json"))["rows"]
ab = json.load(open("records/ablation_generator_answerer.json"))["rows"]
ab2 = json.load(open("records/ablation_independent_answerer.json"))["rows"]

# rows are dicts keyed by item_id; index admission by frameF::doc::section::arm
adm = {}
for r in (ad.values() if isinstance(ad, dict) else ad):
    key = f"{r['chunk_id']}::{r['arm']}"
    adm[key] = r

def vstar(row):
    """V* = 1 - R_txt : item NOT answerable from text alone."""
    to = row["text_only"]
    if to.get("status") != "COMPLETE":
        return None
    return 0 if to["correct_at_primary_threshold"] else 1

def stratify(rows, label):
    groups = {"all8": [], "g6_fail": [], "g6pass_g78_fail": []}
    missing = 0
    for item_id, row in rows.items():
        a = adm.get(item_id)
        if a is None:
            missing += 1
            continue
        v = vstar(row)
        if v is None:
            continue
        fc = set(a["failed_conditions"])
        if not fc:
            groups["all8"].append(v)
        elif "g6_answer_not_in_quote" in fc:
            groups["g6_fail"].append(v)
        else:
            groups["g6pass_g78_fail"].append(v)
    print(f"--- {label} (missing join: {missing}) ---")
    for g, vs in groups.items():
        if vs:
            print(f"  {g:20s} n={len(vs):3d}  V*={sum(vs)/len(vs):.3f} ({sum(vs)}/{len(vs)})")
    return groups

g1 = stratify(ab, "generator answerer")
g2 = stratify(ab2, "independent answerer")

# key contrast: among G6-PASS items only, do fully-admitted still differ from G7/G8-fail?
print()
print("KEY: within G6-pass stratum, all8 vs g6pass_g78_fail (non-mechanical part):")
for nm, g in (("generator", g1), ("independent", g2)):
    a, b = g["all8"], g["g6pass_g78_fail"]
    if a and b:
        print(f"  {nm}: all8 V*={sum(a)/len(a):.3f} (n={len(a)})  vs  g78fail V*={sum(b)/len(b):.3f} (n={len(b)})")

# sanity: recompute paper's 33/57 vs 64/168 (generator)
allv = [v for row in ab.values() if (v := vstar(row)) is not None]
adm_v = [v for iid, row in ab.items() if adm.get(iid, {}).get("admitted") and (v := vstar(row)) is not None]
rej_v = [v for iid, row in ab.items() if iid in adm and not adm[iid]["admitted"] and (v := vstar(row)) is not None]
print()
print(f"sanity generator: admitted V*={sum(adm_v)}/{len(adm_v)} (paper 33/57) | rejected V*={sum(rej_v)}/{len(rej_v)} (paper 64/168)")
