#!/usr/bin/env python3
"""ECM-v2: the division-of-labour gates.

WHY THIS EXISTS
---------------
The v1 evidence contract asks the generator for a verbatim text quotation and a
content-hashed figure, and the v1 gate checks exactly that: the quote reproduces
inside the conditioning text, and the hash is a member of the bundle. Nothing in
that gate binds the ANSWER to the FIGURE.

Measured consequence on this corpus: the returned quotation already contains the
whole answer in 58% of admitted frame-D items and 79% of admitted frame-E items.
Such an item is answerable by reading the quotation alone; the image is decorative
and its hash is a formality. That is why every multimodal endpoint came back null
while the provenance endpoint reproduced -- the instrument was measuring
provenance, which it enforces, and reporting it as multimodality, which it did
not enforce.

Auditing the v1 contract clause by clause: five of its nine clauses have a
mechanical gate, and the four without one are exactly the multimodal clauses
("the question must genuinely need the image", "the answer must be supported by
both channels", ANSWER-FIRST, SEAL). Those four were requests in a prompt, not
conditions on a response.

WHAT ECM-v2 ADDS
----------------
One principle, three checks. The two evidence channels must divide labour:

    the TEXT quotation establishes what the question is ABOUT;
    the FIGURE supplies what the question ASKS FOR.

    G6  answer-not-in-quote   : N(answer) is not a substring of N(quote).
                                Structural relation between two returned fields.
    G7  answer-meets-figure   : >= 2 content words of the answer occur in the
                                recognised lettering of the chunk's figures.
    G8  description-meets-figure : >= 3 content words of visual_evidence.
                                description occur in that same lettering.

G6 is the load-bearing gate. G7 and G8 are corroborating and WEAK, and their
weakness is measured rather than assumed: see CHANCE_BASELINES below.

HONEST LIMITS, STATED IN THE CODE THAT IMPLEMENTS THEM
------------------------------------------------------
1. G7/G8 compare against OCR of the figure regions, and on this corpus most
   figure regions are tables, i.e. text rendered as layout. Their lettering
   therefore overlaps the prose heavily, so a generic Vietnamese answer hits some
   figure word by chance. Measured by permuting which figure pool is paired with
   which item (400 permutations, frame-E admitted items):

       G7 >= 1 word : observed 0.828, chance 95th pct 0.677  -> lift +0.151
       G7 >= 2 words: observed 0.766, chance 95th pct 0.508  -> lift +0.258
       G7 >= 3 words: observed 0.672, chance 95th pct 0.394  -> lift +0.278
       G8 >= 3 words: observed 0.852, chance 95th pct 0.565  -> lift +0.287
       G8 >= 5 words: observed 0.758, chance 95th pct 0.409  -> lift +0.348

   The >= 1 variant is near chance and is NOT used. Thresholds are set at the
   knee, not at the maximum lift, because a higher threshold rejects short
   correct answers ("Tòa án độc lập" has three content words in total).

2. A stricter gate was designed, measured, and REJECTED: require the answer to
   hit a figure word ABSENT from the prose (the "surplus" channel). On frame E it
   passes 2.3% of items against a 3.2% chance rate -- below chance, because 26 of
   60 chunks have no surplus lettering at all. On law textbooks the figure rarely
   carries wording the prose does not, so that gate would reject nearly every
   item for a corpus reason. It is recorded here so the rejection is documented
   rather than silently dropped.

3. G6 admits 19.5% of frame-E items and 41.7% of frame-D items generated under
   the v1 prompt. That is a filtering rate, not a result: those items were
   produced by a prompt that never asked for the division of labour. ECM-v2 pairs
   these gates with a prompt that states them, and only a fresh generation round
   measures the method.

No gate here relaxes any v1 condition. ECM-v2 = v1 gates AND these three.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Sequence

# --------------------------------------------------------------------------
# thresholds, frozen
# --------------------------------------------------------------------------
G7_MIN_ANSWER_FIGURE_WORDS = 2
G8_MIN_DESCRIPTION_FIGURE_WORDS = 3
MIN_CONTENT_WORD_CHARS = 3

# Measured chance rates, carried beside the thresholds so a reader of the gate
# sees how weak G7/G8 are without leaving the file. Method: 400 random pairings
# of item to figure-word pool over the 128 admitted frame-E items.
CHANCE_BASELINES = {
    "method": ("400 permutations pairing each item with another chunk's figure "
               "lettering; frame-E admitted items, n=128"),
    "g7_answer_meets_figure": {
        "1_word": {"observed": 0.828, "chance_mean": 0.627, "chance_p95": 0.677},
        "2_words": {"observed": 0.766, "chance_mean": 0.457, "chance_p95": 0.508},
        "3_words": {"observed": 0.672, "chance_mean": 0.343, "chance_p95": 0.394},
    },
    "g8_description_meets_figure": {
        "3_words": {"observed": 0.852, "chance_mean": 0.518, "chance_p95": 0.565},
        "5_words": {"observed": 0.758, "chance_mean": 0.366, "chance_p95": 0.409},
    },
    "rejected_variant_answer_meets_surplus_only": {
        "observed": 0.023, "chance_mean": 0.032, "chance_p95": 0.056,
        "why_rejected": ("below chance; 26 of 60 frame-E chunks carry no figure "
                         "lettering absent from the prose, so the gate would "
                         "reject items for a corpus property"),
    },
}

# Vietnamese function words and domain furniture. Excluded from content-word
# overlap so "của / trong / pháp luật / nhà nước" cannot satisfy G7 or G8.
# Accent-folded, because the OCR channel loses diacritics on roughly one word in
# ten even at confidence 90 and a diacritic slip must not decide a gate.
_STOPWORDS = frozenset("""
cua trong va cac nhung mot la co khong duoc voi den tu theo nhu tai ve
cho boi hoac neu thi ma nay do day kia ra vao len xuong nen se dang da cung chi
con hon nua rat qua lam khi sau truoc giua ben ngoai tren duoi phai trai
nguoi viec dieu phan muc chuong tiet quyen luat phap nha nuoc
""".split())

_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹ]+")


def blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_ECM_V2:" + reason)


def normalise(text: Any) -> str:
    """NFC, whitespace-collapsed, stripped. Identical to the v1 quote normaliser."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text or ""))).strip()


