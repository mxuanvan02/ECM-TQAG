#!/usr/bin/env python3
"""Recompute every quantity reported in the ECM-TQAG manuscript from the released records.

This script reads ONLY the files published under ``records/`` and depends on
nothing outside the Python standard library.  It issues no network calls and
reads no page images, so it can be run by a reviewer with this directory alone.

Usage:
    python3 verify_reported_quantities.py            # print recomputed values
    python3 verify_reported_quantities.py --check    # also assert them against
                                                    # the values printed in the paper

Exit status is 0 when every check passes and 1 when any check fails, so the
script doubles as a regression test on the released records.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECORDS = HERE / "records"

ARMS = ("ecm_full", "gate_disclosed", "direct", "structured_no_contract")
ARM_LABEL = {
    "ecm_full": "ECM",
    "gate_disclosed": "GATE",
    "direct": "DIR",
    "structured_no_contract": "STR",
}
CONFIRMATORY = ("direct", "structured_no_contract")  # Holm family with gate_disclosed
FAMILY = ("gate_disclosed", "direct", "structured_no_contract")


# --------------------------------------------------------------------------- stats


def exact_mcnemar(b: int, d: int) -> float:
    """Two-sided exact conditional McNemar / sign test on the discordant pairs."""
    n = b + d
    if n == 0:
        return 1.0
    k = max(b, d)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / (2**n)
    return min(1.0, 2 * tail)


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Beta quantile by bisection on the regularised incomplete beta function."""
    if a <= 0:
        return 0.0
    if b <= 0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a,b) via its continued fraction."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log1p(-x) * b - lbeta) / a
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _betainc(b, a, 1.0 - x)
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
    return front * (f - 1.0)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    lo = 0.0 if k == 0 else _beta_ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else _beta_ppf(1 - alpha / 2, k + 1, n - k)
    return round(lo, 4), round(hi, 4)


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    out: dict[str, dict] = {}
    stopped = False
    for rank, (name, p) in enumerate(ordered):
        threshold = alpha / (m - rank)
        rejected = (p <= threshold) and not stopped
        if not rejected:
            stopped = True
        out[name] = {"p": p, "threshold": round(threshold, 5), "rejected": rejected}
    return out


def cohen_kappa(pairs: list[tuple[int, int]]) -> float:
    """Unweighted kappa on a binary classification."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    agree = sum(1 for a, b in pairs if a == b) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    return (agree - chance) / (1 - chance) if chance < 1 else float("nan")


def weighted_kappa(pairs: list[tuple[int, int]], k: int = 5) -> float:
    """Quadratic weighted kappa on a 1..k ordinal scale."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    obs = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        obs[a - 1][b - 1] += 1
    ra = [sum(row) for row in obs]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) / (k - 1)) ** 2
            num += w * obs[i][j]
            den += w * ra[i] * rb[j] / n
    return 1.0 - num / den if den else float("nan")


# --------------------------------------------------------------------------- loading


