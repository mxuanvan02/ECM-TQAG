"""Strict, dependency-free contracts for ECM-TQAG experiment data."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any

SCHEMA = "ecm-tqag.condition-package.v1"
ANSWER_SCHEMA = "ecm-tqag.answer.v1"
CONDITIONS = ("text_only", "text_layout", "full_pixels")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def receipt(obj: Any) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _object(value: Any, required: set[str], allowed: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        raise ValueError(f"{name} missing: {sorted(missing)}")
    if extra:
        raise ValueError(f"{name} unknown fields: {sorted(extra)}")
    return value


def _string(value: Any, name: str, *, max_len: int = 10000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValueError(f"{name} must be a non-empty string of at most {max_len} characters")
    return value


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("invalid PNG")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height:
        raise ValueError("PNG dimensions must be positive")
    return width, height


def decode_pixels(asset: dict) -> bytes:
    fields = {"encoding", "media_type", "data", "byte_length", "sha256", "dimensions", "provenance"}
    _object(asset, fields, fields, "pixel_asset")
    if asset["encoding"] != "base64" or asset["media_type"] != "image/png":
        raise ValueError("pixel_asset must be a base64-encoded PNG")
    if not isinstance(asset["data"], str) or len(asset["data"]) % 4:
        raise ValueError("invalid base64 pixel data")
    try:
        data = base64.b64decode(asset["data"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid pixel data") from exc
    width, height = _png_dimensions(data)
    if not isinstance(asset["byte_length"], int) or isinstance(asset["byte_length"], bool):
        raise ValueError("pixel byte_length must be an integer")
    if asset["byte_length"] != len(data):
        raise ValueError("pixel byte length mismatch")
    if not isinstance(asset["sha256"], str) or not _SHA256.fullmatch(asset["sha256"]):
        raise ValueError("invalid pixel SHA-256")
    if asset["sha256"] != hashlib.sha256(data).hexdigest():
        raise ValueError("pixel SHA-256 mismatch")
    if asset["dimensions"] != {"width": width, "height": height}:
        raise ValueError("pixel dimension mismatch")
    _string(asset["provenance"], "pixel_asset.provenance", max_len=500)
    return data


def _reject_unsafe_values(value: Any) -> None:
    raw = json.dumps(value, ensure_ascii=False).lower()
    markers = ("/" + "home/", "/users/", "file://", "bearer ", "api_key", "api-key", "sk-")
    if any(marker in raw for marker in markers) or re.search(r"[a-z]:\\", raw):
        raise ValueError("unsafe path or credential-shaped value")


def validate_package(package: dict) -> dict:
    p = _object(
        package,
        {"schema", "item_id", "condition", "question", "evidence"},
        {"schema", "item_id", "condition", "question", "evidence", "pixel_asset"},
        "package",
    )
    if p["schema"] != SCHEMA:
        raise ValueError("wrong package schema")
    if not isinstance(p["item_id"], str) or not _SAFE_ID.fullmatch(p["item_id"]):
        raise ValueError("invalid item_id")
    condition = p["condition"]
    if condition not in CONDITIONS:
        raise ValueError("unknown condition")
    _string(p["question"], "question", max_len=2000)
    evidence = _object(p["evidence"], {"text"}, {"text", "layout"}, "evidence")
    _string(evidence["text"], "evidence.text")
    if condition == "text_only" and "layout" in evidence:
        raise ValueError("text_only cannot contain layout")
    if condition in {"text_layout", "full_pixels"}:
        layout = _object(evidence.get("layout"), {"nodes", "edges"}, {"nodes", "edges"}, "evidence.layout")
        nodes = layout["nodes"]
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("layout.nodes must be a non-empty array")
        if all(isinstance(x, str) and x for x in nodes):  # legacy public package
            node_ids = nodes
            edges = layout["edges"]
            if not isinstance(edges, list) or any(not isinstance(x, list) or len(x) != 2 or any(y not in node_ids for y in x) for x in edges):
                raise ValueError("invalid legacy layout.edges")
        else:
            node_ids = []
            for node in nodes:
                n = _object(node, {"id", "label", "value"}, {"id", "label", "value"}, "layout node")
                node_ids.append(_string(n["id"], "layout node id", max_len=128))
                _string(n["label"], "layout node label", max_len=500)
                _string(n["value"], "layout node value")
            edges = layout["edges"]
            for edge in edges if isinstance(edges, list) else [None]:
                e = _object(edge, {"id", "type", "source", "target", "relation", "directed"}, {"id", "type", "source", "target", "relation", "directed"}, "layout edge")
                if e["type"] != "layout_relation" or e["directed"] is not True or e["source"] not in node_ids or e["target"] not in node_ids:
                    raise ValueError("invalid typed directed layout edge")
                _string(e["id"], "layout edge id", max_len=128)
                _string(e["relation"], "layout edge relation", max_len=128)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("layout node ids must be unique")
    if condition != "full_pixels" and "pixel_asset" in p:
        raise ValueError("pixel asset is not allowed outside full_pixels")
    if condition == "full_pixels":
        decode_pixels(p.get("pixel_asset", {}))
    _reject_unsafe_values(p)
    return {"condition": condition, "item_id": p["item_id"], "package_sha256": receipt(p)}


def validate_answer(answer: dict) -> dict:
    fields = {"schema", "item_id", "condition", "package_sha256", "answer", "source"}
    a = _object(answer, fields, fields, "answer")
    if a["schema"] != ANSWER_SCHEMA or not isinstance(a["item_id"], str) or not _SAFE_ID.fullmatch(a["item_id"]):
        raise ValueError("invalid answer identity")
    if a["condition"] not in CONDITIONS:
        raise ValueError("invalid answer condition")
    if not isinstance(a["package_sha256"], str) or not _SHA256.fullmatch(a["package_sha256"]):
        raise ValueError("invalid package SHA-256 in answer")
    _string(a["answer"], "answer", max_len=20000)
    _string(a["source"], "source", max_len=100)
    _reject_unsafe_values(a)
    return {"item_id": a["item_id"], "condition": a["condition"], "answer_sha256": receipt(a)}


def parse_response(payload: str, content_type: str = "application/json") -> list[dict]:
    if not isinstance(payload, str) or len(payload) > 10_000_000:
        raise ValueError("response must be bounded text")
    if "text/event-stream" in content_type.lower():
        chunks: list[str] = []
        current: list[str] = []
        for line in payload.splitlines():
            if not line.strip():
                if current:
                    chunks.append("\n".join(current)); current = []
            elif line.startswith("data:"):
                current.append(line[5:].lstrip())
            elif line.startswith(":") or line.startswith(("event:", "id:", "retry:")):
                continue
            else:
                raise ValueError("invalid SSE line")
        if current:
            chunks.append("\n".join(current))
        out: list[dict] = []
        for chunk in chunks:
            if chunk == "[DONE]":
                continue
            try:
                value = json.loads(chunk)
            except json.JSONDecodeError as exc:
                raise ValueError("invalid SSE JSON") from exc
            values = value if isinstance(value, list) else [value]
            if any(not isinstance(v, dict) for v in values):
                raise ValueError("response records must be objects")
            out.extend(values)
        return out
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON response") from exc
    values = value if isinstance(value, list) else [value]
    if any(not isinstance(v, dict) for v in values):
        raise ValueError("response records must be objects")
    return values


def validate_directory(path: str | Path) -> dict:
    directory = Path(path)
    if not directory.is_dir():
        raise ValueError(f"not a directory: {directory}")
    reports = []
    identities = set()
    items = sorted(
        (item for item in directory.rglob("*.json") if item.is_file() and not item.is_symlink()),
        key=lambda item: item.relative_to(directory).as_posix(),
    )
    for item in items:
        try:
            report = validate_package(json.loads(item.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{item.name}: {exc}") from exc
        identity = (report["item_id"], report["condition"])
        if identity in identities:
            raise ValueError(f"duplicate package identity: {identity}")
        identities.add(identity)
        reports.append({"path": item.relative_to(directory).as_posix(), **report})
    if not reports:
        raise ValueError("no package JSON files")
    return {"status": "PASS", "package_count": len(reports), "packages": reports}
