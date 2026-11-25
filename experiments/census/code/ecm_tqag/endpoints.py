"""Round-4 primary endpoint: paired visual-necessity margin, frozen before execution.

Frozen source: prospective/v3103_round2/ROUND4_NECESSITY_ADDENDUM.md v2, §2.

Rounds 1, 2e and 3 all failed to separate the arms on the protocol's primary
endpoint ``V`` (``min(s1,s2,s3) >= 3``), because judged VISUAL NECESSITY is a
near-constant zero on this corpus and a near-constant endpoint cannot
discriminate arms at any feasible n. This module implements the more sensitive
endpoint pre-registered for round 4 on the SAME judged quantity:

    M(c, a) = min over gate-passing judges j of N_j(c, a)      (NOT thresholded)

where ``N_j`` is judge j's ``visual_necessity`` score in 1..5.

``V`` is NOT relaxed, the threshold 3 is NOT lowered, and the gate ``G`` is NOT
modified anywhere in this module: ``V`` continues to be reported alongside.

Three pair-inclusion rules are frozen (§2) and ALL THREE must be reported every
time, whatever they show -- the triple is fixed so that rule-shopping after
seeing round-4 data is impossible:

  strict  (PRIMARY) chunk contributes only if BOTH judges returned gate-passing
                    records for BOTH arms, so ``min`` is over the same number of
                    judges on each side.
  lenient           ``min`` over whatever gate-passing records exist.
  itt               every assigned chunk contributes; missing/failed judge
                    record yields necessity 0 for that arm. Borrows strength
                    from admission and partly re-measures the mechanical
                    effect, so it is NOT primary despite being most favourable.

Primary test: paired two-sided EXACT SIGN TEST on discordant pairs of
M(c, ecm_full) vs M(c, b) under ``strict``, for ECM vs direct and ECM vs
structured_no_contract, with HOLM control at family alpha=0.05 (0.025 then 0.05).

Direction is NOT pre-assumed: the test is two-sided and a baseline beating ECM
is a valid, reportable outcome.
"""
from __future__ import annotations

from math import comb
from typing import Any, Mapping, Sequence

# Family 1 (pre-registered before round 4): the contract against the two
# uninformed controls. Holm is applied WITHIN this family only, so adding a new
# arm cannot retroactively weaken an already pre-registered rejection.
ARMS_CONTRAST = (("ecm_full", "direct"), ("ecm_full", "structured_no_contract"))

# Family 2 (pre-registered before this census): mechanism isolation. gate_disclosed
# states all five gate conditions but imposes no select/plan/realise ordering, so
# this contrast separates "the criterion was disclosed" from "evidence was frozen
# first". Its own family at alpha 0.05; never pooled into family 1.
ARMS_CONTRAST_MECHANISM = (("ecm_full", "gate_disclosed"),)
POOLING_RULES = ("strict", "lenient", "itt")
FAMILY_ALPHA = 0.05


def exact_sign_test(b: int, c: int) -> float:
    """Two-sided exact sign test p-value on discordant counts (b, c).

    Under H0 each discordant pair is a fair coin, so the discordant count is
    Binomial(n=b+c, 0.5). The two-sided p is the doubled smaller tail, clamped
    at 1. b + c == 0 means no discordant pairs and therefore no evidence in
    either direction: p = 1.
    """
    if b < 0 or c < 0:
        raise ValueError("BLOCKED_ROUND4:SIGN_TEST_NEGATIVE")
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def holm(pvalues: Mapping[str, float], alpha: float = FAMILY_ALPHA) -> dict[str, Any]:
    """Holm step-down at family ``alpha`` over a small labelled family.

    Returns per-hypothesis threshold, rejection flag, and adjusted p-value.
    Rejection stops at the first non-rejection (step-down), as Holm requires.
    """
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    out: dict[str, Any] = {}
    running = 0.0
    still_rejecting = True
    for rank, (name, p) in enumerate(items):
        threshold = alpha / (m - rank)
        if still_rejecting and p <= threshold:
            rejected = True
        else:
            rejected = False
            still_rejecting = False
        running = max(running, min(1.0, p * (m - rank)))
        out[name] = {
            "p_value": p,
            "holm_rank": rank + 1,
            "holm_threshold": threshold,
            "rejected_at_family_alpha": rejected,
            "p_adjusted_holm": running,
        }
    return out


def _gate_passing(record: Any) -> bool:
    """A judge record counts only if it is COMPLETE and passes its own gates.

    Mirrors ``gamma_j`` exactly as used by ``V``: a critical provenance
    violation disqualifies the record.
    """
    if not isinstance(record, Mapping) or record.get("status") != "COMPLETE":
        return False
    obj = record.get("object")
    if not isinstance(obj, Mapping):
        return False
    if obj.get("critical_provenance_violation") is True:
        return False
    return isinstance(obj.get("visual_necessity"), int)