def load_tasks(subdir: str) -> list[dict]:
    root = RECORDS / subdir / "task_records"
    if not root.is_dir():
        sys.exit("missing records directory: %s" % root)
    out = []
    for path in sorted(root.glob("*.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def parse_census(tasks: list[dict]):
    """Return (admission, judge_scores, chunk_ids)."""
    admission: dict[tuple[str, str], int] = {}
    judges: dict[tuple[str, str, str], dict] = {}
    chunks: set[str] = set()
    for rec in tasks:
        tid = rec.get("task_id", "")
        parts = tid.split("::")
        if tid.startswith("generation::"):
            # generation::r4c::framec::<doc>::<page>::<arm>
            chunk = "::".join(parts[2:5])
            arm = parts[5]
            chunks.add(chunk)
            admission[(chunk, arm)] = 1 if rec.get("gates_passed") is True else 0
        elif tid.startswith("judge::"):
            chunk = "::".join(parts[2:5])
            arm, judge = parts[5], parts[6]
            if rec.get("status") == "COMPLETE" and rec.get("gates_passed") is True:
                judges[(chunk, arm, judge)] = rec["object"]
    return admission, judges, sorted(chunks)


def _norm_fold(text: str) -> str:
    """N of eq. (6) followed by case folding, as fixed in the analysis plan."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def grade_ablation(rec: dict, gold: dict) -> int | None:
    """Apply the pre-registered grading rule to one ablation response.

    Multiple choice: the returned option index must equal the recorded
    ``correct_option``.  Short answer: the normalised answer must contain the
    recorded answer or be contained by it.  Returns None when no gold item
    exists, so the caller can drop the pair rather than score it as wrong.
    """
    if gold is None:
        return None
    returned = rec.get("returned")
    if not isinstance(returned, dict):
        return 0
    if rec.get("question_type") == "multiple_choice":
        idx = returned.get("option_index")
        if not isinstance(idx, int):
            return 0
        return 1 if idx == gold.get("correct_option") else 0
    got = returned.get("answer")
    want = gold.get("answer")
    if not isinstance(got, str) or not isinstance(want, str) or not got or not want:
        return 0
    g, w = _norm_fold(got), _norm_fold(want)
    return 1 if (w in g or g in w) else 0


def parse_ablation(tasks: list[dict], gold: dict[str, dict]):
    """Return {answerer: {item_id: {branch: correct}}} plus item metadata."""
    out: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    meta: dict[str, dict] = {}
    for rec in tasks:
        if rec.get("status") != "COMPLETE":
            continue
        ans = rec["answerer"]
        item = rec["item_id"]
        branch = rec["branch"]
        graded = grade_ablation(rec, gold.get(item))
        if graded is None:
            continue
        out[ans][item][branch] = graded
        meta.setdefault(item, {"arm": rec.get("arm"), "question_type": rec.get("question_type")})
    return out, meta


def admitted_items(tasks: list[dict]) -> dict[str, dict]:
    """The admitted generation objects, keyed the way the ablation keys items."""
    gold: dict[str, dict] = {}
    for rec in tasks:
        tid = rec.get("task_id", "")
        if not tid.startswith("generation::") or rec.get("gates_passed") is not True:
            continue
        parts = tid.split("::")
        gold["::".join(parts[2:6])] = rec["object"]
    return gold


# --------------------------------------------------------------------------- report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="assert against the published values")
    args = ap.parse_args()

    failures: list[str] = []

    def check(name: str, got, want, tol=0.0):
        if not args.check:
            return
        ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
        if not ok:
            failures.append("%s: recomputed %r, paper says %r" % (name, got, want))

    census = load_tasks("census")
    admission, judges, chunks = parse_census(census)
    n = len(chunks)

    print("=" * 72)
    print("CENSUS  n = %d chunks, %d chunk-arm attempts" % (n, len(admission)))
    print("=" * 72)
    check("frame size", n, 24)
    check("attempts", len(admission), 96)

    counts = {}
    for arm in ARMS:
        k = sum(admission[(c, arm)] for c in chunks)
        counts[arm] = k
        lo, hi = clopper_pearson(k, n)
        print("  %-5s %2d/%d = %.2f   CP95 [%.2f, %.2f]" % (ARM_LABEL[arm], k, n, k / n, lo, hi))
    check("ECM admitted", counts["ecm_full"], 22)
    check("GATE admitted", counts["gate_disclosed"], 17)
    check("DIR admitted", counts["direct"], 15)
    check("STR admitted", counts["structured_no_contract"], 14)
    check("admitted total", sum(counts.values()), 68)

    print("\nPAIRED CONTRASTS (exact McNemar, ECM vs control)")
    pvals = {}
    for arm in FAMILY:
        b = sum(1 for c in chunks if admission[(c, "ecm_full")] == 1 and admission[(c, arm)] == 0)
        d = sum(1 for c in chunks if admission[(c, "ecm_full")] == 0 and admission[(c, arm)] == 1)
        p = exact_mcnemar(b, d)
        pvals[arm] = p
        print("  ECM vs %-5s  b=%d d=%d  p=%.4f" % (ARM_LABEL[arm], b, d, p))
        if arm == "direct":
            check("ECM-DIR b", b, 7)
            check("ECM-DIR d", d, 0)
            check("ECM-DIR p", round(p, 3), 0.016)
        if arm == "structured_no_contract":
            check("ECM-STR b", b, 9)
            check("ECM-STR d", d, 1)
            check("ECM-STR p", round(p, 3), 0.021)
        if arm == "gate_disclosed":
            check("ECM-GATE b", b, 6)
            check("ECM-GATE d", d, 1)
            check("ECM-GATE p", round(p, 3), 0.125)

    print("\nHOLM step-down over the three-contrast family (alpha = 0.05)")
    for arm, info in holm(pvals).items():
        print("  ECM vs %-5s  p=%.4f  threshold=%.5f  %s"
              % (ARM_LABEL[arm], info["p"], info["threshold"],
                 "REJECT" if info["rejected"] else "not rejected"))
    hol = holm(pvals)
    check("Holm rejects DIR", hol["direct"]["rejected"], True)
    check("Holm rejects STR", hol["structured_no_contract"]["rejected"], True)
    check("Holm does not reject GATE", hol["gate_disclosed"]["rejected"], False)

    print("\nAUXILIARY CONTRAST (outside the family, descriptive)")
    b = sum(1 for c in chunks
            if admission[(c, "gate_disclosed")] == 1 and admission[(c, "direct")] == 0)
    d = sum(1 for c in chunks
            if admission[(c, "gate_disclosed")] == 0 and admission[(c, "direct")] == 1)
    print("  GATE vs DIR   b=%d d=%d  p=%.4f" % (b, d, exact_mcnemar(b, d)))
    check("GATE-DIR b", b, 5)
    check("GATE-DIR d", d, 3)
    check("GATE-DIR p", round(exact_mcnemar(b, d), 2), 0.73)

    # ---------------------------------------------------------------- taxonomy
    attribution = RECORDS / "census" / "FAILURE_ATTRIBUTION.json"
    if attribution.exists():
        att = json.loads(attribution.read_text(encoding="utf-8"))
        print("\nFAILURE TAXONOMY (from the sealed attribution audit)")
        by = att["by_category_and_arm"]
        for cat in sorted(by):
            row = " ".join("%s=%d" % (ARM_LABEL[a], by[cat].get(a, 0)) for a in ARMS)
            print("  %-38s %s" % (cat, row))
        img = by["quotation_of_image_rendered_text"]
        check("image-quoting ECM", img["ecm_full"], 0)
        check("image-quoting GATE", img["gate_disclosed"], 1)
        check("image-quoting DIR", img["direct"], 3)
        check("image-quoting STR", img["structured_no_contract"], 3)
        check("image-quoting total", att["totals"]["quotation_of_image_rendered_text"], 7)
        check("case-only total", att["totals"]["case_only_false_reject"], 5)
        check("unresolved total", att["totals"]["unresolved"], 6)

    # ---------------------------------------------------------------- judged
    print("\nJUDGED ENDPOINTS")
    print("  rater records passing their own checks: %d" % len(judges))
    check("judge records", len(judges), 136)

    raters = sorted({j for (_, _, j) in judges})
    v_counts = {}
    for arm in ARMS:
        met = 0
        for c in chunks:
            if admission[(c, arm)] != 1:
                continue
            recs = [judges[(c, arm, r)] for r in raters if (c, arm, r) in judges]
            if len(recs) == len(raters) and all(
                o["evidence_correctness"] >= 3 and o["visual_necessity"] >= 3
                and o["answerability"] >= 3 for o in recs
            ):
                met += 1
        v_counts[arm] = met
    print("  endpoint V met: " + ", ".join("%s %d/%d" % (ARM_LABEL[a], v_counts[a], n) for a in ARMS))
    check("V ecm", v_counts["ecm_full"], 3)
    check("V gate", v_counts["gate_disclosed"], 2)
    check("V dir", v_counts["direct"], 2)
    check("V str", v_counts["structured_no_contract"], 1)

    below = sum(1 for o in judges.values() if o["visual_necessity"] < 3)
    dist = Counter(o["visual_necessity"] for o in judges.values())
    print("  visual necessity below 3: %d of %d   distribution %s"
          % (below, len(judges), dict(sorted(dist.items()))))
    check("necessity below 3", below, 93)

    print("  quadratic weighted kappa per criterion (items both raters scored)")
    crit = ("visual_necessity", "evidence_correctness", "answerability",
            "vietnamese_language", "pedagogical_value")
    keys = {(c, a) for (c, a, _) in judges}
    for name in crit:
        pairs = [(judges[(c, a, raters[0])][name], judges[(c, a, raters[1])][name])
                 for (c, a) in sorted(keys)
                 if (c, a, raters[0]) in judges and (c, a, raters[1]) in judges]
        kw = weighted_kappa(pairs)
        exact = sum(1 for x, y in pairs if x == y) / len(pairs)
        within = sum(1 for x, y in pairs if abs(x - y) <= 1) / len(pairs)
        print("    %-22s kw=%.2f  exact=%.0f%%  within1=%.0f%%  n=%d"
              % (name, kw, 100 * exact, 100 * within, len(pairs)))
        if name == "visual_necessity":
            check("kw visual necessity", round(kw, 2), 0.82)
        if name == "pedagogical_value":
            check("kw pedagogical value", round(kw, 2), 0.21)

    # ---------------------------------------------------------------- ablation
    abl_tasks = load_tasks("ablation")
    branches, meta = parse_ablation(abl_tasks, admitted_items(census))
    print("\nMEASURED VISUAL NECESSITY (text-only ablation)")
    necessity_flags: dict[str, dict[str, int]] = {}
    for answerer in sorted(branches, key=lambda a: (a != "qwen/qwen3-vl-8b-instruct", a)):
        items = {i: b for i, b in branches[answerer].items() if len(b) == 2}
        txt = sum(b["text_only"] for b in items.values())
        img = sum(b["text_image"] for b in items.values())
        nec = {i: int(b["text_image"] == 1 and b["text_only"] == 0) for i, b in items.items()}
        necessity_flags[answerer] = nec
        b_only = sum(nec.values())
        d_only = sum(1 for b in items.values() if b["text_image"] == 0 and b["text_only"] == 1)
        p = exact_mcnemar(b_only, d_only)
        lo, hi = clopper_pearson(b_only, len(items))
        print("  %-30s n=%d  R_txt=%d  R_+img=%d  Gamma+1=%d  p=%.4f  rate=%.2f [%.2f, %.2f]"
              % (answerer, len(items), txt, img, b_only, p, b_only / len(items), lo, hi))
        mcq = {i: b for i, b in items.items() if meta[i]["question_type"] == "multiple_choice"}
        print("    multiple choice: n=%d  text-only correct %d"
              % (len(mcq), sum(b["text_only"] for b in mcq.values())))
        if answerer.startswith("qwen"):
            check("qwen n", len(items), 68)
            check("qwen text-only", txt, 33)
            check("qwen text+image", img, 47)
            check("qwen necessary", b_only, 16)
            check("qwen p", round(p, 4), 0.0013)
            check("qwen mcq text-only", sum(b["text_only"] for b in mcq.values()), 18)
        if answerer.startswith("google"):
            check("gemini n", len(items), 67)
            check("gemini text-only", txt, 31)
            check("gemini text+image", img, 41)
            check("gemini necessary", b_only, 11)
            check("gemini p", round(p, 4), 0.0063)
            check("gemini mcq text-only", sum(b["text_only"] for b in mcq.values()), 15)

    if len(necessity_flags) == 2:
        a1, a2 = sorted(necessity_flags, key=lambda a: (a != "qwen/qwen3-vl-8b-instruct", a))
        shared = sorted(set(necessity_flags[a1]) & set(necessity_flags[a2]))
        pairs = [(necessity_flags[a1][i], necessity_flags[a2][i]) for i in shared]
        b = sum(1 for x, y in pairs if x == 1 and y == 0)
        d = sum(1 for x, y in pairs if x == 0 and y == 1)
        k = cohen_kappa(pairs)
        raw = sum(1 for x, y in pairs if x == y) / len(pairs)
        print("  answerer agreement on %d shared items: kappa=%.3f  raw=%.3f  p=%.4f"
              % (len(pairs), k, raw, exact_mcnemar(b, d)))
        check("answerer kappa", round(k, 2), 0.40)
        check("answerer p", round(exact_mcnemar(b, d), 2), 0.27)

    # measured vs rated
    rated: dict[str, list[int]] = {}
    for (c, a, r), o in judges.items():
        rated.setdefault("%s::%s" % (c, a), []).append(o["visual_necessity"])
    qwen = necessity_flags.get("qwen/qwen3-vl-8b-instruct", {})
    pairs = []
    for item, flag in qwen.items():
        parts = item.split("::")
        key = "framec::%s::%s::%s" % (parts[1], parts[2], parts[3])
        scores = rated.get(key)
        if scores:
            pairs.append((flag, int(min(scores) >= 3)))
    if pairs:
        k = cohen_kappa(pairs)
        raw = sum(1 for x, y in pairs if x == y) / len(pairs)
        both = sum(1 for x, y in pairs if x == 1 and y == 1)
        neither = sum(1 for x, y in pairs if x == 0 and y == 0)
        rated_only = sum(1 for x, y in pairs if x == 0 and y == 1)
        measured_only = sum(1 for x, y in pairs if x == 1 and y == 0)
        print("\nMEASURED vs RATED necessity on %d items" % len(pairs))
        print("  both=%d  neither=%d  rated only=%d  measured only=%d  raw=%.2f  kappa=%.2f"
              % (both, neither, rated_only, measured_only, raw, k))
        check("measured-vs-rated kappa", round(k, 2), 0.42)
        check("measured-vs-rated raw", round(raw, 2), 0.78)

    # ---------------------------------------------------------------- verdict
    print("\n" + "=" * 72)
    if not args.check:
        print("Recomputation complete.  Re-run with --check to assert the paper's values.")
        return 0
    if failures:
        print("FAILED %d check(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("All checks passed: every reported quantity recomputes from the released records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
