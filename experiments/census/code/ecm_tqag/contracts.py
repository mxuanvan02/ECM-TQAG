"""Frozen offline contracts for ECM-TQAG v3.10.

This module performs no network I/O.  It verifies the prospective artifacts and
recomputes deterministic assignments without repairing malformed input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

ARMS = ("ecm_full", "gate_disclosed", "direct", "structured_no_contract")
GENERATOR_MODEL = "qwen/qwen3-vl-8b-instruct"


def _blocked(reason: str) -> ValueError:
    return ValueError("BLOCKED_V310:" + reason)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def recompute_type_assignment(
    chunk_ids: Sequence[str], *, salt: str
) -> dict[str, str]:
    if (
        len(chunk_ids) != 16
        or len(set(chunk_ids)) != 16
        or not isinstance(salt, str)
        or not salt
        or any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids)
    ):
        raise _blocked("TYPE_ASSIGNMENT")
    ordered = sorted(
        chunk_ids,
        key=lambda chunk_id: (
            hashlib.sha256(f"{salt}|{chunk_id}".encode("utf-8")).hexdigest(),
            chunk_id,
        ),
    )
    mcq = set(ordered[:8])
    return {
        chunk_id: "multiple_choice" if chunk_id in mcq else "short_answer"
        for chunk_id in chunk_ids
    }


def recompute_pilot_selection(
    assignments: Mapping[str, str],
    doc_ids: Mapping[str, str],
    *,
    salt: str,
) -> list[dict[str, str]]:
    if (
        set(assignments) != set(doc_ids)
        or len(assignments) != 16
        or not isinstance(salt, str)
        or not salt
    ):
        raise _blocked("PILOT_SELECTION")
    if set(assignments.values()) != {"multiple_choice", "short_answer"}:
        raise _blocked("PILOT_SELECTION")

    selected: list[dict[str, str]] = []
    used_docs: set[str] = set()
    for question_type in ("multiple_choice", "short_answer"):
        candidates = [
            chunk_id
            for chunk_id, assigned_type in assignments.items()
            if assigned_type == question_type
        ]
        candidates.sort(
            key=lambda chunk_id: (
                hashlib.sha256(f"{salt}|{chunk_id}".encode("utf-8")).hexdigest(),
                chunk_id,
            )
        )
        count = 0
        for chunk_id in candidates:
            doc_id = doc_ids.get(chunk_id)
            if not isinstance(doc_id, str) or not doc_id:
                raise _blocked("PILOT_SELECTION")
            if doc_id in used_docs:
                continue
            selected.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "question_type": question_type,
                }
            )
            used_docs.add(doc_id)
            count += 1
            if count == 2:
                break
        if count != 2:
            raise _blocked("PILOT_SELECTION")
    return selected


def verify_candidate_digest(
    root: Path | str, digest_path: Path | str
) -> dict[str, Any]:
    root_path = Path(root)
    try:
        digest = json.loads(Path(digest_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise _blocked("DIGEST") from exc
    if not isinstance(digest, dict):
        raise _blocked("DIGEST")
    declared = digest.get("artifact_sha256")
    if not isinstance(declared, dict) or len(declared) != 7:
        raise _blocked("DIGEST")
    if any(
        not isinstance(relative, str)
        or not isinstance(expected, str)
        or len(expected) != 64
        for relative, expected in declared.items()
    ):
        raise _blocked("DIGEST")
    for relative, expected in declared.items():
        path = root_path / relative
        try:
            actual = file_sha256(path)
        except OSError as exc:
            raise _blocked("DIGEST") from exc
        if actual != expected:
            raise _blocked("DIGEST")
    aggregate = canonical_sha256(declared)
    if aggregate != digest.get("aggregate_sha256"):
        raise _blocked("DIGEST")
    if digest.get("provider_calls") != 0 or digest.get("paid_authorization") is not False:
        raise _blocked("DIGEST")
    return dict(digest)


__all__ = [
    "ARMS",
    "GENERATOR_MODEL",
    "canonical_bytes",
    "canonical_sha256",
    "file_sha256",
    "recompute_pilot_selection",
    "recompute_type_assignment",
    "verify_candidate_digest",
]
