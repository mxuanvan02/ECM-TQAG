#!/usr/bin/env python3
"""Recompute every quantity the ECM-TQAG manuscript reports, from records/ alone.

This script reads only the JSON files published beside it under ``records/``.
It uses nothing outside the Python standard library, makes no network call, and
reads no page image, figure crop, or source text: the published records carry
graded decisions and rater scores, not the items themselves.

    python3 verify_reported_quantities.py           # print recomputed values
    python3 verify_reported_quantities.py --check   # assert them against the paper

Exit status is 0 when every check passes and 1 when any check fails, so the
script doubles as a regression test on the released records.

One thing to read carefully. The two ablation runs did not tabulate the same
grid of F1 thresholds: the pre-registered run reports seven and the replication
nine. Counting each on its own grid would compare different denominators, so the
threshold comparison is computed on the seven thresholds BOTH runs tabulate, and
the two extra points are reported separately rather than folded in.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
RECORDS = HERE / "records"

ARMS = ("ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct", "structured_no_contract")
CONTRACT = "ecm_v2"
RATERS = ("claude-opus-5", "gpt-5.6-sol")
BRANCHES = ("text_only", "text_image")
PRIMARY = "0.70"
CRITERIA = ("evidence_correctness", "answerability", "visual_necessity",
            "pedagogical_value", "vietnamese_language")


def load(name: str) -> dict[str, Any]:
    path = RECORDS / name
    if not path.is_file():
        raise SystemExit(f"missing released record: records/{name}")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# exact statistics, all from the standard library
# --------------------------------------------------------------------------
def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> list[float]:
    """Exact binomial interval, inverted from the beta quantile by bisection."""
    if n == 0:
        return [0.0, 0.0]

    def beta_cdf(x: float, a: float, b: float) -> float:
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        # regularised incomplete beta by continued fraction
        lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
        front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
        f, c, d = 1.0, 1.0, 0.0
        for i in range(0, 300):
            m = i // 2
            if i == 0:
                num = 1.0
            elif i % 2 == 0:
                num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
            else:
                num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
            d = 1.0 + num * d
            d = 1e-30 if abs(d) < 1e-30 else d
            d = 1.0 / d
            c = 1.0 + num / c
            c = 1e-30 if abs(c) < 1e-30 else c
            f *= c * d
            if abs(1.0 - c * d) < 1e-12:
                break
        result = front * (f - 1.0)
        return result if x < (a + 1) / (a + b + 2) else 1.0 - beta_cdf_swap(x, a, b, lbeta)

    def beta_cdf_swap(x: float, a: float, b: float, lbeta: float) -> float:
        front = math.exp(math.log(1 - x) * b + math.log(x) * a - lbeta) / b
        f, c, d = 1.0, 1.0, 0.0
        y = 1 - x
        for i in range(0, 300):
            m = i // 2
            if i == 0:
                num = 1.0
            elif i % 2 == 0:
                num = (m * (a - m) * y) / ((b + 2 * m - 1) * (b + 2 * m))
            else:
                num = -((b + m) * (a + b + m) * y) / ((b + 2 * m) * (b + 2 * m + 1))
            d = 1.0 + num * d
            d = 1e-30 if abs(d) < 1e-30 else d
            d = 1.0 / d
            c = 1.0 + num / c
            c = 1e-30 if abs(c) < 1e-30 else c
            f *= c * d
            if abs(1.0 - c * d) < 1e-12:
                break
        return front * (f - 1.0)

    def solve(target: float, a: float, b: float) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if beta_cdf(mid, a, b) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    low = 0.0 if k == 0 else solve(alpha / 2, k, n - k + 1)
    high = 1.0 if k == n else solve(1 - alpha / 2, k + 1, n - k)
    return [round(low, 4), round(high, 4)]


def exact_two_sided_binomial(b: int, d: int) -> float:
    """Exact conditional McNemar / sign test on the discordant pairs."""
    n = b + d
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(max(b, d), n + 1)) * (0.5 ** n)
    return min(1.0, 2 * tail)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test on a 2x2 table, by summing equal-or-rarer tables."""
    row1, row2 = a + b, c + d
    col1 = a + c
    total = row1 + row2

    def prob(x: int) -> float:
        return (math.comb(row1, x) * math.comb(row2, col1 - x)
                / math.comb(total, col1))

    observed = prob(a)
    lo = max(0, col1 - row2)
    hi = min(row1, col1)
    p = sum(prob(x) for x in range(lo, hi + 1)
            if prob(x) <= observed * (1 + 1e-9))
    return min(1.0, p)


def holm(pvals: Mapping[str, float], alpha: float = 0.05) -> dict[str, dict[str, Any]]:
    """Holm step-down, stopping at the first non-rejection."""
    order = sorted(pvals.items(), key=lambda kv: kv[1])
    out: dict[str, dict[str, Any]] = {}
    m = len(order)
    still = True
    for rank, (name, p) in enumerate(order, start=1):
        thr = alpha / (m - rank + 1)
        rejected = still and p <= thr
        if not rejected:
            still = False
        out[name] = {"p_value": p, "holm_rank": rank,
                     "holm_threshold": round(thr, 6), "rejected": rejected}
    return out