def necessity_scores(
    judge_records: Mapping[str, Any],
    *,
    chunk_ids: Sequence[str],
    arms: Sequence[str],
    judges: Sequence[str],
    mode: str,
) -> dict[str, dict[str, dict[str, int]]]:
    """Collect gate-passing visual_necessity per chunk, arm, judge."""
    scores: dict[str, dict[str, dict[str, int]]] = {
        cid: {arm: {} for arm in arms} for cid in chunk_ids
    }
    for cid in chunk_ids:
        for arm in arms:
            for judge in judges:
                tid = f"judge::{mode}::{cid}::{arm}::{judge}"
                rec = judge_records.get(tid)
                if _gate_passing(rec):
                    scores[cid][arm][judge] = int(rec["object"]["visual_necessity"])
    return scores


def margin(
    scores: Mapping[str, Mapping[str, Mapping[str, int]]],
    *,
    chunk_id: str,
    arm: str,
    judges: Sequence[str],
    rule: str,
) -> int | None:
    """M(c, a) under one pooling rule. None means the chunk does not contribute."""
    per_judge = scores[chunk_id][arm]
    if rule == "strict":
        if len(per_judge) != len(judges):
            return None
        return min(per_judge.values())
    if rule == "lenient":
        if not per_judge:
            return None
        return min(per_judge.values())
    if rule == "itt":
        if len(per_judge) != len(judges):
            return 0
        return min(per_judge.values())
    raise ValueError("BLOCKED_ROUND4:UNKNOWN_POOLING_RULE:" + str(rule))


def contrast(
    scores: Mapping[str, Mapping[str, Mapping[str, int]]],
    *,
    chunk_ids: Sequence[str],
    left: str,
    right: str,
    judges: Sequence[str],
    rule: str,
) -> dict[str, Any]:
    """One paired contrast under one pooling rule."""
    left_higher = right_higher = ties = 0
    contributing: list[str] = []
    pairs: list[dict[str, Any]] = []
    for cid in chunk_ids:
        lm = margin(scores, chunk_id=cid, arm=left, judges=judges, rule=rule)
        rm = margin(scores, chunk_id=cid, arm=right, judges=judges, rule=rule)
        if lm is None or rm is None:
            continue
        contributing.append(cid)
        pairs.append({"chunk_id": cid, "left": lm, "right": rm})
        if lm > rm:
            left_higher += 1
        elif rm > lm:
            right_higher += 1
        else:
            ties += 1
    p = exact_sign_test(left_higher, right_higher)
    return {
        "left_arm": left,
        "right_arm": right,
        "pooling_rule": rule,
        "n_contributing": len(contributing),
        "left_higher": left_higher,
        "right_higher": right_higher,
        "ties": ties,
        "discordant": left_higher + right_higher,
        "p_two_sided_exact_sign": p,
        "pairs": pairs,
    }


def analyse(
    judge_records: Mapping[str, Any],
    *,
    chunk_ids: Sequence[str],
    arms: Sequence[str],
    judges: Sequence[str],
    mode: str,
    below_floor: bool,
) -> dict[str, Any]:
    """Full frozen round-4 endpoint analysis: all three rules, Holm on strict."""
    scores = necessity_scores(
        judge_records, chunk_ids=chunk_ids, arms=arms, judges=judges, mode=mode
    )
    results: dict[str, dict[str, Any]] = {}
    for rule in POOLING_RULES:
        for left, right in ARMS_CONTRAST:
            key = f"{rule}::{left}_vs_{right}"
            results[key] = contrast(
                scores, chunk_ids=chunk_ids, left=left, right=right,
                judges=judges, rule=rule,
            )
    strict_family = {
        f"{left}_vs_{right}": results[f"strict::{left}_vs_{right}"]["p_two_sided_exact_sign"]
        for left, right in ARMS_CONTRAST
    }
    holm_result = holm(strict_family, FAMILY_ALPHA)
    if below_floor:
        for entry in holm_result.values():
            entry["rejected_at_family_alpha"] = None
            entry["suppressed_reason"] = (
                "frame below pre-registered floor of 40; ROUND4_NECESSITY_ADDENDUM.md "
                "section 4 floor clause: reported as underpowered descriptive, sign "
                "tests reported WITHOUT significance claims"
            )
    return {
        "schema": "ecm-tqag.round4.necessity-endpoint.v1",
        "endpoint": "M(c,a) = min over gate-passing judges of visual_necessity (not thresholded)",
        "primary_rule": "strict",
        "family_alpha": FAMILY_ALPHA,
        "below_floor": below_floor,
        "significance_claims_permitted": not below_floor,
        "contrasts": results,
        "holm_on_strict": holm_result,
        "per_chunk_scores": scores,
    }


__all__ = [
    "ARMS_CONTRAST", "POOLING_RULES", "FAMILY_ALPHA",
    "exact_sign_test", "holm", "necessity_scores", "margin",
    "contrast", "analyse",
]
