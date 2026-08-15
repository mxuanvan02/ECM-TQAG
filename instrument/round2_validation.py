"""Round-2 repaired evidence contract (exploratory instrument revision).

Implements defect D1 repair from prospective/v3103_round2/ROUND2_PROTOCOL.md:
  1. verbatim gate on NFC-normalized, whitespace-collapsed strings;
  2. in-order elision tolerance ("..." / "..." markers), reported separately;
  3. MCQ answer rule UNCHANGED (byte-exact answer == options[correct_option]);
  4. all other gates byte-identical to round 1 (schema exactness, visual
     census membership, non-empty fields).

Round-1 semantics remain authoritative for round-1 records; this module is a
distinct prospective instrument and never re-labels round-1 outcomes.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Mapping

from ecm_tqag.v310_validation import (
    _blocked,
    _nonempty_string,
    _validate_visual,
    decode_one_json_object,
)

ROUND2_CONTRACT_SCHEMA = "ecm-tqag.round2.repaired-contract.v1"

_ELISION_RE = re.compile(r"\.\.\.|…")


def normalize_text(value: str) -> str:
    """NFC-normalize and collapse whitespace; strip ends."""
    value = unicodedata.normalize("NFC", value or "")
    return re.sub(r"\s+", " ", value).strip()


def classify_quote(quote: Any, source_text: Any) -> str:
    """Return one of: missing, exact_verbatim, normalized_verbatim,
    elided_verbatim, non_verbatim."""
    if not isinstance(quote, str) or not quote.strip():
        return "missing"
    if not isinstance(source_text, str):
        return "non_verbatim"
    if quote in source_text:
        return "exact_verbatim"
    nq = normalize_text(quote)
    ns = normalize_text(source_text)
    if nq and nq in ns:
        return "normalized_verbatim"
    fragments = [normalize_text(f) for f in _ELISION_RE.split(quote)]
    fragments = [f for f in fragments if f]
    if len(fragments) >= 2 and all(len(f) >= 8 for f in fragments):
        pos = 0
        for frag in fragments:
            idx = ns.find(frag, pos)
            if idx < 0:
                return "non_verbatim"
            pos = idx + len(frag)
        return "elided_verbatim"
    return "non_verbatim"


def validate_generation_round2(
    obj: Any,
    *,
    question_type: str,
    source_text: str,
    image_hashes: set[str],
) -> dict[str, Any]:
    """Round-2 gate. Raises BLOCKED_V310R2:* on failure; returns the object
    plus the quote class under 'round2_quote_class'."""
    common = {
        "question",
        "answer",
        "question_type",
        "text_evidence_quote",
        "visual_evidence",
    }
    expected = (
        common if question_type == "short_answer"
        else common | {"options", "correct_option"}
    )
    if question_type not in {"short_answer", "multiple_choice"}:
        raise _blocked("R2:QUESTION_TYPE")
    if not isinstance(obj, Mapping) or set(obj) != expected:
        raise _blocked("R2:GENERATION")
    out = dict(obj)
    if out.get("question_type") != question_type:
        raise _blocked("R2:GENERATION")
    if not all(_nonempty_string(out.get(key)) for key in ("question", "answer", "text_evidence_quote")):
        raise _blocked("R2:GENERATION")
    quote_class = classify_quote(out["text_evidence_quote"], source_text)
    if quote_class == "non_verbatim" or quote_class == "missing":
        raise _blocked("R2:GENERATION:QUOTE_" + quote_class.upper())
    if not _validate_visual(out.get("visual_evidence"), image_hashes):
        raise _blocked("R2:GENERATION")
    if question_type == "multiple_choice":
        options = out.get("options")
        correct = out.get("correct_option")
        if (
            not isinstance(options, list)
            or len(options) != 4
            or any(not _nonempty_string(option) for option in options)
            or len(set(options)) != 4
            or isinstance(correct, bool)
            or not isinstance(correct, int)
            or not 0 <= correct <= 3
            or out["answer"] != options[correct]
        ):
            raise _blocked("R2:GENERATION")
    out = dict(out)
    out["round2_quote_class"] = quote_class
    return out


PROMPT_CLARIFICATION = (
    " CHU Y KY THUAT: truong text_evidence_quote phai lay tu ken VAN BAN NGUON "
    "(khong lay chu chi thay trong anh); voi multiple_choice, truong answer phai "
    "chep dung nguyen van chuoi cua lua chon dung trong options."
)


def amend_user_template(template: str) -> str:
    return template + PROMPT_CLARIFICATION


def round2_generation_messages(
    arm_prompt: Mapping[str, str],
    *,
    question_type: str,
    source_text: str,
    document_structure: Any,
    image_hashes: list[str],
) -> list[dict[str, str]]:
    """Render round-2 generation messages from a round-1 arm prompt plus the
    D1 clarification (user template only; system unchanged)."""
    user = amend_user_template(str(arm_prompt["user_template"])).format(
        source_text=source_text,
        document_structure_json=json.dumps(document_structure, ensure_ascii=False, sort_keys=True),
        question_type=question_type,
        image_hashes_json=json.dumps(list(image_hashes), ensure_ascii=False),
    )
    return [
        {"role": "system", "content": str(arm_prompt["system"])},
        {"role": "user", "content": user},
    ]