def fold(text: Any) -> str:
    """Accent- and case-folded form, for comparisons that must survive OCR
    diacritic loss."""
    stripped = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def content_words(text: Any, *, min_chars: int = MIN_CONTENT_WORD_CHARS) -> set[str]:
    """Accent-folded content words: >= min_chars characters and not a stopword."""
    out: set[str] = set()
    for raw in _WORD_RE.findall(normalise(text)):
        if len(raw) < min_chars:
            continue
        folded = fold(raw)
        if folded and folded not in _STOPWORDS:
            out.add(folded)
    return out


def figure_word_pool(figure_text: Mapping[str, Any] | None) -> set[str]:
    """Content words recognised inside a chunk's figure regions.

    Reads the gated OCR channel (`evidence.figure_text.words`), which is already
    filtered to per-word confidence >= 90 by the augmentation step. This channel
    is NOT quotable as prose and is not used by any v1 gate; here it is used only
    to test overlap, where a residual OCR slip costs a false rejection rather
    than admitting a bad item.
    """
    if not isinstance(figure_text, Mapping):
        return set()
    words = figure_text.get("words")
    if not isinstance(words, Sequence) or isinstance(words, (str, bytes)):
        return set()
    return content_words(" ".join(str(w) for w in words))


# --------------------------------------------------------------------------
# the three gates
# --------------------------------------------------------------------------
def g6_answer_not_in_quote(answer: Any, quote: Any) -> tuple[bool, dict[str, Any]]:
    """The answer must not be readable off the text quotation.

    Load-bearing gate. A relation between two fields the generator returned, so
    it needs no external reference and has no chance baseline: either the
    quotation hands over the answer or it does not.

    Comparison is on the NFC/whitespace-normalised strings WITH diacritics: this
    is a containment test on the model's own output, where accents are reliable,
    and folding them would let "thặng dư" match "thang du" and over-reject.
    """
    a = normalise(answer)
    q = normalise(quote)
    if not a:
        return False, {"reason": "empty_answer"}
    if not q:
        return False, {"reason": "empty_quote"}
    contained = a.lower() in q.lower()
    return (not contained), {
        "answer_chars": len(a),
        "quote_chars": len(q),
        "answer_inside_quote": contained,
    }