def qwk(a: list[int], b: list[int], lo: int = 1, hi: int = 5) -> float:
    """Quadratic weighted kappa on an ordinal scale."""
    k = hi - lo + 1
    n = len(a)
    if n == 0:
        return 0.0
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x - lo][y - lo] += 1.0
    ra = [0.0] * k
    rb = [0.0] * k
    for i in range(k):
        for j in range(k):
            ra[i] += obs[i][j]
            rb[j] += obs[i][j]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * obs[i][j]
            den += w * ra[i] * rb[j] / n
    return 0.0 if den == 0 else round(1 - num / den, 4)


# --------------------------------------------------------------------------
# admission
# --------------------------------------------------------------------------
def admission_tables() -> tuple[dict, dict, list[str]]:
    rec = load("admission_decisions.json")
    full: dict[str, dict[str, bool]] = defaultdict(dict)
    prov: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in rec["rows"].values():
        full[row["arm"]][row["chunk_id"]] = bool(row["admitted"])
        prov[row["arm"]][row["chunk_id"]] = bool(row["provenance_admitted"])
    chunks = sorted(set().union(*(set(v) for v in full.values())))
    return dict(full), dict(prov), chunks


def paired(table: Mapping[str, Mapping[str, bool]], left: str, right: str,
           chunks: list[str]) -> dict[str, Any]:
    b = d = 0
    for c in chunks:
        x, y = table[left].get(c), table[right].get(c)
        if x is None or y is None or x == y:
            continue
        if x and not y:
            b += 1
        else:
            d += 1
    return {"left_only_b": b, "right_only_c": d,
            "p_two_sided_exact": round(exact_two_sided_binomial(b, d), 6)}


def report_admission() -> dict[str, Any]:
    full, prov, chunks = admission_tables()
    n = len(chunks)
    out: dict[str, Any] = {"n_chunks": n, "n_arms": len(full),
                           "admission": {}, "provenance_group": {}}
    for arm in ARMS:
        k = sum(full[arm].get(c, False) for c in chunks)
        out["admission"][arm] = {"admitted": k, "n": n, "rate": round(k / n, 4),
                                 "ci95": clopper_pearson(k, n)}
        kp = sum(prov[arm].get(c, False) for c in chunks)
        out["provenance_group"][arm] = {"admitted": kp, "n": n,
                                       "rate": round(kp / n, 4),
                                       "ci95": clopper_pearson(kp, n)}
    rates = sorted(out["provenance_group"][a]["rate"] for a in ARMS)
    out["provenance_group_spread"] = {"min": rates[0], "max": rates[-1],
                                      "n_arms": len(rates)}
    family = {f"{CONTRACT}_vs_{a}": paired(full, CONTRACT, a, chunks)
              for a in ARMS if a != CONTRACT}
    out["confirmatory_family"] = family
    out["holm"] = holm({k: v["p_two_sided_exact"] for k, v in family.items()})
    out["provenance_group_contrasts"] = {
        f"{CONTRACT}_vs_direct": paired(prov, CONTRACT, "direct", chunks),
        "ecm_full_vs_direct": paired(prov, "ecm_full", "direct", chunks),
    }
    return out


def report_conditions() -> dict[str, Any]:
    """Which condition rejects, among items that clear the provenance group."""
    rec = load("admission_decisions.json")
    out: dict[str, Any] = {}
    for arm in ARMS:
        rows = [r for r in rec["rows"].values()
                if r["arm"] == arm and r["provenance_admitted"]]
        counts: dict[str, int] = defaultdict(int)
        for r in rows:
            for cond in r.get("failed_conditions") or []:
                counts[cond] += 1
        q = counts.get("g6_answer_not_in_quote", 0)
        out[arm] = {"provenance_admitted": len(rows),
                    "rejected_by_condition": dict(sorted(counts.items())),
                    "quotation_sufficient_Q": q,
                    "quotation_sufficient_rate": round(q / len(rows), 4) if rows else None}
    return out


def report_strata() -> dict[str, Any]:
    strata = load("frame_strata.json")["rows"]
    full, _, chunks = admission_tables()
    out: dict[str, Any] = {}
    for field in ("figure_role", "question_type"):
        block: dict[str, Any] = {}
        for value in sorted({v[field] for v in strata.values()}):
            subset = [c for c in chunks if strata.get(c, {}).get(field) == value]
            block[value] = {"n": len(subset),
                           "admitted_per_arm": {
                               a: sum(full[a].get(c, False) for c in subset)
                               for a in ARMS}}
        out[field] = block
    chars = sorted(v["conditioning_chars"] for v in strata.values())
    # statistics.median, not chars[n//2] and not floor division: for even n the
    # median is the MEAN of the two middle values. On this frame (n=60) they are
    # 1466 and 1571, so the index form yields 1571 and floor division 1518.
    out["conditioning_chars"] = {
        "min": chars[0], "max": chars[-1],
        "median": statistics.median(chars)}
    return out


# --------------------------------------------------------------------------
# the ablation
# --------------------------------------------------------------------------
def excluded_ids() -> set[str]:
    doc = load("protocol.json")["documents"]["ablation_preregistration"]["document"]
    block = doc.get("declared_exclusion_before_execution") or {}
    return set(block.get("item_ids") or [])


