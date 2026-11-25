"""Executable offline endpoint-native request and envelope contracts for v3.10.2.

This module performs no I/O.  It constructs JSON-ready request mappings and
strictly extracts the frozen seven-field short-answer judge object without
aliasing, insertion, fallback, or repair.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .validation import decode_one_json_object, judge_response_format, validate_judgement

# Surface-shape fixtures for the offline envelope contract. The rater names
# here are the LEGACY routes and are never dialled: this module performs no
# I/O. The census raters are routes.JUDGE_MODELS_R2C.
MODELS = {
    "chat_completions": "qwen/qwen3-vl-8b-instruct",
    "messages": "claude-sonnet-5",
    "responses": "gpt-5.6-terra",
}
SURFACE_ORDER = ("chat_completions", "messages", "responses")
TOOL_NAME = "submit_judgement"


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_V3102_ENDPOINT:" + reason)


def _schema() -> dict[str, Any]:
    # Reuse the unchanged v3.10 frozen judge schema rather than maintaining a
    # second semantic schema.  Return a detached mapping safe for payload use.
    value = judge_response_format("short_answer")
    return dict(value["json_schema"]["schema"])


def _messages(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)) or not messages:
        raise _blocked("MESSAGES")
    out: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, Mapping) or set(item) != {"role", "content"}:
            raise _blocked("MESSAGES")
        role, content = item.get("role"), item.get("content")
        if role not in {"system", "user", "assistant"} or not isinstance(content, str) or not content:
            raise _blocked("MESSAGES")
        out.append({"role": role, "content": content})
    return out


def build_request(surface: str, messages: Sequence[Mapping[str, Any]], *, max_tokens: int = 2048) -> dict[str, Any]:
    """Build the exact prospective request body for one frozen route surface."""
    if surface not in SURFACE_ORDER:
        raise _blocked("SURFACE")
    if type(max_tokens) is not int or not 1 <= max_tokens <= 2048:
        raise _blocked("MAX_TOKENS")
    msgs = _messages(messages)
    model = MODELS[surface]
    schema = _schema()
    if surface == "chat_completions":
        return {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ecm_tqag_v310_judge_short_answer", "strict": True, "schema": schema},
            },
        }
    if surface == "messages":
        system = [m["content"] for m in msgs if m["role"] == "system"]
        non_system = [m for m in msgs if m["role"] != "system"]
        if len(system) > 1 or not non_system:
            raise _blocked("MESSAGES_SYSTEM")
        body = {
            "model": model,
            "messages": non_system,
            "max_tokens": max_tokens,
            "tools": [{"name": TOOL_NAME, "description": "Submit the frozen ECM-TQAG judgement.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }
        if system:
            body["system"] = system[0]
        return body
    # OpenAI Responses native structured-text contract.
    return {
        "model": model,
        "input": msgs,
        "max_output_tokens": max_tokens,
        "text": {
            "format": {"type": "json_schema", "name": "ecm_tqag_v310_judge_short_answer", "strict": True, "schema": schema}
        },
    }


def _exact_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _blocked("JUDGE_OBJECT")
    # Unchanged validator enforces exact key set and values; no mutation occurs.
    return validate_judgement(value, question_type="short_answer")


def extract_response(surface: str, envelope: Any) -> dict[str, Any]:
    """Extract one judge object from an exact endpoint envelope, fail closed."""
    if surface not in SURFACE_ORDER or not isinstance(envelope, Mapping):
        raise _blocked("ENVELOPE")
    expected_model = MODELS[surface]
    if envelope.get("model") != expected_model:
        raise _blocked("MODEL_IDENTITY")
    if surface == "chat_completions":
        choices = envelope.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
            raise _blocked("CHAT_CARDINALITY")
        message = choices[0].get("message")
        if not isinstance(message, Mapping) or set(message) not in ({"content"}, {"role", "content"}):
            raise _blocked("CHAT_MESSAGE")
        if "role" in message and message.get("role") != "assistant":
            raise _blocked("CHAT_MESSAGE")
        return _exact_mapping(decode_one_json_object(message.get("content")))
    if surface == "messages":
        content = envelope.get("content")
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], Mapping):
            raise _blocked("TOOL_CARDINALITY")
        block = content[0]
        if set(block) != {"type", "name", "input"} or block.get("type") != "tool_use" or block.get("name") != TOOL_NAME:
            raise _blocked("TOOL_SELECTION")
        return _exact_mapping(block.get("input"))
    output = envelope.get("output")
    if not isinstance(output, list) or len(output) != 1 or not isinstance(output[0], Mapping):
        raise _blocked("RESPONSES_CARDINALITY")
    item = output[0]
    content = item.get("content")
    if item.get("type") != "message" or set(item) not in ({"type", "content"}, {"type", "role", "content"}):
        raise _blocked("RESPONSES_MESSAGE")
    if "role" in item and item.get("role") != "assistant":
        raise _blocked("RESPONSES_MESSAGE")
    if not isinstance(content, list) or len(content) != 1:
        raise _blocked("RESPONSES_MESSAGE")
    part = content[0]
    if not isinstance(part, Mapping) or set(part) != {"type", "text"} or part.get("type") != "output_text":
        raise _blocked("OUTPUT_TEXT")
    return _exact_mapping(decode_one_json_object(part.get("text")))


def build_native_request(
    surface: str,
    *,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Build a route-native body while rejecting caller/model drift."""
    if surface not in MODELS or model != MODELS[surface]:
        raise _blocked("MODEL_IDENTITY")
    return build_request(surface, messages, max_tokens=max_tokens)


def extract_native_judgement(surface: str, envelope: Any, *, expected_model: str) -> dict[str, Any]:
    """Extract under an explicit frozen model identity, without repair."""
    if surface not in MODELS or expected_model != MODELS[surface]:
        raise _blocked("MODEL_IDENTITY")
    return extract_response(surface, envelope)


__all__ = [
    "MODELS", "SURFACE_ORDER", "TOOL_NAME", "build_request", "extract_response",
    "build_native_request", "extract_native_judgement",
]

