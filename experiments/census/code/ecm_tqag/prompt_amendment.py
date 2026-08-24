"""Round-2e prompt repair (D3, minimal arm-neutral form).

Round 2d confirmed defect D3 is real but its FIX was mis-designed: a ~1000-char
instruction block appended identically to all three arms interacted with the two
TERSE arms only, inducing decoder degeneration (valid JSON prefix, then hundreds
of whitespace characters, then EOS without closing the object) in 7/16 direct and
4/16 structured responses, and 0/16 ECM. The resulting 15-vs-5-vs-6 gate contrast
therefore measured the prompt edit rather than the evidence-contract intervention,
and round 2d is sealed as invalid for arm comparison (VALIDITY_SEAL.json).

Round 2e states ONLY the missing convention, in the shortest form that removes the
ambiguity, so that the added token mass is negligible relative to the arm prompts
themselves and cannot plausibly drive an arm-dependent decoding pathology.

WHAT IS FIXED (specification defect, ours):
  ``correct_option`` is documented nowhere in official/PROMPT_SCHEMA_CONTRACT.json
  as 0-based; the schema declares only ``integer``. The 0..3 range and the
  ``answer == options[correct_option]`` equality live exclusively in the
  ``local_validation`` block, i.e. on the validator side. The model was asked for
  an unqualified integer and, in 14 of 24 round-2c MCQ attempts, chose the natural
  human 1-based convention.

WHAT IS NOT CHANGED:
  - the deterministic gate (``correct_option`` in 0..3 and byte-exact
    ``answer == options[correct_option]``);
  - the no-repair policy;
  - the judge prompt, schema, scale, blinding, ITT accounting, zero retry.

Relaxing the gate to accept 1-based indices after observing that most attempts
used them would be post-hoc gate loosening, and is undecidable whenever ``answer``
matches both ``options[co]`` and ``options[co - 1]``.
"""
from __future__ import annotations

from .gate import PROMPT_CLARIFICATION as PROMPT_CLARIFICATION_V1
from ._prompt_amend_v2 import PROMPT_CLARIFICATION_V2

# Minimal arm-neutral statement of the previously unstated convention.
# Deliberately short: two sentences, no restructuring of the arm instruction.
PROMPT_CLARIFICATION_V3 = (
    " Quy ước: text_evidence_quote lấy nguyên văn từ VĂN BẢN NGUỒN (không lấy chữ"
    " chỉ có trong ảnh). Với multiple_choice, correct_option đếm từ 0 (0,1,2,3) và"
    " answer phải chép nguyên văn options[correct_option]."
)


def amend_generation_payload(payload: dict, clarification: str = PROMPT_CLARIFICATION_V3) -> dict:
    """Append the minimal clarification to the user text part of a payload."""
    payload["messages"][1]["content"][0]["text"] += clarification
    return payload


__all__ = [
    "PROMPT_CLARIFICATION_V1",
    "PROMPT_CLARIFICATION_V2",
    "PROMPT_CLARIFICATION_V3",
    "amend_generation_payload",
]