def a2_status() -> dict[str, bool]:
    rec = load("admission_decisions.json")
    return {rid: bool(r["admitted"]) for rid, r in rec["rows"].items()}


def report_ablation(which: str, threshold: str = PRIMARY) -> dict[str, Any]:
    rec = load(f"ablation_{which}.json")
    dropped = excluded_ids()
    status = a2_status()

    scored: dict[str, dict[str, bool]] = {}
    for item_id, row in rec["rows"].items():
        if item_id in dropped:
            continue
        cells = {}
        for branch in BRANCHES:
            cell = row.get(branch) or {}
            if cell.get("status") != "COMPLETE":
                cells = {}
                break
            grid = cell.get("correct_by_threshold") or {}
            if threshold not in grid:
                cells = {}
                break
            cells[branch] = bool(grid[threshold])
        if len(cells) == len(BRANCHES):
            scored[item_id] = cells

    pass_need = pass_ans = fail_need = fail_ans = 0
    to = ti = b = c = 0
    for item_id, cells in scored.items():
        v_star = not cells["text_only"]
        if status.get(item_id):
            if v_star:
                pass_need += 1
            else:
                pass_ans += 1
        else:
            if v_star:
                fail_need += 1
            else:
                fail_ans += 1
        to += cells["text_only"]
        ti += cells["text_image"]
        if cells["text_image"] and not cells["text_only"]:
            b += 1
        elif cells["text_only"] and not cells["text_image"]:
            c += 1

    n = len(scored)
    n_pass, n_fail = pass_need + pass_ans, fail_need + fail_ans
    v_star_total = pass_need + fail_need
    return {
        "answerer": rec["answerer"],
        "run": rec["run"],
        "threshold": threshold,
        "n_scored_both_branches": n,
        "construct_validity": {
            "contingency_table": {
                "a2_pass_needs_figure": pass_need,
                "a2_pass_answerable": pass_ans,
                "a2_fail_needs_figure": fail_need,
                "a2_fail_answerable": fail_ans},
            "n_a2_pass": n_pass, "n_a2_fail": n_fail,
            "v_star_a2_pass": round(pass_need / n_pass, 4) if n_pass else None,
            "v_star_a2_fail": round(fail_need / n_fail, 4) if n_fail else None,
            "fisher_exact_two_sided_p": round(
                fisher_exact_two_sided(pass_need, pass_ans, fail_need, fail_ans), 6)},
        "branch_contrast": {
            "n": n,
            "text_only_correct": to, "text_image_correct": ti,
            "text_only_rate": round(to / n, 4) if n else None,
            "text_image_rate": round(ti / n, 4) if n else None,
            "image_helped_b": b, "image_hurt_c": c,
            "mcnemar_exact_two_sided_p": round(exact_two_sided_binomial(b, c), 6),
            "v_star_count": v_star_total,
            "v_star_rate": round(v_star_total / n, 4) if n else None,
            "v_star_ci95": clopper_pearson(v_star_total, n)},
    }


def report_mcq(which: str) -> dict[str, Any]:
    rec = load(f"ablation_{which}.json")
    dropped = excluded_ids()
    to = ti = n = 0
    for item_id, row in rec["rows"].items():
        if item_id in dropped or row.get("question_type") != "multiple_choice":
            continue
        cells = [(row.get(br) or {}) for br in BRANCHES]
        if any(c.get("status") != "COMPLETE" for c in cells):
            continue
        n += 1
        to += bool(cells[0]["correct_at_primary_threshold"])
        ti += bool(cells[1]["correct_at_primary_threshold"])
    return {"n": n, "text_only_correct": to, "text_image_correct": ti}


def threshold_curve(which: str) -> dict[str, dict[str, Any]]:
    """One point per threshold THIS run tabulated, and no others."""
    rec = load(f"ablation_{which}.json")
    out = {}
    for thr in rec["thresholds_reported"]:
        cv = report_ablation(which, threshold=thr)["construct_validity"]
        out[thr] = {"fisher_p": cv["fisher_exact_two_sided_p"],
                    "v_star_a2_pass": cv["v_star_a2_pass"],
                    "v_star_a2_fail": cv["v_star_a2_fail"],
                    "significant_at_0.05": cv["fisher_exact_two_sided_p"] <= 0.05}
    return out


def report_threshold_curve_shared() -> dict[str, Any]:
    """Both answerers counted on the thresholds BOTH runs tabulate.

    The pre-registered run tabulated seven F1 thresholds and the replication
    nine. Counting each on its own grid puts two different denominators in one
    sentence, and it flatters the replication, because both extra points are
    significant. The comparison is therefore made on the shared grid and the
    extra points are listed separately.
    """
    gen = threshold_curve("generator_answerer")
    ind = threshold_curve("independent_answerer")
    shared = sorted(set(gen) & set(ind))

    def count(curve: Mapping[str, Mapping[str, Any]], keys: list[str]) -> dict[str, int]:
        return {
            "n_significant": sum(curve[k]["significant_at_0.05"] for k in keys),
            "n_direction_holds": sum(
                curve[k]["v_star_a2_pass"] > curve[k]["v_star_a2_fail"] for k in keys)}

    return {
        "shared_thresholds": shared,
        "n_shared": len(shared),
        "generator_answerer": count(gen, shared),
        "independent_answerer": count(ind, shared),
        "thresholds_only_in_replication": {
            k: {"fisher_p": ind[k]["fisher_p"],
                "significant_at_0.05": ind[k]["significant_at_0.05"]}
            for k in sorted(set(ind) - set(gen))},
        "generator_grid": sorted(gen),
        "independent_grid": sorted(ind),
    }


