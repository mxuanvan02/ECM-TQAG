"""Structural contracts for evidence-first ECM-TQAG item construction.

These checks make a constructed TQA item provenance-complete and tamper-evident.
They intentionally do not decide legal or semantic correctness.
"""
from __future__ import annotations

from typing import Any

from .core import CONDITIONS, _SHA256, _SAFE_ID, _object, _string, receipt

CONSTRUCTED_ITEM_SCHEMA = "ecm-tqag.constructed-item.v1"


def _atom(value: Any, index: int) -> dict[str, Any]:
    atom = _object(value, {"atom_id", "value", "kind"}, {"atom_id", "value", "kind"}, f"answer_atoms[{index}]")
    if not isinstance(atom["atom_id"], str) or not _SAFE_ID.fullmatch(atom["atom_id"]):
        raise ValueError(f"invalid answer atom id at {index}")
    _string(atom["value"], f"answer_atoms[{index}].value", max_len=4000)
    _string(atom["kind"], f"answer_atoms[{index}].kind", max_len=100)
    return atom


def validate_constructed_item(item: dict[str, Any]) -> dict[str, str]:
    """Validate the public structural contract for one generated four-choice item."""
    required = {
        "schema", "item_id", "package_sha256", "motif", "derivation",
        "answer_atoms", "provenance_trace", "question", "choices",
        "answer_index", "answer", "rationale",
    }
    obj = _object(item, required, required, "constructed_item")
    if obj["schema"] != CONSTRUCTED_ITEM_SCHEMA:
        raise ValueError("wrong constructed-item schema")
    if not isinstance(obj["item_id"], str) or not _SAFE_ID.fullmatch(obj["item_id"]):
        raise ValueError("invalid constructed item_id")
    if not isinstance(obj["package_sha256"], str) or not _SHA256.fullmatch(obj["package_sha256"]):
        raise ValueError("invalid constructed-item package SHA-256")
    motif = _object(obj["motif"], {"type", "evidence_nodes"}, {"type", "evidence_nodes"}, "motif")
    _string(motif["type"], "motif.type", max_len=100)
    nodes = motif["evidence_nodes"]
    if not isinstance(nodes, list) or not nodes or any(not isinstance(v, str) or not v.strip() for v in nodes):
        raise ValueError("motif.evidence_nodes must be a non-empty string list")
    derivation = obj["derivation"]
    if not isinstance(derivation, list) or not derivation:
        raise ValueError("derivation must be a non-empty ordered list")
    for index, step in enumerate(derivation):
        _string(step, f"derivation[{index}]", max_len=1000)
    atoms = obj["answer_atoms"]
    if not isinstance(atoms, list) or not atoms:
        raise ValueError("answer_atoms must be non-empty")
    atoms = [_atom(atom, index) for index, atom in enumerate(atoms)]
    atom_ids = [atom["atom_id"] for atom in atoms]
    if len(atom_ids) != len(set(atom_ids)):
        raise ValueError("answer atom ids must be unique")
    traces = obj["provenance_trace"]
    if not isinstance(traces, list) or len(traces) != len(atoms):
        raise ValueError("provenance_trace must contain exactly one record per answer atom")
    traced_atoms: list[str] = []
    for index, trace in enumerate(traces):
        record = _object(trace, {"atom_id", "source_ref"}, {"atom_id", "source_ref"}, f"provenance_trace[{index}]")
        if record["atom_id"] not in atom_ids:
            raise ValueError("provenance trace references an unknown atom")
        _string(record["source_ref"], f"provenance_trace[{index}].source_ref", max_len=500)
        traced_atoms.append(record["atom_id"])
    if set(traced_atoms) != set(atom_ids) or len(traced_atoms) != len(set(traced_atoms)):
        raise ValueError("every answer atom must have exactly one provenance trace")
    _string(obj["question"], "question", max_len=4000)
    choices = obj["choices"]
    if not isinstance(choices, list) or len(choices) != 4:
        raise ValueError("choices must contain exactly four options")
    for index, choice in enumerate(choices):
        _string(choice, f"choices[{index}]", max_len=4000)
    if len(set(choices)) != 4:
        raise ValueError("choices must be unique")
    answer_index = obj["answer_index"]
    if isinstance(answer_index, bool) or not isinstance(answer_index, int) or not 0 <= answer_index < 4:
        raise ValueError("answer_index must be an integer from 0 to 3")
    if obj["answer"] != choices[answer_index]:
        raise ValueError("answer must exactly match the indexed choice")
    _string(obj["rationale"], "rationale", max_len=8000)
    return {"item_id": obj["item_id"], "constructed_item_sha256": receipt(obj)}


def validate_constructed_directory(path: str | Any) -> dict[str, Any]:
    from pathlib import Path
    import json

    directory = Path(path)
    if not directory.is_dir():
        raise ValueError(f"not a directory: {directory}")
    reports, identities = [], set()
    for entry in sorted((p for p in directory.rglob("*.json") if p.is_file() and not p.is_symlink()), key=lambda p: p.relative_to(directory).as_posix()):
        try:
            report = validate_constructed_item(json.loads(entry.read_text(encoding="utf-8")))
        except Exception as exc:
            raise ValueError(f"{entry.name}: {exc}") from exc
        if report["item_id"] in identities:
            raise ValueError(f"duplicate constructed item id: {report['item_id']}")
        identities.add(report["item_id"])
        reports.append({"path": entry.relative_to(directory).as_posix(), **report})
    if not reports:
        raise ValueError("no constructed item JSON files")
    return {"status": "PASS", "constructed_item_count": len(reports), "items": reports}
