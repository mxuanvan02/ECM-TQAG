"""Small, dependency-free contract for a constructed ECM-TQAG item.

This module describes construction metadata only.  It neither calls an answering
service nor makes claims about model or human evaluation.
"""
from __future__ import annotations

from typing import Any

from .core import _SAFE_ID, receipt

CONSTRUCTION_SCHEMA = "ecm-tqag.construction-record.v1"


def _object(value: Any, required: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required
    if missing:
        raise ValueError(f"{name} missing: {sorted(missing)}")
    if extra:
        raise ValueError(f"{name} unknown fields: {sorted(extra)}")
    return value


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _text(value: Any, name: str, limit: int = 10_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be non-empty text of at most {limit} characters")
    return value


def validate_construction(record: Any) -> dict[str, Any]:
    """Validate a construction record and return its stable identity and receipt.

    The receipt is a SHA-256 checksum of the record with its ``receipt`` field
    omitted.  It is an integrity aid, not a signature or correctness claim.
    """
    fields = {
        "schema", "item_id", "motif", "program", "answer_atoms",
        "provenance", "question", "choices", "receipt",
    }
    item = _object(record, fields, "construction record")
    if item["schema"] != CONSTRUCTION_SCHEMA:
        raise ValueError("wrong construction record schema")
    _id(item["item_id"], "item_id")

    motif = _object(item["motif"], {"id", "kind", "description"}, "motif")
    _id(motif["id"], "motif id")
    _id(motif["kind"], "motif kind")
    _text(motif["description"], "motif description", 500)

    atoms = item["answer_atoms"]
    if not isinstance(atoms, list) or not atoms:
        raise ValueError("answer_atoms must be a non-empty array")
    atom_ids: set[str] = set()
    for index, atom in enumerate(atoms):
        a = _object(atom, {"id", "value"}, f"answer_atoms[{index}]")
        atom_id = _id(a["id"], "answer atom id")
        if atom_id in atom_ids:
            raise ValueError("answer atom ids must be unique")
        atom_ids.add(atom_id)
        _text(a["value"], "answer atom value")

    program = _object(item["program"], {"steps", "final_answer_atom_id"}, "program")
    if not isinstance(program["steps"], list) or not program["steps"]:
        raise ValueError("program.steps must be a non-empty array")
    step_ids: set[str] = set()
    produced: set[str] = set()
    for index, step in enumerate(program["steps"]):
        s = _object(step, {"id", "operation", "input_atom_ids", "output_atom_id"}, f"program.steps[{index}]")
        step_id = _id(s["id"], "program step id")
        if step_id in step_ids:
            raise ValueError("program step ids must be unique")
        step_ids.add(step_id)
        _id(s["operation"], "program operation")
        if not isinstance(s["input_atom_ids"], list) or any(_id(atom_id, "program input atom id") not in atom_ids for atom_id in s["input_atom_ids"]):
            raise ValueError("program inputs must reference answer atoms")
        output_id = _id(s["output_atom_id"], "program output atom id")
        if output_id not in atom_ids or output_id in produced:
            raise ValueError("program outputs must uniquely reference answer atoms")
        produced.add(output_id)
    final_atom = _id(program["final_answer_atom_id"], "final answer atom id")
    if final_atom not in produced:
        raise ValueError("final answer atom must be produced by the program")

    provenance = item["provenance"]
    if not isinstance(provenance, list) or not provenance:
        raise ValueError("provenance must be a non-empty array")
    provenance_ids: set[str] = set()
    supported_atoms: set[str] = set()
    for index, entry in enumerate(provenance):
        p = _object(entry, {"id", "atom_id", "source"}, f"provenance[{index}]")
        provenance_id = _id(p["id"], "provenance id")
        if provenance_id in provenance_ids:
            raise ValueError("provenance ids must be unique")
        provenance_ids.add(provenance_id)
        atom_id = _id(p["atom_id"], "provenance atom id")
        if atom_id not in atom_ids:
            raise ValueError("provenance must reference an answer atom")
        supported_atoms.add(atom_id)
        _text(p["source"], "provenance source", 500)
    if final_atom not in supported_atoms:
        raise ValueError("final answer atom requires provenance")

    question = _object(item["question"], {"text"}, "question")
    _text(question["text"], "question text", 2_000)
    choices = item["choices"]
    if not isinstance(choices, list) or len(choices) < 2:
        raise ValueError("choices must contain at least two options")
    choice_ids: set[str] = set()
    choice_texts: set[str] = set()
    correct = []
    for index, choice in enumerate(choices):
        c = _object(choice, {"id", "text", "atom_id", "correct"}, f"choices[{index}]")
        choice_id = _id(c["id"], "choice id")
        if choice_id in choice_ids:
            raise ValueError("choice ids must be unique")
        choice_ids.add(choice_id)
        text = _text(c["text"], "choice text", 1_000)
        if text in choice_texts:
            raise ValueError("choice text must be unique")
        choice_texts.add(text)
        if _id(c["atom_id"], "choice atom id") not in atom_ids or not isinstance(c["correct"], bool):
            raise ValueError("invalid choice atom or correctness flag")
        if c["correct"]:
            correct.append(c)
    if len(correct) != 1 or correct[0]["atom_id"] != final_atom:
        raise ValueError("exactly one choice must select the final answer atom")
    if correct[0]["text"] != next(a["value"] for a in atoms if a["id"] == final_atom):
        raise ValueError("correct choice text must equal the final answer atom value")

    if not isinstance(item["receipt"], str) or len(item["receipt"]) != 64:
        raise ValueError("invalid construction receipt")
    expected = receipt({key: value for key, value in item.items() if key != "receipt"})
    if item["receipt"] != expected:
        raise ValueError("construction receipt mismatch")
    return {"status": "PASS", "item_id": item["item_id"], "receipt": item["receipt"]}


def seal_construction(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copied record with its deterministic receipt attached."""
    unsigned = {key: value for key, value in record.items() if key != "receipt"}
    sealed = {**unsigned, "receipt": receipt(unsigned)}
    validate_construction(sealed)
    return sealed
