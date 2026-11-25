"""Strict provider shapes, prompt rendering, and local gates for v3.10."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import ARMS
from .judge_contract import append_judge_output_contract

EXPECTED_JUDGE_KEYS = frozenset({
    "answerability",
    "critical_provenance_violation",
    "evidence_correctness",
    "pedagogical_value",
    "rationale",
    "vietnamese_language",
    "visual_necessity",
})

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "official"
    / "PROMPT_SCHEMA_CONTRACT.json"
)


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_V310:" + reason)


def _format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {"name": name, "strict": True, "schema": schema},
    }


def _visual_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["image_sha256", "description", "necessity_rationale"],
        "properties": {
            "image_sha256": {"type": "string"},
            "description": {"type": "string"},
            "necessity_rationale": {"type": "string"},
        },
    }


def generation_response_format(question_type: str) -> dict[str, Any]:
    common = {
        "question": {"type": "string"},
        "answer": {"type": "string"},
        "question_type": {"type": "string", "enum": [question_type]},
        "text_evidence_quote": {"type": "string"},
        "visual_evidence": _visual_schema(),
    }
    if question_type == "short_answer":
        properties = common
    elif question_type == "multiple_choice":
        properties = {
            **common,
            "options": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {"type": "string"},
            },
            "correct_option": {"type": "integer"},
        }
    else:
        raise _blocked("QUESTION_TYPE")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }
    return _format("ecm_tqag_v310_generation_" + question_type, schema)


def judge_response_format(question_type: str) -> dict[str, Any]:
    if question_type not in {"short_answer", "multiple_choice"}:
        raise _blocked("QUESTION_TYPE")
    score = {"type": "integer", "minimum": 1, "maximum": 5}
    properties: dict[str, Any] = {
        "evidence_correctness": score,
        "visual_necessity": score,
        "answerability": score,
        "pedagogical_value": score,
        "vietnamese_language": score,
        "critical_provenance_violation": {"type": "boolean"},
        "rationale": {"type": "string"},
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }
    return _format("ecm_tqag_official_judge", schema)


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite JSON number")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def decode_one_json_object(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw:
        raise _blocked("JSON_OBJECT")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except Exception as exc:
        raise _blocked("JSON_OBJECT") from exc
    if not isinstance(value, dict):
        raise _blocked("JSON_OBJECT")
    return value


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_visual(value: Any, image_hashes: set[str]) -> bool:
    if not isinstance(value, Mapping):
        return False
    if set(value) != {"image_sha256", "description", "necessity_rationale"}:
        return False
    return (
        value.get("image_sha256") in image_hashes
        and _nonempty_string(value.get("description"))
        and _nonempty_string(value.get("necessity_rationale"))
    )


def validate_generation(
    obj: Any,
    *,
    question_type: str,
    source_text: str,
    image_hashes: set[str],
) -> dict[str, Any]:
    common = {
        "question",
        "answer",
        "question_type",
        "text_evidence_quote",
        "visual_evidence",
    }
    expected = common if question_type == "short_answer" else common | {"options", "correct_option"}
    if question_type not in {"short_answer", "multiple_choice"}:
        raise _blocked("QUESTION_TYPE")
    if not isinstance(obj, Mapping) or set(obj) != expected:
        raise _blocked("GENERATION")
    out = dict(obj)
    if out.get("question_type") != question_type:
        raise _blocked("GENERATION")
    if not all(_nonempty_string(out.get(key)) for key in ("question", "answer", "text_evidence_quote")):
        raise _blocked("GENERATION")
    quote = out["text_evidence_quote"]
    if not isinstance(source_text, str) or quote not in source_text:
        raise _blocked("GENERATION")
    if not _validate_visual(out.get("visual_evidence"), image_hashes):
        raise _blocked("GENERATION")
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
            raise _blocked("GENERATION")
    return out


def validate_judgement(obj: Any, *, question_type: str) -> dict[str, Any]:
    if question_type not in {"short_answer", "multiple_choice"}:
        raise _blocked("QUESTION_TYPE")
    if not isinstance(obj, Mapping) or set(obj) != EXPECTED_JUDGE_KEYS:
        raise _blocked("JUDGE")
    out = dict(obj)
    for key in EXPECTED_JUDGE_KEYS - {"critical_provenance_violation", "rationale"}:
        value = out.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise _blocked("JUDGE")
    if not isinstance(out.get("critical_provenance_violation"), bool):
        raise _blocked("JUDGE")
    if not _nonempty_string(out.get("rationale")):
        raise _blocked("JUDGE")
    return out


def _contract() -> dict[str, Any]:
    try:
        value = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise _blocked("PROMPT_CONTRACT") from exc
    if not isinstance(value, dict):
        raise _blocked("PROMPT_CONTRACT")
    return value


def render_generation_messages(
    arm: str,
    *,
    question_type: str,
    source_text: str,
    document_structure: Any,
    image_hashes: Sequence[str],
) -> list[dict[str, str]]:
    if arm not in ARMS:
        raise _blocked("ARM")
    generation_response_format(question_type)
    prompt = _contract().get("generator_prompts", {}).get(arm)
    if not isinstance(prompt, Mapping):
        raise _blocked("PROMPT_CONTRACT")
    try:
        user = str(prompt["user_template"]).format(
            source_text=source_text,
            document_structure_json=json.dumps(document_structure, ensure_ascii=False, sort_keys=True),
            question_type=question_type,
            image_hashes_json=json.dumps(list(image_hashes), ensure_ascii=False),
        )
        system = str(prompt["system"])
    except Exception as exc:
        raise _blocked("PROMPT_CONTRACT") from exc
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def render_judge_messages(
    *,
    candidate_code: str,
    question_type: str,
    source_text: str,
    image_hashes: Sequence[str],
    candidate: Mapping[str, Any],
) -> list[dict[str, str]]:
    judge_response_format(question_type)
    prompt = _contract().get("judge_prompt")
    if not isinstance(prompt, Mapping):
        raise _blocked("PROMPT_CONTRACT")
    try:
        user = str(prompt["user_template"]).format(
            candidate_code=candidate_code,
            source_text=source_text,
            question_type=question_type,
            image_hashes_json=json.dumps(list(image_hashes), ensure_ascii=False),
            candidate_json=json.dumps(candidate, ensure_ascii=False, sort_keys=True),
        )
        system = append_judge_output_contract(str(prompt["system"]))
    except Exception as exc:
        raise _blocked("PROMPT_CONTRACT") from exc
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


__all__ = [
    "decode_one_json_object",
    "generation_response_format",
    "judge_response_format",
    "render_generation_messages",
    "render_judge_messages",
    "validate_generation",
    "validate_judgement",
]