def report_containment_rule(which: str) -> dict[str, Any]:
    """The same endpoint under the withdrawn asymmetric rule, for comparability."""
    rec = load(f"ablation_{which}.json")
    dropped = excluded_ids()
    status = a2_status()
    pn = pa = fn = fa = 0
    for item_id, row in rec["rows"].items():
        if item_id in dropped:
            continue
        cells = [(row.get(br) or {}) for br in BRANCHES]
        if any(c.get("status") != "COMPLETE" for c in cells):
            continue
        if "correct_under_containment_rule" not in cells[0]:
            continue
        v_star = not bool(cells[0]["correct_under_containment_rule"])
        if status.get(item_id):
            pn, pa = (pn + 1, pa) if v_star else (pn, pa + 1)
        else:
            fn, fa = (fn + 1, fa) if v_star else (fn, fa + 1)
    return {"contingency_table": {"a2_pass_needs_figure": pn, "a2_pass_answerable": pa,
                                  "a2_fail_needs_figure": fn, "a2_fail_answerable": fa},
            "v_star_a2_pass": round(pn / (pn + pa), 4) if pn + pa else None,
            "v_star_a2_fail": round(fn / (fn + fa), 4) if fn + fa else None,
            "fisher_exact_two_sided_p": round(fisher_exact_two_sided(pn, pa, fn, fa), 6)}


# --------------------------------------------------------------------------
# judged endpoints
# --------------------------------------------------------------------------
def judged_cells() -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    rec = load("judged_scores.json")
    out: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for item_id, row in rec["rows"].items():
        parts = item_id.split("::")
        chunk, arm = "::".join(parts[:-1]), parts[-1]
        if all(r in row for r in RATERS):
            out[(chunk, arm)] = row
    return out


def report_judged() -> dict[str, Any]:
    cells = judged_cells()
    _, _, chunks = admission_tables()
    rec = load("admission_decisions.json")
    g6: dict[tuple[str, str], bool] = {}
    for row in rec["rows"].values():
        g6[(row["chunk_id"], row["arm"])] = (
            "g6_answer_not_in_quote" not in (row.get("failed_conditions") or []))

    def min_score(chunk: str, arm: str, crit: str):
        row = cells.get((chunk, arm))
        if not row:
            return None
        vals = [row[r].get(crit) for r in RATERS]
        return min(vals) if all(isinstance(v, int) for v in vals) else None

    def violation(chunk: str, arm: str):
        row = cells.get((chunk, arm))
        if not row:
            return None
        return any(row[r].get("critical_provenance_violation") is True for r in RATERS)

    def sign_block(score, keep=None) -> dict[str, Any]:
        block = {}
        for other in [a for a in ARMS if a != CONTRACT]:
            hi = lo = tie = 0
            for c in chunks:
                if keep is not None and not keep(c, other):
                    continue
                x, y = score(c, CONTRACT), score(c, other)
                if x is None or y is None:
                    continue
                if x > y:
                    hi += 1
                elif y > x:
                    lo += 1
                else:
                    tie += 1
            block[f"{CONTRACT}_vs_{other}"] = {
                "n_co_judged": hi + lo + tie, "ecm_v2_higher": hi,
                "control_higher": lo, "tied": tie,
                "p_two_sided_exact_sign": round(exact_two_sided_binomial(hi, lo), 6)}
        return block

    out: dict[str, Any] = {"n_judged_cells": len(cells), "paired_criteria": {}}
    for crit in CRITERIA:
        out["paired_criteria"][crit] = sign_block(
            lambda c, a, crit=crit: min_score(c, a, crit))

    viol = {}
    for other in [a for a in ARMS if a != CONTRACT]:
        b = d = 0
        for c in chunks:
            x, y = violation(c, CONTRACT), violation(c, other)
            if x is None or y is None or x == y:
                continue
            if x and not y:
                b += 1
            else:
                d += 1
        viol[f"{CONTRACT}_vs_{other}"] = {
            "ecm_v2_only_b": b, "control_only_c": d,
            "p_two_sided_exact_mcnemar": round(exact_two_sided_binomial(b, d), 6)}
    out["critical_provenance_violation"] = viol

    out["g6_stratified_evidence_correctness"] = {
        "both_passed_g6": sign_block(
            lambda c, a: min_score(c, a, "evidence_correctness"),
            keep=lambda c, other: g6.get((c, CONTRACT)) and g6.get((c, other))),
        "both_failed_g6": sign_block(
            lambda c, a: min_score(c, a, "evidence_correctness"),
            keep=lambda c, other: (g6.get((c, CONTRACT)) is False
                                   and g6.get((c, other)) is False)),
    }

    agreement = {}
    for crit in CRITERIA:
        a = [row[RATERS[0]][crit] for row in cells.values()
             if isinstance(row[RATERS[0]].get(crit), int)
             and isinstance(row[RATERS[1]].get(crit), int)]
        b = [row[RATERS[1]][crit] for row in cells.values()
             if isinstance(row[RATERS[0]].get(crit), int)
             and isinstance(row[RATERS[1]].get(crit), int)]
        agreement[crit] = {"n": len(a), "qwk": qwk(a, b)}
    out["rater_agreement_qwk"] = agreement
    return out


