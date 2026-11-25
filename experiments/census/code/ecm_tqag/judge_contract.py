"""Shared prompt-only output contract for official judge requests.

This module does not decode, validate, repair, extract, coerce, retry, or call a
provider.  The existing strict provider schema and local validator remain the
authoritative enforcement mechanisms.
"""
from __future__ import annotations

JUDGE_OUTPUT_CONTRACT = (
    "OUTPUT CONTRACT (mandatory): Output exactly one JSON object and nothing else: "
    "no prose, Markdown, code fence, prefix, or suffix. The object must contain "
    "exactly these seven fields (no additional, missing, renamed, translated, or "
    "aliased fields): evidence_correctness, visual_necessity, answerability, "
    "pedagogical_value, vietnamese_language, critical_provenance_violation, "
    "rationale. Each of evidence_correctness, visual_necessity, answerability, "
    "pedagogical_value, and vietnamese_language must be a JSON integer from 1 "
    "through 5, selected from the supplied evidence rather than from the example. "
    "critical_provenance_violation must be a JSON boolean true or false. rationale "
    "must be a nonempty JSON string grounded in the supplied evidence. "
    "Syntactically valid shape example (illustrative values only; do not copy any values):"
    '{"evidence_correctness":1,"visual_necessity":2,"answerability":3,'
    '"pedagogical_value":4,"vietnamese_language":5,'
    '"critical_provenance_violation":false,"rationale":"Evidence-grounded explanation."}'
    "\nDetermine every substantive value independently from the request."
)


def append_judge_output_contract(system_prompt: str) -> str:
    """Append the shared contract without changing any payload schema or decoder."""
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("BLOCKED_JUDGE_OUTPUT_CONTRACT:SYSTEM_PROMPT")
    return system_prompt.rstrip() + "\n\n" + JUDGE_OUTPUT_CONTRACT


__all__ = ["JUDGE_OUTPUT_CONTRACT", "append_judge_output_contract"]
