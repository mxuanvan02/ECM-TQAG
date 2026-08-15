"""Round-2c judge-family substitution (protocol change, frozen before execution).

Round 2b's judge stage was voided by a provider outage: the claude-sonnet-5 route
returned HTTP 503 ("No available accounts") on 17 of 18 calls, so only 1 of 18
candidates received both judges and the hard-valid endpoint was not measurable.

Owner decision (chat 2026-08-15): substitute the two judge families with
claude-opus-5 and gpt-5.6-sol, and re-run the full census.

This is a DISTINCT instrument from round 1 / round 2b, because the judge families
are part of the frozen measurement. It is declared here BEFORE execution:

  - round-1 modules are audit-bound and are NOT modified. ``build_judge_request``
    rejects any judge outside the frozen ``JUDGE_MODELS``, and
    ``build_transport_configs`` only defines the three original routes, so this
    module supplies round-2c-local equivalents instead.
  - the judge PROMPT, the seven-field judgement schema, the 1--5 scale, the
    arm-blind candidate coding, the deterministic gates, ITT accounting and
    zero retry/fallback/replacement are all UNCHANGED.
  - round-2c results are therefore comparable to round 1 on the generation stage
    (identical generator route and gates) but NOT directly comparable on the
    judge stage, which uses different judge families.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ecm_tqag.run.transport import TransportConfig
from ecm_tqag.v310_runner import _verified_evidence
from ecm_tqag.v310_validation import judge_response_format, render_judge_messages

# Substituted judge families (order is stable and used for task ids).
JUDGE_MODELS_R2C = ("claude-opus-5", "gpt-5.6-sol")

GENERATOR_ROUTE = "qwen/qwen3-vl-8b-instruct"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OMNIPROXY_URL = "http://127.0.0.1:8080/v1/chat/completions"

# Retained for provenance: the round-2b judge routes this run replaces.
SUPERSEDED_JUDGE_MODELS = ("claude-sonnet-5", "gpt-5.6-terra")


def build_transport_configs_r2c(
    *, openrouter_key_file: Path, omniproxy_key_file: Path
) -> dict[str, TransportConfig]:
    """Round-2c route table: generator unchanged, two substituted judge routes."""
    common = {"allow_fallbacks": False, "max_retries": 0, "timeout_sec": 300}
    configs = {
        GENERATOR_ROUTE: TransportConfig(
            provider="openrouter",
            model=GENERATOR_ROUTE,
            base_url=OPENROUTER_URL,
            api_key_file=Path(openrouter_key_file),
            **common,
        )
    }
    for judge in JUDGE_MODELS_R2C:
        configs[judge] = TransportConfig(
            provider="omniproxy",
            model=judge,
            base_url=OMNIPROXY_URL,
            api_key_file=Path(omniproxy_key_file),
            **common,
        )
    return configs


def build_judge_request_r2c(
    package: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any],
    candidate_code: str,
    judge_model: str,
    question_type: str,
) -> dict[str, Any]:
    """Round-2c judge request.

    Byte-identical in prompt/schema/decoding to the round-1 builder; the only
    difference is the accepted judge-model allow-list.
    """
    if judge_model not in JUDGE_MODELS_R2C:
        raise ValueError("BLOCKED_ROUND2C:JUDGE_MODEL")
    if not isinstance(candidate_code, str) or not candidate_code.startswith("C-"):
        raise ValueError("BLOCKED_ROUND2C:CANDIDATE_CODE")
    if package.get("question_type") != question_type:
        raise ValueError("BLOCKED_ROUND2C:QUESTION_TYPE")
    evidence = _verified_evidence(package)
    rendered = render_judge_messages(
        candidate_code=candidate_code,
        question_type=question_type,
        source_text=evidence["text"],
        image_hashes=evidence["image_hashes"],
        candidate=candidate,
    )
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": rendered[1]["content"]},
        *evidence["image_parts"],
    ]
    return {
        "model": judge_model,
        "candidate_code": candidate_code,
        "evidence_sha256": evidence["evidence_sha256"],
        "payload": {
            "messages": [rendered[0], {"role": "user", "content": user_content}],
            "temperature": 0,
            "max_tokens": 768,
            "response_format": judge_response_format(question_type),
        },
    }


__all__ = [
    "JUDGE_MODELS_R2C",
    "SUPERSEDED_JUDGE_MODELS",
    "GENERATOR_ROUTE",
    "build_transport_configs_r2c",
    "build_judge_request_r2c",
]