def report_rated_vs_measured() -> dict[str, Any]:
    """Rated visual necessity against the measured outcome, on the same items."""
    cells = judged_cells()
    rec = load("ablation_generator_answerer.json")
    dropped = excluded_ids()

    def rated(item_id: str):
        parts = item_id.split("::")
        row = cells.get(("::".join(parts[:-1]), parts[-1]))
        if not row:
            return None
        vals = [row[r].get("visual_necessity") for r in RATERS]
        return min(vals) >= 3 if all(isinstance(v, int) for v in vals) else None

    def outcomes(item_id: str):
        row = rec["rows"].get(item_id) or {}
        cs = [(row.get(br) or {}) for br in BRANCHES]
        if any(c.get("status") != "COMPLETE" for c in cs):
            return None
        return (bool(cs[0]["correct_at_primary_threshold"]),
                bool(cs[1]["correct_at_primary_threshold"]))

    def table(measured_of) -> dict[str, Any]:
        both = neither = rated_only = measured_only = 0
        for item_id in rec["rows"]:
            r = rated(item_id)
            o = outcomes(item_id)
            if r is None or o is None:
                continue
            m = measured_of(o)
            if r and m:
                both += 1
            elif r:
                rated_only += 1
            elif m:
                measured_only += 1
            else:
                neither += 1
        n = both + neither + rated_only + measured_only
        po = (both + neither) / n if n else 0.0
        pr = (((both + rated_only) * (both + measured_only)
               + (neither + measured_only) * (neither + rated_only)) / (n * n)) if n else 0.0
        return {"n": n, "both": both, "neither": neither,
                "rated_only": rated_only, "measured_only": measured_only,
                "raw_agreement": round(po, 4),
                "cohen_kappa": round((po - pr) / (1 - pr), 4) if pr < 1 else None}

    return {
        "note": ("this table spans every admitted item, including the two the "
                 "ablation excluded from its graded denominator, which is why n "
                 "is 227 and not 225"),
        "vs_figure_attributable": table(lambda o: (not o[0]) and o[1]),
        "vs_not_answerable_from_text": table(lambda o: not o[0]),
    }


# --------------------------------------------------------------------------
def build() -> dict[str, Any]:
    return {
        "admission": report_admission(),
        "conditions": report_conditions(),
        "strata": report_strata(),
        "ablation_generator_answerer": report_ablation("generator_answerer"),
        "ablation_independent_answerer": report_ablation("independent_answerer"),
        "mcq_generator_answerer": report_mcq("generator_answerer"),
        "threshold_curve_shared_grid": report_threshold_curve_shared(),
        "containment_rule_independent": report_containment_rule("independent_answerer"),
        "judged": report_judged(),
        "rated_vs_measured": report_rated_vs_measured(),
    }


A = "admission."
G = "ablation_generator_answerer."
I = "ablation_independent_answerer."
J = "judged.paired_criteria.evidence_correctness."
S = "threshold_curve_shared_grid."

