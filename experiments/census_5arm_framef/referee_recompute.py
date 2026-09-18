"""Two referee-side recomputations the manuscript does not report:
(1) MC-subset claim "answered from text in 28 of 30 cases"
(2) a SECTION-CLUSTERED permutation p-value for the V* contrast, i.e. what the
    honest number is once the 60-section clustering is respected.
"""
import json
import random
from collections import defaultdict
from math import comb

ad = json.load(open("records/admission_decisions.json"))["rows"]
ab = json.load(open("records/ablation_generator_answerer.json"))
ab2 = json.load(open("records/ablation_independent_answerer.json"))

adm = {}
for r in (ad.values() if isinstance(ad, dict) else ad):
    adm[f"{r['chunk_id']}::{r['arm']}"] = r

def txt_correct(row):
    to = row["text_only"]
    return None if to.get("status") != "COMPLETE" else bool(to["correct_at_primary_threshold"])

# ---- (1) MC subset ----
for nm, blob in (("generator", ab), ("independent", ab2)):
    rows = blob["rows"]
    rows = rows.values() if isinstance(rows, dict) else rows
    mc = [r for r in rows if r.get("question_type") == "multiple_choice"]
    ok = sum(1 for r in mc if txt_correct(r) is True)
    sa = [r for r in rows if r.get("question_type") == "short_answer"]
    oksa = sum(1 for r in sa if txt_correct(r) is True)
    print(f"{nm}: MC answered-from-text {ok}/{len(mc)} (paper: 28/30) | SA {oksa}/{len(sa)}")

print()

# ---- (2) section-clustered permutation test on V* ----
def build(rows, blob_rows):
    """Return list of (section_id, group_label, vstar) for the 227 items."""
    out = []
    for iid, r in blob_rows.items():
        a = adm.get(iid)
        c = txt_correct(r)
        if a is None or c is None:
            continue
        sec = iid.rsplit("::", 1)[0]  # item_id = frameF::doc::section::arm
        grp = "admitted" if a["admitted"] else "rejected"
        out.append((sec, grp, 0 if c else 1))
    return out

def stat_diff(recs):
    """observed statistic: V*_admitted - V*_rejected."""
    g = defaultdict(list)
    for sec, grp, v in recs:
        g[grp].append(v)
    a, b = g["admitted"], g["rejected"]
    return sum(a) / len(a) - sum(b) / len(b), len(a), len(b)

def clustered_perm(recs, n_perm=20000, seed=0):
    """Permute group labels at the SECTION level (cluster-respecting null)."""
    by_sec = defaultdict(list)
    for sec, grp, v in recs:
        by_sec[sec].append((grp, v))
    secs = sorted(by_sec)
    # section-level group signature (multiset of labels) stays attached to section
    sigs = {s: [g for g, _ in by_sec[s]] for s in secs}
    obs, na, nb = stat_diff(recs)
    rng = random.Random(seed)
    ge = 0
    for _ in range(n_perm):
        perm = secs[:]
        rng.shuffle(perm)
        # reassign each section's label-signature to another section's items
        ad_s, rj_s = 0.0, 0.0
        n_ad = n_rj = 0
        for src, dst in zip(secs, perm):
            vals = [v for _, v in by_sec[dst]]
            labs = sigs[src]
            for lab, v in zip(labs, vals):
                if lab == "admitted":
                    ad_s += v; n_ad += 1
                else:
                    rj_s += v; n_rj += 1
        if n_ad and n_rj:
            d = ad_s / n_ad - rj_s / n_rj
            if abs(d) >= abs(obs) - 1e-12:
                ge += 1
    return obs, na, nb, (ge + 1) / (n_perm + 1)

for nm, blob in (("generator", ab), ("independent", ab2)):
    recs = build(None, blob["rows"])
    obs, na, nb, p = clustered_perm(recs, n_perm=20000, seed=42)
    print(f"{nm}: n_sections={len({s for s,_,_ in recs})}  "
          f"V*_adm-V*_rej={obs:+.3f} (n={na} vs {nb})")
    print(f"   SECTION-CLUSTERED permutation p = {p:.4f}   "
          f"(paper's item-level Fisher p = 0.013 / 0.031)")
print()
print("If the clustered p is >> 0.05, the significance claim does not survive the")
print("clustering the manuscript itself discloses but does not correct for.")