def g7_answer_meets_figure(
    answer: Any, pool: set[str], *, minimum: int = G7_MIN_ANSWER_FIGURE_WORDS
) -> tuple[bool, dict[str, Any]]:
    """Content of the answer must be visible in the figure's lettering.

    Weak gate: lift over chance is +0.258 at the frozen threshold of 2. Reported
    with its overlap so a reader can see how close to the threshold an admission
    sat.
    """
    words = content_words(answer)
    hit = sorted(words & pool)
    return (len(hit) >= minimum), {
        "answer_content_words": len(words),
        "figure_pool_words": len(pool),
        "overlap": len(hit),
        "minimum": minimum,
        "overlap_sample": hit[:8],
    }


def g8_description_meets_figure(
    description: Any, pool: set[str], *, minimum: int = G8_MIN_DESCRIPTION_FIGURE_WORDS
) -> tuple[bool, dict[str, Any]]:
    """The stated description must be about THIS figure.

    v1 checked only that `description` was a non-empty string, so a plausible
    invention passed. This requires the description to share content words with
    what OCR actually read inside the figure.
    """
    words = content_words(description)
    hit = sorted(words & pool)
    return (len(hit) >= minimum), {
        "description_content_words": len(words),
        "figure_pool_words": len(pool),
        "overlap": len(hit),
        "minimum": minimum,
        "overlap_sample": hit[:8],
    }


# --------------------------------------------------------------------------
# composite
# --------------------------------------------------------------------------
GATE_NAMES = ("g6_answer_not_in_quote", "g7_answer_meets_figure",
              "g8_description_meets_figure")


def evaluate(
    item: Mapping[str, Any], figure_text: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Evaluate all three ECM-v2 gates on one v1-admitted item.

    `item` is the generator object as the v1 gate returned it, so this function
    presupposes v1 admission and never re-implements it. Returns every gate's
    verdict and evidence, plus `passed` for the conjunction: ECM-v2 admission is
    v1 admission AND all three.
    """
    if not isinstance(item, Mapping):
        raise blocked("ITEM_NOT_MAPPING")
    visual = item.get("visual_evidence")
    if not isinstance(visual, Mapping):
        raise blocked("VISUAL_EVIDENCE_MISSING")

    pool = figure_word_pool(figure_text)
    g6, e6 = g6_answer_not_in_quote(item.get("answer"),
                                    item.get("text_evidence_quote"))
    g7, e7 = g7_answer_meets_figure(item.get("answer"), pool)
    g8, e8 = g8_description_meets_figure(visual.get("description"), pool)

    gates = {
        "g6_answer_not_in_quote": {"passed": g6, **e6},
        "g7_answer_meets_figure": {"passed": g7, **e7},
        "g8_description_meets_figure": {"passed": g8, **e8},
    }
    failed = [name for name in GATE_NAMES if not gates[name]["passed"]]
    return {
        "schema": "ecm-tqag.ecm-v2-gates.v1",
        "passed": not failed,
        "failed_gates": failed,
        "gates": gates,
        "thresholds": {
            "g7_min_answer_figure_words": G7_MIN_ANSWER_FIGURE_WORDS,
            "g8_min_description_figure_words": G8_MIN_DESCRIPTION_FIGURE_WORDS,
            "min_content_word_chars": MIN_CONTENT_WORD_CHARS,
        },
    }


def validate_generation_ecm_v2(
    item: Mapping[str, Any], figure_text: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Fail-closed form: raise on the first failing gate, else return the item
    with the gate record attached under `ecm_v2_gates`.

    Mirrors `validate_generation_round2`, so a runner can call it directly after
    the v1 gate and get the same raise-on-reject contract.
    """
    result = evaluate(item, figure_text)
    if not result["passed"]:
        raise blocked("GATE:" + ",".join(result["failed_gates"]))
    out = dict(item)
    out["ecm_v2_gates"] = result
    return out


__all__ = [
    "CHANCE_BASELINES",
    "G7_MIN_ANSWER_FIGURE_WORDS",
    "G8_MIN_DESCRIPTION_FIGURE_WORDS",
    "GATE_NAMES",
    "content_words",
    "evaluate",
    "figure_word_pool",
    "fold",
    "g6_answer_not_in_quote",
    "g7_answer_meets_figure",
    "g8_description_meets_figure",
    "normalise",
    "validate_generation_ecm_v2",
]