# (label, dotted path into the recomputed tree, the value printed in the paper)
PAPER: list[tuple[str, str, Any]] = [
    # admission, the primary endpoint
    ("frame n = 60", A + "n_chunks", 60),
    ("five arms", A + "n_arms", 5),
    ("A ECM 24/60", A + "admission.ecm_v2.admitted", 24),
    ("A ECM rate 0.40", A + "admission.ecm_v2.rate", 0.4),
    ("A ECM CI [0.28,0.53]", A + "admission.ecm_v2.ci95", [0.2756, 0.5346]),
    ("A DISC 10/60", A + "admission.ecm_v2_disclosed.admitted", 10),
    ("A PROV 11/60", A + "admission.ecm_full.admitted", 11),
    ("A DIR 6/60", A + "admission.direct.admitted", 6),
    ("A STR 6/60", A + "admission.structured_no_contract.admitted", 6),

    ("Holm STR b=20", A + "confirmatory_family.ecm_v2_vs_structured_no_contract.left_only_b", 20),
    ("Holm STR d=2", A + "confirmatory_family.ecm_v2_vs_structured_no_contract.right_only_c", 2),
    ("Holm STR p=0.00012", A + "confirmatory_family.ecm_v2_vs_structured_no_contract.p_two_sided_exact", 0.000121),
    ("Holm DIR b=21", A + "confirmatory_family.ecm_v2_vs_direct.left_only_b", 21),
    ("Holm DIR p=0.00028", A + "confirmatory_family.ecm_v2_vs_direct.p_two_sided_exact", 0.000277),
    ("Holm DISC b=16", A + "confirmatory_family.ecm_v2_vs_ecm_v2_disclosed.left_only_b", 16),
    ("Holm DISC p=0.0013", A + "confirmatory_family.ecm_v2_vs_ecm_v2_disclosed.p_two_sided_exact", 0.001312),
    ("Holm PROV p=0.011", A + "confirmatory_family.ecm_v2_vs_ecm_full.p_two_sided_exact", 0.010622),
    ("all four reject", A + "holm.ecm_v2_vs_ecm_full.rejected", True),

    # provenance group is not traded away
    ("A_P ECM 50/60", A + "provenance_group.ecm_v2.admitted", 50),
    ("A_P ECM CI [0.72,0.92]", A + "provenance_group.ecm_v2.ci95", [0.7148, 0.9171]),
    ("A_P DISC 48/60", A + "provenance_group.ecm_v2_disclosed.admitted", 48),
    ("A_P DIR 44/60", A + "provenance_group.direct.admitted", 44),
    ("A_P PROV 41/60", A + "provenance_group.ecm_full.admitted", 41),
    ("A_P all five in 0.68-0.83 (min)", A + "provenance_group_spread.min", 0.6833),
    ("A_P all five in 0.68-0.83 (max)", A + "provenance_group_spread.max", 0.8333),
    ("A_P spread over 5 arms", A + "provenance_group_spread.n_arms", 5),
    ("A_P ECM vs DIR b=10", A + "provenance_group_contrasts.ecm_v2_vs_direct.left_only_b", 10),
    ("A_P ECM vs DIR p=0.18", A + "provenance_group_contrasts.ecm_v2_vs_direct.p_two_sided_exact", 0.179565),
    ("A_P PROV vs DIR p=0.66", A + "provenance_group_contrasts.ecm_full_vs_direct.p_two_sided_exact", 0.663624),

    # where admission is lost
    ("G6 rejects 37/44 direct", "conditions.direct.quotation_sufficient_Q", 37),
    ("direct prov-admitted 44", "conditions.direct.provenance_admitted", 44),
    ("G6 rejects 34/44 structured", "conditions.structured_no_contract.quotation_sufficient_Q", 34),
    ("G6 rejects 30/48 disclosure", "conditions.ecm_v2_disclosed.quotation_sufficient_Q", 30),
    ("G6 rejects 29/41 prov-only", "conditions.ecm_full.quotation_sufficient_Q", 29),
    ("G6 rejects 15/50 contract", "conditions.ecm_v2.quotation_sufficient_Q", 15),
    ("Q direct 0.84", "conditions.direct.quotation_sufficient_rate", 0.8409),
    ("Q contract 0.30", "conditions.ecm_v2.quotation_sufficient_rate", 0.3),

    # strata, descriptive
    ("36 table chunks", "strata.figure_role.table.n", 36),
    ("table: 13 contract", "strata.figure_role.table.admitted_per_arm.ecm_v2", 13),
    ("24 pictorial chunks", "strata.figure_role.pictorial.n", 24),
    ("pictorial: 11 contract", "strata.figure_role.pictorial.admitted_per_arm.ecm_v2", 11),
    ("conditioning chars min 212", "strata.conditioning_chars.min", 212),
    ("conditioning chars max 7634", "strata.conditioning_chars.max", 7634),
    ("conditioning chars median 1518.5", "strata.conditioning_chars.median", 1518.5),

    # construct validity, generator as answerer
    ("ablation n = 225", G + "n_scored_both_branches", 225),
    ("V* admitted 33/57", G + "construct_validity.contingency_table.a2_pass_needs_figure", 33),
    ("V* rejected 64/168", G + "construct_validity.contingency_table.a2_fail_needs_figure", 64),
    ("V* admitted rate 0.58", G + "construct_validity.v_star_a2_pass", 0.5789),
    ("V* rejected rate 0.38", G + "construct_validity.v_star_a2_fail", 0.381),
    ("Fisher p = 0.013", G + "construct_validity.fisher_exact_two_sided_p", 0.012908),
    ("branch text-only 128", G + "branch_contrast.text_only_correct", 128),
    ("branch text+figure 136", G + "branch_contrast.text_image_correct", 136),
    ("branch b = 16", G + "branch_contrast.image_helped_b", 16),
    ("branch d = 8", G + "branch_contrast.image_hurt_c", 8),
    ("branch p = 0.15", G + "branch_contrast.mcnemar_exact_two_sided_p", 0.15159),
    ("MCQ 28 of 30 from text", "mcq_generator_answerer.text_only_correct", 28),
    ("MCQ n = 30", "mcq_generator_answerer.n", 30),

    # the replication with an independent answerer
    ("replication n = 225", I + "n_scored_both_branches", 225),
    ("replication V* admitted 34/57", I + "construct_validity.contingency_table.a2_pass_needs_figure", 34),
    ("replication V* rejected 71/168", I + "construct_validity.contingency_table.a2_fail_needs_figure", 71),
    ("replication V* admitted 0.60", I + "construct_validity.v_star_a2_pass", 0.5965),
    ("replication V* rejected 0.42", I + "construct_validity.v_star_a2_fail", 0.4226),
    ("replication Fisher p = 0.031", I + "construct_validity.fisher_exact_two_sided_p", 0.031059),
    ("replication text-only 120", I + "branch_contrast.text_only_correct", 120),
    ("replication text+figure 124", I + "branch_contrast.text_image_correct", 124),
    ("replication b = 10", I + "branch_contrast.image_helped_b", 10),
    ("replication d = 6", I + "branch_contrast.image_hurt_c", 6),
    ("replication p = 0.45", I + "branch_contrast.mcnemar_exact_two_sided_p", 0.454498),
    ("replication containment p = 0.0026", "containment_rule_independent.fisher_exact_two_sided_p", 0.002609),

    # the threshold curve, on the grid both runs tabulate
    ("shared grid has 7 thresholds", S + "n_shared", 7),
    ("generator: 6 of 7 significant", S + "generator_answerer.n_significant", 6),
    ("generator: direction at all 7", S + "generator_answerer.n_direction_holds", 7),
    ("replication: 5 of 7 significant", S + "independent_answerer.n_significant", 5),
    ("replication: direction at all 7", S + "independent_answerer.n_direction_holds", 7),

    # what the contract costs
    ("cost PROV n = 34", J + "ecm_v2_vs_ecm_full.n_co_judged", 34),
    ("cost PROV 4/22", J + "ecm_v2_vs_ecm_full.control_higher", 22),
    ("cost PROV p = 0.0005", J + "ecm_v2_vs_ecm_full.p_two_sided_exact_sign", 0.000534),
    ("cost DISC n = 43", J + "ecm_v2_vs_ecm_v2_disclosed.n_co_judged", 43),
    ("cost DISC p = 0.0003", J + "ecm_v2_vs_ecm_v2_disclosed.p_two_sided_exact_sign", 0.000325),
    ("cost DIR n = 40", J + "ecm_v2_vs_direct.n_co_judged", 40),
    ("cost DIR p = 0.0002", J + "ecm_v2_vs_direct.p_two_sided_exact_sign", 0.000192),
    ("cost STR n = 38", J + "ecm_v2_vs_structured_no_contract.n_co_judged", 38),
    ("cost STR p = 0.0001", J + "ecm_v2_vs_structured_no_contract.p_two_sided_exact_sign", 0.000104),
    ("visual necessity DISC 7/8", "judged.paired_criteria.visual_necessity.ecm_v2_vs_ecm_v2_disclosed.ecm_v2_higher", 7),
    ("visual necessity DISC p = 1.00", "judged.paired_criteria.visual_necessity.ecm_v2_vs_ecm_v2_disclosed.p_two_sided_exact_sign", 1.0),
    ("provenance violation DIR p = 0.039", "judged.critical_provenance_violation.ecm_v2_vs_direct.p_two_sided_exact_mcnemar", 0.039062),
    ("answerability PROV p = 0.0026", "judged.paired_criteria.answerability.ecm_v2_vs_ecm_full.p_two_sided_exact_sign", 0.002599),
    ("language DIR p = 0.023", "judged.paired_criteria.vietnamese_language.ecm_v2_vs_direct.p_two_sided_exact_sign", 0.022656),
    ("G6-pass PROV 6 to 0", "judged.g6_stratified_evidence_correctness.both_passed_g6.ecm_v2_vs_ecm_full.control_higher", 6),
    ("G6-pass PROV p = 0.031", "judged.g6_stratified_evidence_correctness.both_passed_g6.ecm_v2_vs_ecm_full.p_two_sided_exact_sign", 0.03125),
    ("G6-fail DISC 8 to 1", "judged.g6_stratified_evidence_correctness.both_failed_g6.ecm_v2_vs_ecm_v2_disclosed.control_higher", 8),
    ("G6-fail DISC p = 0.039", "judged.g6_stratified_evidence_correctness.both_failed_g6.ecm_v2_vs_ecm_v2_disclosed.p_two_sided_exact_sign", 0.039062),

    # rated and measured necessity diverge
    ("rated vs measured n = 227", "rated_vs_measured.vs_figure_attributable.n", 227),
    ("both positive 4", "rated_vs_measured.vs_figure_attributable.both", 4),
    ("neither 192", "rated_vs_measured.vs_figure_attributable.neither", 192),
    ("rated only 19", "rated_vs_measured.vs_figure_attributable.rated_only", 19),
    ("measured only 12", "rated_vs_measured.vs_figure_attributable.measured_only", 12),
    ("raw agreement 0.86", "rated_vs_measured.vs_figure_attributable.raw_agreement", 0.8634),
    ("kappa 0.13", "rated_vs_measured.vs_figure_attributable.cohen_kappa", 0.1331),
    ("V* kappa -0.02", "rated_vs_measured.vs_not_answerable_from_text.cohen_kappa", -0.0202),
    ("V* raw 0.54", "rated_vs_measured.vs_not_answerable_from_text.raw_agreement", 0.5419),

    # rater agreement
    ("kappa_w visual necessity 0.59", "judged.rater_agreement_qwk.visual_necessity.qwk", 0.5899),
    ("kappa_w evidence correctness 0.65", "judged.rater_agreement_qwk.evidence_correctness.qwk", 0.653),
    ("kappa_w pedagogical value 0.20", "judged.rater_agreement_qwk.pedagogical_value.qwk", 0.1969),
]


