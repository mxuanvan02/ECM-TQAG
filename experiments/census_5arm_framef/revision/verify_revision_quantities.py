#!/usr/bin/env python3
"""Recompute every NEW quantity added in the ECM-TQAG revision, from records/ alone.

Companion to the authors' verify_reported_quantities.py, which covers the 119
quantities already in the manuscript. This script covers the quantities added by
the revision: the three-stage admission decomposition, the six-gate sensitivity,
the leakage-removed sensitivity, the per-arm text-only-failure contrasts, and the
min-rater/mean-rater sensitivity on judged evidence correctness.

Standard library only. No network. Reads no page image, figure crop or source text.

Usage:  python3 revision/verify_revision_quantities.py [--check]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

RECORDS = Path(__file__).resolve().parents[1] / "records"

ARMS = ["ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct", "structured_no_contract"]
LABEL = {"ecm_v2": "ECM", "ecm_v2_disclosed": "DISC", "ecm_full": "PROV",
         "direct": "DIR", "structured_no_contract": "STR"}
IMAGE_GATES = ("g6_answer_not_in_quote", "g7_answer_meets_figure",
               "g8_description_meets_figure")


def load(name: str) -> dict:
    return json.loads((RECORDS / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- exact tests
def _logC(n: int, k: int) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def mcnemar_exact(b: int, d: int) -> float:
    """Two-sided exact McNemar, as Eq. (mcnemar) in the manuscript."""
    n = b + d
    if n == 0:
        return 1.0
    m = max(b, d)
    tail = sum(math.exp(_logC(n, i) + n * math.log(0.5)) for i in range(m, n + 1))
    return min(1.0, 2.0 * tail)


def sign_exact(a: int, b: int) -> float:
    """Two-sided exact sign test on discordant pairs; ties omitted."""
    return mcnemar_exact(a, b)


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact by summing tables no more probable than observed."""
    n = a + b + c + d
    r1, r2, c1 = a + b, c + d, a + c

    def lp(x: int) -> float:
        return (_logC(r1, x) + _logC(r2, c1 - x) - _logC(n, c1))

    obs = lp(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    tot = 0.0
    for x in range(lo, hi + 1):
        v = lp(x)
        if v <= obs + 1e-9:
            tot += math.exp(v)
    return min(1.0, tot)


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, tuple]:
    """Step-down Holm with stop-at-first-failure, as pre-registered."""
    order = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(order)
    out, still = {}, True
    for i, (k, p) in enumerate(order):
        thr = alpha / (m - i)
        rej = still and p <= thr
        if not rej:
            still = False
        out[k] = (p, thr, rej)
    return out


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P[X <= k] for X~Bin(n,p), evaluated directly for the small n here."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    return sum(math.exp(_logC(n, i) + i * math.log(p)
                        + (n - i) * math.log1p(-p)) for i in range(k + 1))


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Two-sided exact binomial interval without third-party packages."""
    if not 0 <= x <= n or n <= 0:
        raise ValueError("require 0 <= x <= n and n > 0")

    def bisect_decreasing(k: int, target: float) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if _binom_cdf(k, n, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if x == 0 else bisect_decreasing(x - 1, 1 - alpha / 2)
    upper = 1.0 if x == n else bisect_decreasing(x, alpha / 2)
    return lower, upper


def power_mcnemar(n: int, p01: float, p10: float, alpha: float = 0.05) -> float:
    """Exact power of the two-sided exact McNemar test at the given cell rates."""
    pd = p01 + p10
    if pd <= 0:
        return 0.0
    r = p01 / pd
    tot = 0.0
    for m in range(n + 1):
        lpm = _logC(n, m) + m * math.log(pd) + (n - m) * math.log1p(-pd)
        if lpm < -60:
            if m > n * pd + 10 * math.sqrt(n * pd * (1 - pd)):
                break
            continue
        acc = 0.0
        for b in range(m + 1):
            if mcnemar_exact(b, m - b) <= alpha:
                acc += math.exp(_logC(m, b) + b * math.log(r)
                                + (m - b) * math.log1p(-r))
        tot += math.exp(lpm) * acc
    return tot


# ------------------------------------------------------------------- results
def build() -> dict:
    adm = load("admission_decisions.json")["rows"]
    aiq = load("answer_in_question.json")
    gen = load("ablation_generator_answerer.json")["rows"]
    ind = load("ablation_independent_answerer.json")["rows"]
    judged = load("judged_scores.json")["rows"]
    proto = load("protocol.json")

    chunks = sorted({r["chunk_id"] for r in adm.values()})
    out: dict = {}

    # per (chunk, arm) gate state
    st = {}
    for r in adm.values():
        failed = set(r["failed_conditions"])
        ap = bool(r["provenance_admitted"])
        st[(r["chunk_id"], r["arm"])] = {
            "AP": ap,
            "A8": bool(r["admitted"]) if r["admitted"] is not None else False,
            "G6": ap and "g6_answer_not_in_quote" not in failed,
            "G78": ap and not ({"g7_answer_meets_figure",
                                "g8_description_meets_figure"} & failed),
        }

    # ---- 1. three-stage decomposition
    dec = {}
    for a in ARMS:
        ap = sum(st[(c, a)]["AP"] for c in chunks)
        g6 = sum(st[(c, a)]["G6"] for c in chunks)
        a8 = sum(st[(c, a)]["A8"] for c in chunks)
        g78_given_g6 = sum(st[(c, a)]["G78"] and st[(c, a)]["G6"] for c in chunks)
        dec[LABEL[a]] = {
            "AP": ap, "n": len(chunks),
            "G6_pass": g6, "G6_rate": round(g6 / ap, 4) if ap else None,
            "G78_given_G6": g78_given_g6,
            "G78_rate": round(g78_given_g6 / g6, 4) if g6 else None,
            "A8": a8, "A8_rate": round(a8 / len(chunks), 4),
            "product": round((ap / len(chunks)) * (g6 / ap) * (g78_given_g6 / g6), 4)
            if ap and g6 else None,
        }
    out["decomposition"] = dec

    # ---- 2. is the conditional G7^G8 rate distinguishable across arms?
    pairs = {}
    e_pass, e_n = dec["ECM"]["G78_given_G6"], dec["ECM"]["G6_pass"]
    for lb in ["DISC", "PROV", "DIR", "STR"]:
        o_pass, o_n = dec[lb]["G78_given_G6"], dec[lb]["G6_pass"]
        pairs[f"ECM_vs_{lb}"] = round(fisher_exact_2x2(
            e_pass, e_n - e_pass, o_pass, o_n - o_pass), 4)
    out["g78_conditional_fisher"] = pairs

    # ---- 3. six-gate variant (drop G7/G8)
    a6 = {LABEL[a]: sum(st[(c, a)]["G6"] for c in chunks) for a in ARMS}
    out["six_gate_counts"] = a6
    six = {}
    for lb in ["DISC", "PROV", "DIR", "STR"]:
        other = [a for a in ARMS if LABEL[a] == lb][0]
        b = sum(st[(c, "ecm_v2")]["G6"] and not st[(c, other)]["G6"] for c in chunks)
        d = sum(st[(c, other)]["G6"] and not st[(c, "ecm_v2")]["G6"] for c in chunks)
        six[f"ECM_vs_{lb}"] = {"b": b, "d": d, "p": mcnemar_exact(b, d)}
    out["six_gate_contrasts"] = {
        k: {"b": v["b"], "d": v["d"], "p": float(f"{v['p']:.4g}"),
            "thr": float(f"{t:.6g}"), "reject": rj}
        for (k, v), (_, (_, t, rj)) in zip(
            six.items(), holm({k: v["p"] for k, v in six.items()}).items())
    }
    # rank-flip pair DISC vs PROV on the six-gate rule
    b = sum(st[(c, "ecm_v2_disclosed")]["G6"] and not st[(c, "ecm_full")]["G6"]
            for c in chunks)
    d = sum(st[(c, "ecm_full")]["G6"] and not st[(c, "ecm_v2_disclosed")]["G6"]
            for c in chunks)
    out["six_gate_disc_vs_prov"] = {"b": b, "d": d,
                                    "p": float(f"{mcnemar_exact(b, d):.4g}")}

    # ---- 3b. G6-alone paired contrasts, restricted to pairs where BOTH arms
    # cleared provenance admission. This is the load-bearing-stage test the
    # revision reports: the disclosure arm states G6 verbatim, so the contrast
    # asks whether being told the string test suffices to pass it.
    g6a = {}
    for lb in ["DISC", "PROV", "DIR", "STR"]:
        other = [a for a in ARMS if LABEL[a] == lb][0]
        both = [c for c in chunks
                if st[(c, "ecm_v2")]["AP"] and st[(c, other)]["AP"]]
        b = sum(st[(c, "ecm_v2")]["G6"] and not st[(c, other)]["G6"] for c in both)
        d = sum(st[(c, other)]["G6"] and not st[(c, "ecm_v2")]["G6"] for c in both)
        g6a[f"ECM_vs_{lb}"] = {"n_pairs": len(both), "b": b, "d": d,
                               "p": mcnemar_exact(b, d)}
    hg6 = holm({k: v["p"] for k, v in g6a.items()})
    out["g6_alone_contrasts"] = {
        k: {"n_pairs": v["n_pairs"], "b": v["b"], "d": v["d"],
            "p": float(f"{v['p']:.4g}"),
            "thr": float(f"{hg6[k][1]:.6g}"), "reject": hg6[k][2]}
        for k, v in g6a.items()
    }
    out["g6_alone_ratio"] = round(dec["ECM"]["G6_rate"] / dec["DISC"]["G6_rate"], 3)

    # ---- 4. leakage x admission
    out["leak_per_arm"] = {LABEL[a]: aiq["per_arm"][a] for a in ARMS}
    out["leak_totals"] = {"n_rows": aiq["n_rows"],
                          "n_leak": aiq["n_answer_in_question"],
                          "n_leak_all_eight": aiq["n_answer_in_question_passing_all_eight"],
                          "crosstab_vs_g6": aiq["cross_tabulation_against_g6"]}

    # ---- 5. leakage-removed sensitivity on the confirmatory family
    leak_ids = {k for k, r in aiq["rows"].items() if r["answer_in_question"]}

    def clean(c: str, a: str) -> bool:
        return st[(c, a)]["A8"] and f"{c}::{a}" not in leak_ids

    out["a8_clean_counts"] = {LABEL[a]: sum(clean(c, a) for c in chunks) for a in ARMS}
    raw = {}
    for lb in ["DISC", "PROV", "DIR", "STR"]:
        other = [a for a in ARMS if LABEL[a] == lb][0]
        b = sum(clean(c, "ecm_v2") and not clean(c, other) for c in chunks)
        d = sum(clean(c, other) and not clean(c, "ecm_v2") for c in chunks)
        raw[f"ECM_vs_{lb}"] = {"b": b, "d": d, "p": mcnemar_exact(b, d)}
    hres = holm({k: v["p"] for k, v in raw.items()})
    out["a8_clean_contrasts"] = {
        k: {"b": raw[k]["b"], "d": raw[k]["d"], "p": float(f"{hres[k][0]:.4g}"),
            "thr": float(f"{hres[k][1]:.6g}"), "reject": hres[k][2]}
        for k in raw
    }

    # ---- 6. per-arm text-only failure, on the 225 graded denominator
    excl = set(proto["documents"]["ablation_preregistration"]["document"]
               ["declared_exclusion_before_execution"]["item_ids"])
    out["declared_exclusions"] = sorted(excl)

    def vstar_table(rows: dict) -> dict:
        res, tot = {}, {"adm_yes": 0, "adm_n": 0, "rej_yes": 0, "rej_n": 0}
        for a in ARMS:
            cells = {"adm_yes": 0, "adm_n": 0, "rej_yes": 0, "rej_n": 0}
            for iid, r in rows.items():
                if r["arm"] != a or iid in excl:
                    continue
                if r["text_only"]["status"] != "COMPLETE":
                    continue
                cid = iid.rsplit("::", 1)[0]
                if not st[(cid, a)]["AP"]:
                    continue
                v = not r["text_only"]["correct_at_primary_threshold"]
                key = "adm" if st[(cid, a)]["A8"] else "rej"
                cells[f"{key}_n"] += 1
                cells[f"{key}_yes"] += int(v)
            for k in cells:
                tot[k] += cells[k]
            res[LABEL[a]] = {
                "admitted": f"{cells['adm_yes']}/{cells['adm_n']}",
                "rejected": f"{cells['rej_yes']}/{cells['rej_n']}",
                "delta": round(
                    (cells["adm_yes"] / cells["adm_n"] if cells["adm_n"] else 0)
                    - (cells["rej_yes"] / cells["rej_n"] if cells["rej_n"] else 0), 4),
                "fisher_p": float(f"{fisher_exact_2x2(cells['adm_yes'], cells['adm_n'] - cells['adm_yes'], cells['rej_yes'], cells['rej_n'] - cells['rej_yes']):.4g}"),
            }
        res["POOLED"] = {
            "admitted": f"{tot['adm_yes']}/{tot['adm_n']}",
            "rejected": f"{tot['rej_yes']}/{tot['rej_n']}",
            "fisher_p": float(f"{fisher_exact_2x2(tot['adm_yes'], tot['adm_n'] - tot['adm_yes'], tot['rej_yes'], tot['rej_n'] - tot['rej_yes']):.6g}"),
        }
        return res

    out["vstar_generator"] = vstar_table(gen)
    out["vstar_independent"] = vstar_table(ind)

    # ---- 7. power of the paired figure-recovery contrast
    pw = {}
    for tag, b, d, n in [("generator", 16, 8, 225), ("independent", 10, 6, 225)]:
        p01, p10 = b / n, d / n
        lo, hi = n, 4000
        while lo < hi:
            mid = (lo + hi) // 2
            if power_mcnemar(mid, p01, p10) >= 0.80:
                hi = mid
            else:
                lo = mid + 1
        pw[tag] = {"b": b, "d": d, "n": n,
                   "power_at_n": round(power_mcnemar(n, p01, p10), 3),
                   "n_for_power_80": lo,
                   "ratio": round(lo / n, 2)}
    out["figure_recovery_power"] = pw

    # ---- 8. min-rater vs mean-rater on judged criteria
    raters = ["claude-opus-5", "gpt-5.6-sol"]

    def judged_pairs(crit: str, agg: str) -> dict:
        res = {}
        for lb in ["DISC", "PROV", "DIR", "STR"]:
            other = [a for a in ARMS if LABEL[a] == lb][0]
            e_better = o_better = ties = 0
            for c in chunks:
                ke, ko = f"{c}::ecm_v2", f"{c}::{other}"
                if ke not in judged or ko not in judged:
                    continue
                try:
                    ve = [judged[ke][r][crit] for r in raters]
                    vo = [judged[ko][r][crit] for r in raters]
                except KeyError:
                    continue
                f = min if agg == "min" else (lambda xs: sum(xs) / len(xs))
                se, so = f(ve), f(vo)
                if se > so:
                    e_better += 1
                elif so > se:
                    o_better += 1
                else:
                    ties += 1
            res[lb] = {"n": e_better + o_better + ties,
                       "ecm": e_better, "control": o_better, "ties": ties,
                       "p": float(f"{sign_exact(e_better, o_better):.4g}"),
                       "below_floor": (e_better + o_better + ties) < 40}
        return res

    out["judged_sensitivity"] = {
        f"{crit}_{agg}": judged_pairs(crit, agg)
        for crit in ("evidence_correctness", "visual_necessity")
        for agg in ("min", "mean")
    }

    # ---- 9. exact intervals and a post-hoc joint utility endpoint
    # U_t requires full admission, evidence-correctness >= t from BOTH raters,
    # and no critical-provenance flag from either rater. Threshold 4 is the
    # conservative main specification; 3 and 5 are declared sensitivities.
    admission_ci = {}
    for a in ARMS:
        lb = LABEL[a]
        x = sum(st[(c, a)]["A8"] for c in chunks)
        lo, hi = clopper_pearson(x, len(chunks))
        admission_ci[lb] = {"x": x, "n": len(chunks),
                            "lo": round(lo, 4), "hi": round(hi, 4)}
    out["admission_exact_ci"] = admission_ci

    joint = {}
    for threshold in (3, 4, 5):
        passed = {}
        per_arm = {}
        for a in ARMS:
            lb = LABEL[a]
            correctness_only = 0
            utility = 0
            for c in chunks:
                key = f"{c}::{a}"
                scores = judged.get(key)
                if not scores or any(r not in scores for r in raters):
                    passed[(c, a)] = False
                    continue
                correct = all(scores[r]["evidence_correctness"] >= threshold
                              for r in raters)
                no_critical = not any(scores[r]["critical_provenance_violation"]
                                      for r in raters)
                correctness_only += int(correct and no_critical)
                u = st[(c, a)]["A8"] and correct and no_critical
                passed[(c, a)] = u
                utility += int(u)
            lo, hi = clopper_pearson(utility, len(chunks))
            per_arm[lb] = {"correctness_only": correctness_only,
                           "U": utility, "n": len(chunks),
                           "lo": round(lo, 4), "hi": round(hi, 4)}

        contrasts = {}
        for lb in ["DISC", "PROV", "DIR", "STR"]:
            other = next(a for a in ARMS if LABEL[a] == lb)
            b = sum(passed.get((c, "ecm_v2"), False)
                    and not passed.get((c, other), False) for c in chunks)
            d = sum(passed.get((c, other), False)
                    and not passed.get((c, "ecm_v2"), False) for c in chunks)
            contrasts[f"ECM_vs_{lb}"] = {
                "b": b, "d": d, "p": float(f"{mcnemar_exact(b, d):.4g}")}
        joint[str(threshold)] = {"per_arm": per_arm,
                                 "contrasts": contrasts}
    out["joint_utility"] = joint
    return out


# ------------------------------------------------------------------- asserted
# Every value the revision states in prose or in a table. (path, expected).
PAPER: list[tuple[str, str, object]] = [
    # decomposition, as printed in the new table
    ("decomp ECM AP", "decomposition.ECM.AP", 50),
    ("decomp ECM G6 pass", "decomposition.ECM.G6_pass", 35),
    ("decomp ECM G6 rate", "decomposition.ECM.G6_rate", 0.70),
    ("decomp ECM G78|G6", "decomposition.ECM.G78_given_G6", 24),
    ("decomp ECM G78 rate", "decomposition.ECM.G78_rate", 0.6857),
    ("decomp ECM A8", "decomposition.ECM.A8", 24),
    ("decomp DISC G6 rate", "decomposition.DISC.G6_rate", 0.375),
    ("decomp DISC G78|G6", "decomposition.DISC.G78_given_G6", 10),
    ("decomp DISC G78 rate", "decomposition.DISC.G78_rate", 0.5556),
    ("decomp PROV G6 rate", "decomposition.PROV.G6_rate", 0.2927),
    ("decomp PROV G78 rate", "decomposition.PROV.G78_rate", 0.9167),
    ("decomp DIR G6 rate", "decomposition.DIR.G6_rate", 0.1591),
    ("decomp DIR G78 rate", "decomposition.DIR.G78_rate", 0.8571),
    ("decomp STR G6 rate", "decomposition.STR.G6_rate", 0.2273),
    ("decomp STR G78 rate", "decomposition.STR.G78_rate", 0.60),
    # conditional G7^G8 not distinguishable
    ("G78 cond ECM vs PROV p", "g78_conditional_fisher.ECM_vs_PROV", 0.1459),
    ("G78 cond ECM vs DISC p", "g78_conditional_fisher.ECM_vs_DISC", 0.3797),
    ("G78 cond ECM vs DIR p", "g78_conditional_fisher.ECM_vs_DIR", 0.6514),
    # six-gate sensitivity
    ("six-gate ECM", "six_gate_counts.ECM", 35),
    ("six-gate DISC", "six_gate_counts.DISC", 18),
    ("six-gate PROV", "six_gate_counts.PROV", 12),
    ("six-gate DIR", "six_gate_counts.DIR", 7),
    ("six-gate STR", "six_gate_counts.STR", 10),
    ("six-gate ECM vs DIR p", "six_gate_contrasts.ECM_vs_DIR.p", 5.774e-08),
    ("six-gate ECM vs DISC p", "six_gate_contrasts.ECM_vs_DISC.p", 0.0004883),
    ("six-gate all four reject", "six_gate_contrasts.ECM_vs_PROV.reject", True),
    ("six-gate DISC vs PROV p", "six_gate_disc_vs_prov.p", 0.3075),
    # G6-alone contrasts: disclosure states the criterion verbatim
    ("G6-alone DISC pairs", "g6_alone_contrasts.ECM_vs_DISC.n_pairs", 43),
    ("G6-alone DISC b", "g6_alone_contrasts.ECM_vs_DISC.b", 13),
    ("G6-alone DISC d", "g6_alone_contrasts.ECM_vs_DISC.d", 2),
    ("G6-alone DISC p", "g6_alone_contrasts.ECM_vs_DISC.p", 0.007385),
    ("G6-alone DISC rejects", "g6_alone_contrasts.ECM_vs_DISC.reject", True),
    ("G6-alone PROV pairs", "g6_alone_contrasts.ECM_vs_PROV.n_pairs", 34),
    ("G6-alone PROV b", "g6_alone_contrasts.ECM_vs_PROV.b", 18),
    ("G6-alone PROV d", "g6_alone_contrasts.ECM_vs_PROV.d", 0),
    ("G6-alone PROV p", "g6_alone_contrasts.ECM_vs_PROV.p", 7.629e-06),
    ("G6-alone DIR pairs", "g6_alone_contrasts.ECM_vs_DIR.n_pairs", 40),
    ("G6-alone DIR b", "g6_alone_contrasts.ECM_vs_DIR.b", 26),
    ("G6-alone DIR p", "g6_alone_contrasts.ECM_vs_DIR.p", 4.172e-07),
    ("G6-alone STR pairs", "g6_alone_contrasts.ECM_vs_STR.n_pairs", 38),
    ("G6-alone STR b", "g6_alone_contrasts.ECM_vs_STR.b", 21),
    ("G6-alone STR p", "g6_alone_contrasts.ECM_vs_STR.p", 1.097e-05),
    ("G6-alone ECM/DISC rate ratio", "g6_alone_ratio", 1.867),
    # leakage x admission
    ("leak ECM", "leak_per_arm.ECM.answer_in_question", 7),
    ("leak ECM and all eight", "leak_per_arm.ECM.answer_in_question_and_passed_all_eight", 3),
    ("leak DISC and all eight", "leak_per_arm.DISC.answer_in_question_and_passed_all_eight", 1),
    ("leak PROV and all eight", "leak_per_arm.PROV.answer_in_question_and_passed_all_eight", 0),
    ("leak total all eight", "leak_totals.n_leak_all_eight", 4),
    # leakage-removed sensitivity
    ("A8 clean ECM", "a8_clean_counts.ECM", 21),
    ("A8 clean DISC", "a8_clean_counts.DISC", 9),
    ("A8 clean PROV", "a8_clean_counts.PROV", 11),
    ("A8 clean ECM vs PROV p", "a8_clean_contrasts.ECM_vs_PROV.p", 0.05248),
    ("A8 clean ECM vs PROV not rejected", "a8_clean_contrasts.ECM_vs_PROV.reject", False),
    ("A8 clean ECM vs DISC rejected", "a8_clean_contrasts.ECM_vs_DISC.reject", True),
    ("A8 clean ECM vs DIR p", "a8_clean_contrasts.ECM_vs_DIR.p", 0.002599),
    # per-arm V*, generator
    ("V* gen ECM admitted", "vstar_generator.ECM.admitted", "14/24"),
    ("V* gen ECM rejected", "vstar_generator.ECM.rejected", "12/26"),
    ("V* gen ECM p", "vstar_generator.ECM.fisher_p", 0.4129),
    ("V* gen PROV p", "vstar_generator.PROV.fisher_p", 0.07429),
    ("V* gen DIR p", "vstar_generator.DIR.fisher_p", 1.0),
    ("V* gen pooled admitted", "vstar_generator.POOLED.admitted", "33/57"),
    ("V* gen pooled rejected", "vstar_generator.POOLED.rejected", "64/168"),
    ("V* gen pooled p (published)", "vstar_generator.POOLED.fisher_p", 0.012908),
    ("V* ind pooled admitted", "vstar_independent.POOLED.admitted", "34/57"),
    ("V* ind pooled rejected", "vstar_independent.POOLED.rejected", "71/168"),
    ("V* ind pooled p (published)", "vstar_independent.POOLED.fisher_p", 0.031059),
    ("V* ind ECM p", "vstar_independent.ECM.fisher_p", 0.5835),
    # power
    ("power gen at 225", "figure_recovery_power.generator.power_at_n", 0.295),
    ("power ind at 225", "figure_recovery_power.independent.power_at_n", 0.114),
    ("n for power .80 gen", "figure_recovery_power.generator.n_for_power_80", 700),
    ("n for power .80 ind", "figure_recovery_power.independent.n_for_power_80", 1850),
    # judged sensitivity: min-rater reproduces the published table
    ("judged min DISC n", "judged_sensitivity.evidence_correctness_min.DISC.n", 43),
    ("judged min DISC ecm/ctrl", "judged_sensitivity.evidence_correctness_min.DISC.control", 25),
    ("judged min DISC p", "judged_sensitivity.evidence_correctness_min.DISC.p", 0.0003249),
    ("judged min DIR p", "judged_sensitivity.evidence_correctness_min.DIR.p", 0.0001922),
    ("judged min PROV n", "judged_sensitivity.evidence_correctness_min.PROV.n", 34),
    ("judged min STR n", "judged_sensitivity.evidence_correctness_min.STR.n", 38),
    # mean-rater sensitivity, new
    ("judged mean DISC p", "judged_sensitivity.evidence_correctness_mean.DISC.p", 0.0005083),
    ("judged mean PROV p", "judged_sensitivity.evidence_correctness_mean.PROV.p", 0.0005461),
    ("judged mean DIR p", "judged_sensitivity.evidence_correctness_mean.DIR.p", 6.619e-05),
    ("judged mean STR p", "judged_sensitivity.evidence_correctness_mean.STR.p", 0.001319),
    ("necessity min DISC p", "judged_sensitivity.visual_necessity_min.DISC.p", 1.0),
    ("necessity mean DISC p", "judged_sensitivity.visual_necessity_mean.DISC.p", 0.845),
    # exact admission intervals for every arm
    ("admission CI ECM low", "admission_exact_ci.ECM.lo", 0.2756),
    ("admission CI ECM high", "admission_exact_ci.ECM.hi", 0.5346),
    ("admission CI DISC low", "admission_exact_ci.DISC.lo", 0.0829),
    ("admission CI DISC high", "admission_exact_ci.DISC.hi", 0.2852),
    ("admission CI PROV low", "admission_exact_ci.PROV.lo", 0.0952),
    ("admission CI PROV high", "admission_exact_ci.PROV.hi", 0.3044),
    ("admission CI DIR low", "admission_exact_ci.DIR.lo", 0.0376),
    ("admission CI DIR high", "admission_exact_ci.DIR.hi", 0.2051),
    ("admission CI STR low", "admission_exact_ci.STR.lo", 0.0376),
    ("admission CI STR high", "admission_exact_ci.STR.hi", 0.2051),
    # post-hoc joint endpoint U at the conservative threshold 4
    ("joint U4 ECM", "joint_utility.4.per_arm.ECM.U", 4),
    ("joint U4 DISC", "joint_utility.4.per_arm.DISC.U", 3),
    ("joint U4 PROV", "joint_utility.4.per_arm.PROV.U", 5),
    ("joint U4 DIR", "joint_utility.4.per_arm.DIR.U", 2),
    ("joint U4 STR", "joint_utility.4.per_arm.STR.U", 1),
    ("joint U4 ECM CI low", "joint_utility.4.per_arm.ECM.lo", 0.0185),
    ("joint U4 ECM CI high", "joint_utility.4.per_arm.ECM.hi", 0.1620),
    ("joint U4 ECM vs DISC p", "joint_utility.4.contrasts.ECM_vs_DISC.p", 1.0),
    ("joint U4 ECM vs PROV p", "joint_utility.4.contrasts.ECM_vs_PROV.p", 1.0),
    ("joint U4 ECM vs DIR p", "joint_utility.4.contrasts.ECM_vs_DIR.p", 0.625),
    ("joint U4 ECM vs STR p", "joint_utility.4.contrasts.ECM_vs_STR.p", 0.25),
    # threshold sensitivities: all printed arm counts and p-values
    ("joint U3 ECM", "joint_utility.3.per_arm.ECM.U", 9),
    ("joint U3 DISC", "joint_utility.3.per_arm.DISC.U", 6),
    ("joint U3 PROV", "joint_utility.3.per_arm.PROV.U", 7),
    ("joint U3 DIR", "joint_utility.3.per_arm.DIR.U", 2),
    ("joint U3 STR", "joint_utility.3.per_arm.STR.U", 2),
    ("joint U3 ECM vs DISC p", "joint_utility.3.contrasts.ECM_vs_DISC.p", 0.4531),
    ("joint U3 ECM vs PROV p", "joint_utility.3.contrasts.ECM_vs_PROV.p", 0.7905),
    ("joint U3 ECM vs DIR p", "joint_utility.3.contrasts.ECM_vs_DIR.p", 0.03906),
    ("joint U3 ECM vs STR p", "joint_utility.3.contrasts.ECM_vs_STR.p", 0.03906),
    ("joint U5 ECM", "joint_utility.5.per_arm.ECM.U", 1),
    ("joint U5 DISC", "joint_utility.5.per_arm.DISC.U", 2),
    ("joint U5 PROV", "joint_utility.5.per_arm.PROV.U", 1),
    ("joint U5 DIR", "joint_utility.5.per_arm.DIR.U", 0),
    ("joint U5 STR", "joint_utility.5.per_arm.STR.U", 1),
    ("joint U5 ECM vs DISC p", "joint_utility.5.contrasts.ECM_vs_DISC.p", 1.0),
    ("joint U5 ECM vs PROV p", "joint_utility.5.contrasts.ECM_vs_PROV.p", 1.0),
    ("joint U5 ECM vs DIR p", "joint_utility.5.contrasts.ECM_vs_DIR.p", 1.0),
    ("joint U5 ECM vs STR p", "joint_utility.5.contrasts.ECM_vs_STR.p", 1.0),
]


def dig(tree: dict, path: str):
    cur = tree
    for part in path.split("."):
        cur = cur[part]
    return cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    tree = build()

    if not args.check:
        print(json.dumps(tree, indent=2, ensure_ascii=False))
        print(f"\n(run with --check to assert these against the manuscript)")
        return 0

    print("checking new revision quantities against the manuscript\n")
    bad = 0
    for label, path, expected in PAPER:
        got = dig(tree, path)
        if isinstance(expected, bool):
            ok = got is expected
        elif isinstance(expected, float):
            ok = abs(float(got) - expected) <= max(1e-6, abs(expected) * 5e-3)
        else:
            ok = got == expected
        if not ok:
            bad += 1
            print(f"  MISMATCH {label}: got {got!r}, manuscript says {expected!r}")
    print(f"checked: {len(PAPER)}   mismatches: {bad}\n")
    if bad:
        print("VERDICT: at least one new quantity does not recompute")
        return 1
    print("VERDICT: every new quantity recomputes from the released records")
    return 0


if __name__ == "__main__":
    sys.exit(main())