def dig(tree: Mapping[str, Any], path: str) -> Any:
    node: Any = tree
    parts = path.split(".")
    i = 0
    while i < len(parts):
        if not isinstance(node, Mapping):
            raise KeyError(f"not a mapping at {'.'.join(parts[:i])}")
        for span in range(len(parts) - i, 0, -1):
            key = ".".join(parts[i:i + span])
            if key in node:
                node = node[key]
                i += span
                break
        else:
            raise KeyError(f"missing {parts[i]} under {'.'.join(parts[:i])}")
    return node


def same(got: Any, want: Any) -> bool:
    if isinstance(want, bool) or isinstance(got, bool):
        return bool(got) is bool(want)
    if isinstance(want, list):
        return (isinstance(got, list) and len(got) == len(want)
                and all(same(g, w) for g, w in zip(got, want)))
    if isinstance(want, float):
        return isinstance(got, (int, float)) and abs(float(got) - want) <= 1e-4
    return got == want


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="assert the recomputed values against the paper")
    ap.add_argument("--json", action="store_true",
                    help="print the full recomputed tree as JSON")
    args = ap.parse_args()

    tree = build()
    if args.json:
        print(json.dumps(tree, indent=1, sort_keys=True, ensure_ascii=False))
        if not args.check:
            return 0

    if not args.json:
        adm = tree["admission"]
        print("ECM-TQAG: quantities recomputed from records/ alone\n")
        print(f"  frame: n = {adm['n_chunks']} chunks, {adm['n_arms']} arms")
        for arm in ARMS:
            a, p = adm["admission"][arm], adm["provenance_group"][arm]
            print(f"    {arm:24s} A = {a['admitted']:2d}/{a['n']} = {a['rate']:.4f}"
                  f"   A_P = {p['admitted']:2d}/{p['n']} = {p['rate']:.4f}")
        print("\n  confirmatory family, Holm at family-wise alpha = 0.05")
        for name, blk in sorted(adm["holm"].items(), key=lambda kv: kv[1]["holm_rank"]):
            print(f"    {name:36s} p = {blk['p_value']:.6f}"
                  f"  thr = {blk['holm_threshold']:.6f}  rejected = {blk['rejected']}")
        for which in ("generator_answerer", "independent_answerer"):
            ab = tree[f"ablation_{which}"]
            cv, bc = ab["construct_validity"], ab["branch_contrast"]
            print(f"\n  ablation, answerer = {ab['answerer']}"
                  f"  (n = {ab['n_scored_both_branches']})")
            print(f"    V* | A2-pass = {cv['v_star_a2_pass']}"
                  f"   V* | A2-fail = {cv['v_star_a2_fail']}"
                  f"   Fisher p = {cv['fisher_exact_two_sided_p']}")
            print(f"    text-only {bc['text_only_correct']}"
                  f"  text+figure {bc['text_image_correct']}"
                  f"   b = {bc['image_helped_b']}  d = {bc['image_hurt_c']}"
                  f"   McNemar p = {bc['mcnemar_exact_two_sided_p']}")
        sg = tree["threshold_curve_shared_grid"]
        print(f"\n  threshold curve on the {sg['n_shared']} thresholds both runs tabulate")
        print(f"    generator   significant {sg['generator_answerer']['n_significant']}"
              f"   direction {sg['generator_answerer']['n_direction_holds']}")
        print(f"    replication significant {sg['independent_answerer']['n_significant']}"
              f"   direction {sg['independent_answerer']['n_direction_holds']}")
        if sg["thresholds_only_in_replication"]:
            extra = ", ".join(sg["thresholds_only_in_replication"])
            print(f"    tabulated only by the replication: {extra}")
        print("\n  judged evidence correctness, paired sign test")
        for name, blk in sorted(tree["judged"]["paired_criteria"]
                                ["evidence_correctness"].items()):
            print(f"    {name:36s} n = {blk['n_co_judged']:2d}"
                  f"  ECM/other = {blk['ecm_v2_higher']}/{blk['control_higher']}"
                  f"  p = {blk['p_two_sided_exact_sign']}")
        rvm = tree["rated_vs_measured"]["vs_figure_attributable"]
        print(f"\n  rated vs measured necessity: n = {rvm['n']},"
              f" kappa = {rvm['cohen_kappa']}, raw = {rvm['raw_agreement']}")

    if not args.check:
        print("\n(run with --check to assert these against the manuscript)")
        return 0

    print(f"\nchecking {len(PAPER)} quantities against the manuscript\n")
    bad = 0
    for label, path, want in PAPER:
        try:
            got = dig(tree, path)
        except KeyError as exc:
            print(f"  MISSING   {label}\n            {exc}")
            bad += 1
            continue
        if not same(got, want):
            print(f"  MISMATCH  {label}\n            path {path}"
                  f"\n            paper {want}  recomputed {got}")
            bad += 1
    print(f"checked: {len(PAPER)}   mismatches: {bad}\n")
    print("VERDICT: every reported quantity recomputes from the released records"
          if bad == 0 else "VERDICT: FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
