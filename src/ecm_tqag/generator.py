"""Deterministic normalized-document to traceable multimodal TQA generation."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

from .core import SCHEMA, canonical_bytes, decode_pixels, receipt, validate_package

DOCUMENT_SCHEMA = "ecm-tqag.normalized-document.v2"
OUTPUT_SCHEMA = "ecm-tqag.generated-tqa.v2"
MANIFEST_SCHEMA = "ecm-tqag.generation-manifest.v1"
OPERATIONS = {"layout_relation_value", "dominant_rgb"}
CONDITIONS = ("text_only", "text_layout", "full_pixels")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_NODE_TYPES = {"text", "layout", "visual"}
_EDGE_TYPES = {"layout_relation", "visual_attachment"}


def _object(value: Any, required: set[str], allowed: set[str], name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    missing, extra = required - value.keys(), value.keys() - allowed
    if missing:
        raise ValueError(f"{name} missing: {sorted(missing)}")
    if extra:
        raise ValueError(f"{name} unknown fields: {sorted(extra)}")
    return value


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValueError(f"invalid {name}")
    return value


def _text(value: Any, name: str, limit: int = 10000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be non-empty text of at most {limit} characters")
    return value


def _asset(asset: Any, name: str = "asset") -> dict:
    if not isinstance(asset, dict):
        raise ValueError(f"{name} must be a pixel asset")
    decode_pixels(asset)
    return asset


def validate_document(doc: Any) -> dict:
    fields = {"schema", "document_id", "nodes", "edges", "motifs"}
    d = _object(doc, fields, fields, "document")
    if d["schema"] != DOCUMENT_SCHEMA:
        raise ValueError("wrong normalized document schema")
    _safe_id(d["document_id"], "document_id")
    if not isinstance(d["nodes"], list) or not d["nodes"]:
        raise ValueError("nodes must be a non-empty array")
    nodes: dict[str, dict] = {}
    for index, node in enumerate(d["nodes"]):
        n = _object(node, {"id", "type", "label", "value"}, {"id", "type", "label", "value"}, f"nodes[{index}]")
        node_id = _safe_id(n["id"], "node id")
        if node_id in nodes:
            raise ValueError(f"duplicate node id: {node_id}")
        if n["type"] not in _NODE_TYPES:
            raise ValueError(f"invalid node type: {n['type']}")
        _text(n["label"], "node label", 500)
        if n["type"] == "visual":
            _asset(n["value"], f"visual node {node_id}.value")
        else:
            _text(n["value"], "node value")
        nodes[node_id] = n
    if not any(n["type"] == "text" for n in nodes.values()):
        raise ValueError("document requires at least one text node")
    if not isinstance(d["edges"], list):
        raise ValueError("edges must be an array")
    edges: dict[str, dict] = {}
    for index, edge in enumerate(d["edges"]):
        e = _object(edge, {"id", "type", "source", "target", "relation", "directed"},
                    {"id", "type", "source", "target", "relation", "directed"}, f"edges[{index}]")
        edge_id = _safe_id(e["id"], "edge id")
        if edge_id in edges:
            raise ValueError(f"duplicate edge id: {edge_id}")
        if e["type"] not in _EDGE_TYPES or e["directed"] is not True:
            raise ValueError("edges require a supported type and directed=true")
        if e["source"] not in nodes or e["target"] not in nodes or e["source"] == e["target"]:
            raise ValueError(f"edge {edge_id} has invalid endpoints")
        _safe_id(e["relation"], "edge relation")
        if e["type"] == "layout_relation" and (nodes[e["source"]]["type"] != "layout" or nodes[e["target"]]["type"] != "layout"):
            raise ValueError("layout_relation endpoints must be layout nodes")
        if e["type"] == "visual_attachment" and nodes[e["target"]]["type"] != "visual":
            raise ValueError("visual_attachment target must be visual")
        edges[edge_id] = e
    if not isinstance(d["motifs"], list) or not d["motifs"]:
        raise ValueError("document must contain at least one motif")
    motif_ids: set[str] = set()
    for index, motif in enumerate(d["motifs"]):
        m = _object(motif, {"id", "operation", "target", "relation", "prompt_label", "color_map"},
                    {"id", "operation", "target", "relation", "prompt_label", "color_map"}, f"motifs[{index}]")
        motif_id = _safe_id(m["id"], "motif id")
        if motif_id in motif_ids:
            raise ValueError(f"duplicate motif id: {motif_id}")
        motif_ids.add(motif_id)
        if m["operation"] not in OPERATIONS or m["target"] not in nodes:
            raise ValueError(f"invalid motif {motif_id}")
        _text(m["prompt_label"], "prompt_label", 500)
        if m["operation"] == "layout_relation_value":
            if nodes[m["target"]]["type"] != "layout" or not isinstance(m["relation"], str) or not m["relation"]:
                raise ValueError("layout motif requires layout target and relation")
            if m["color_map"] is not None:
                raise ValueError("layout motif color_map must be null")
            matches = [e for e in edges.values() if e["type"] == "layout_relation" and e["source"] == m["target"] and e["relation"] == m["relation"]]
            if len(matches) != 1:
                raise ValueError("layout motif must select exactly one directed typed edge")
        else:
            if nodes[m["target"]]["type"] != "visual" or m["relation"] is not None:
                raise ValueError("dominant_rgb motif requires visual target and null relation")
            cmap = m["color_map"]
            if not isinstance(cmap, dict) or not cmap:
                raise ValueError("dominant_rgb requires a color_map")
            for rgb, label in cmap.items():
                if not isinstance(rgb, str) or not re.fullmatch(r"#[0-9A-F]{6}", rgb):
                    raise ValueError("color_map keys must be uppercase #RRGGBB")
                _text(label, "color label", 100)
    return d


def load_document(path: str | Path) -> dict:
    return validate_document(json.loads(Path(path).read_text(encoding="utf-8")))


def _png_rgb(asset: dict) -> list[tuple[int, int, int]]:
    """Decode bounded, non-interlaced 8-bit RGB/RGBA PNG pixels."""
    data = decode_pixels(asset)
    width, height = struct.unpack(">II", data[16:24])
    if width * height > 1_000_000:
        raise ValueError("PNG is too large for the minimal decoder")
    pos, color_type, bit_depth, interlace, payload = 8, None, None, None, bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, chunk = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        if pos + 12 + length > len(data):
            raise ValueError("truncated PNG")
        if kind == b"IHDR":
            _, _, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk)
            if compression or filtering:
                raise ValueError("unsupported PNG encoding")
        elif kind == b"IDAT":
            payload.extend(chunk)
        pos += length + 12
    if bit_depth != 8 or color_type not in (2, 6) or interlace != 0:
        raise ValueError("dominant_rgb supports non-interlaced 8-bit RGB/RGBA PNGs")
    bpp = 3 if color_type == 2 else 4
    try:
        raw = zlib.decompress(bytes(payload))
    except zlib.error as exc:
        raise ValueError("invalid PNG compressed pixels") from exc
    stride = width * bpp
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG scanline size mismatch")
    previous = bytearray(stride); pixels: list[tuple[int, int, int]] = []; offset = 0
    for _ in range(height):
        method, scan = raw[offset], bytearray(raw[offset + 1:offset + 1 + stride]); offset += stride + 1
        for i in range(stride):
            left = scan[i - bpp] if i >= bpp else 0
            up = previous[i]
            upper_left = previous[i - bpp] if i >= bpp else 0
            if method == 1:
                scan[i] = (scan[i] + left) & 255
            elif method == 2:
                scan[i] = (scan[i] + up) & 255
            elif method == 3:
                scan[i] = (scan[i] + ((left + up) // 2)) & 255
            elif method == 4:
                p = left + up - upper_left; pa, pb, pc = abs(p-left), abs(p-up), abs(p-upper_left)
                scan[i] = (scan[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else upper_left)) & 255
            elif method != 0:
                raise ValueError("unsupported PNG filter")
        pixels.extend((scan[i], scan[i + 1], scan[i + 2]) for i in range(0, stride, bpp))
        previous = scan
    return pixels


def _compute(doc: dict, motif: dict) -> tuple[str, list[dict]]:
    nodes = {n["id"]: n for n in doc["nodes"]}
    if motif["operation"] == "layout_relation_value":
        edge = next(e for e in doc["edges"] if e["type"] == "layout_relation" and e["source"] == motif["target"] and e["relation"] == motif["relation"])
        target = nodes[edge["target"]]
        answer = target["value"]
        steps = [
            {"step_id": "s1", "operation": "select_typed_directed_edge", "inputs": {"source_node_id": motif["target"], "edge_type": "layout_relation", "relation": motif["relation"]}, "output": {"edge_id": edge["id"], "target_node_id": target["id"]}},
            {"step_id": "s2", "operation": "read_node_value", "inputs": {"node_id": target["id"], "field": "value"}, "output": {"answer": answer}},
        ]
    else:
        node = nodes[motif["target"]]; pixels = _png_rgb(node["value"]); counts = Counter(pixels)
        dominant, count = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[0]
        key = "#" + "".join(f"{v:02X}" for v in dominant)
        if key not in motif["color_map"]:
            raise ValueError(f"dominant color {key} is not in motif color_map")
        answer = motif["color_map"][key]
        steps = [
            {"step_id": "s1", "operation": "decode_png_rgb_pixels", "inputs": {"node_id": node["id"], "asset_sha256": node["value"]["sha256"]}, "output": {"pixel_count": len(pixels)}},
            {"step_id": "s2", "operation": "count_exact_rgb", "inputs": {"tie_break": "lexicographically_smallest_rgb"}, "output": {"rgb": key, "count": count}},
            {"step_id": "s3", "operation": "map_rgb_to_label", "inputs": {"rgb": key}, "output": {"answer": answer}},
        ]
    return answer, steps


def _question(motif: dict) -> str:
    if motif["operation"] == "layout_relation_value":
        return f"What value is {motif['relation'].replace('_', ' ')} {motif['prompt_label']}?"
    return f"What is the dominant exact RGB color of {motif['prompt_label']}?"


def _contains_answer(answer: str, text: str) -> bool:
    """Match an answer as a normalized token sequence, not as a substring."""
    answer_tokens = re.findall(r"\w+", answer.casefold())
    text_tokens = re.findall(r"\w+", text.casefold())
    return bool(answer_tokens) and any(text_tokens[i:i + len(answer_tokens)] == answer_tokens for i in range(len(text_tokens) - len(answer_tokens) + 1))


def _evidence(doc: dict) -> tuple[str, dict]:
    texts = sorted((n for n in doc["nodes"] if n["type"] == "text"), key=lambda n: n["id"])
    text = "\n".join(f"{n['label']}: {n['value']}" for n in texts)
    layout_nodes = sorted((n for n in doc["nodes"] if n["type"] == "layout"), key=lambda n: n["id"])
    layout_edges = sorted((e for e in doc["edges"] if e["type"] == "layout_relation"), key=lambda e: e["id"])
    layout = {
        "nodes": [{"id": n["id"], "label": n["label"], "value": n["value"]} for n in layout_nodes],
        "edges": [{"id": e["id"], "type": e["type"], "source": e["source"], "target": e["target"], "relation": e["relation"], "directed": True} for e in layout_edges],
    }
    return text, layout


def validate_triplet(packages: list[dict], expected_hashes: dict[str, str] | None = None) -> dict:
    if not isinstance(packages, list) or len(packages) != 3:
        raise ValueError("triplet must contain exactly three packages")
    by_condition: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    for package in packages:
        report = validate_package(package)
        condition = report["condition"]
        if condition in by_condition:
            raise ValueError(f"duplicate triplet condition: {condition}")
        by_condition[condition], hashes[condition] = package, report["package_sha256"]
    if set(by_condition) != set(CONDITIONS):
        raise ValueError("triplet condition set must be text_only, text_layout, full_pixels")
    values = list(by_condition.values())
    if len({p["item_id"] for p in values}) != 1 or len({p["question"] for p in values}) != 1:
        raise ValueError("triplet item_id and question must match exactly")
    if len({p["evidence"]["text"] for p in values}) != 1:
        raise ValueError("triplet text evidence must match exactly")
    if by_condition["text_layout"]["evidence"]["layout"] != by_condition["full_pixels"]["evidence"]["layout"]:
        raise ValueError("TL layout must exactly match TLV layout")
    if expected_hashes is not None:
        if not isinstance(expected_hashes, dict) or set(expected_hashes) != set(CONDITIONS):
            raise ValueError("expected package hashes must contain exactly the three conditions")
        if any(not isinstance(value, str) or not _SHA256.fullmatch(value) for value in expected_hashes.values()):
            raise ValueError("invalid expected package hash")
        if hashes != expected_hashes:
            raise ValueError("triplet package hashes do not match manifest")
    return {"status": "PASS", "item_id": values[0]["item_id"], "package_hashes": hashes}


def _validate_record(record: Any) -> dict:
    fields = {"schema", "item_id", "source", "program", "answer", "answer_frozen_before_question",
              "question", "provenance_steps", "package_hashes", "receipt"}
    r = _object(record, fields, fields, "generated TQA")
    if r["schema"] != OUTPUT_SCHEMA:
        raise ValueError("wrong generated TQA schema")
    _safe_id(r["item_id"], "generated TQA item_id")
    source = _object(r["source"], {"document_id", "sha256"}, {"document_id", "sha256"}, "generated TQA source")
    _safe_id(source["document_id"], "generated TQA document_id")
    if not isinstance(source["sha256"], str) or not _SHA256.fullmatch(source["sha256"]):
        raise ValueError("invalid generated TQA source digest")
    program = _object(r["program"], {"motif_id", "operation", "target_node_id", "relation", "color_map"},
                      {"motif_id", "operation", "target_node_id", "relation", "color_map"}, "generated TQA program")
    _safe_id(program["motif_id"], "program motif_id")
    _safe_id(program["target_node_id"], "program target_node_id")
    if program["operation"] not in OPERATIONS:
        raise ValueError("invalid generated TQA operation")
    if program["relation"] is not None:
        _safe_id(program["relation"], "program relation")
    if program["color_map"] is not None:
        if not isinstance(program["color_map"], dict) or not program["color_map"]:
            raise ValueError("invalid program color_map")
        for rgb, label in program["color_map"].items():
            if not isinstance(rgb, str) or not re.fullmatch(r"#[0-9A-F]{6}", rgb):
                raise ValueError("invalid program RGB")
            _text(label, "program color label", 100)
    _text(r["answer"], "generated answer")
    _text(r["question"], "generated question", 2000)
    if r["answer_frozen_before_question"] is not True:
        raise ValueError("answer must be frozen before question realization")
    if not isinstance(r["provenance_steps"], list) or len(r["provenance_steps"]) < 2:
        raise ValueError("provenance_steps must contain at least two steps")
    for index, step in enumerate(r["provenance_steps"]):
        s = _object(step, {"step_id", "operation", "inputs", "output"}, {"step_id", "operation", "inputs", "output"}, f"provenance_steps[{index}]")
        _safe_id(s["step_id"], "provenance step_id")
        _text(s["operation"], "provenance operation", 200)
        if not isinstance(s["inputs"], dict) or not isinstance(s["output"], dict):
            raise ValueError("provenance inputs and output must be objects")
    hashes = r["package_hashes"]
    if not isinstance(hashes, dict) or set(hashes) != set(CONDITIONS) or any(not isinstance(v, str) or not _SHA256.fullmatch(v) for v in hashes.values()):
        raise ValueError("generated TQA package_hashes must contain exactly three SHA-256 values")
    if not isinstance(r["receipt"], str) or not _SHA256.fullmatch(r["receipt"]):
        raise ValueError("invalid generated TQA receipt")
    if receipt({k: v for k, v in r.items() if k != "receipt"}) != r["receipt"]:
        raise ValueError("generated TQA receipt mismatch")
    return r


def _item(doc: dict, motif: dict, source_sha256: str) -> tuple[dict, list[dict]]:
    # Freeze the answer and its complete replay trace before question realization.
    answer, steps = _compute(doc, motif)
    frozen = canonical_bytes({"answer": answer, "steps": steps})
    question = _question(motif)
    if _contains_answer(answer, question):
        raise ValueError("answer leakage into generated question")
    if frozen != canonical_bytes({"answer": answer, "steps": steps}):
        raise RuntimeError("answer changed during question realization")
    text, layout = _evidence(doc)
    if _contains_answer(answer, text):
        raise ValueError("modality-dependent answer leaks into text-only evidence")
    item_id = f"{doc['document_id']}-{motif['id']}"
    visual_nodes = {n["id"]: n for n in doc["nodes"] if n["type"] == "visual"}
    if motif["operation"] == "dominant_rgb":
        pixel_asset = visual_nodes[motif["target"]]["value"]
    else:
        attached = [e for e in doc["edges"] if e["type"] == "visual_attachment"]
        if not attached:
            raise ValueError("all condition triplets require a visual_attachment asset")
        pixel_asset = visual_nodes[attached[0]["target"]]["value"]
    packages: list[dict] = []
    for condition in CONDITIONS:
        evidence: dict[str, Any] = {"text": text}
        if condition != "text_only":
            evidence["layout"] = layout
        package: dict[str, Any] = {"schema": SCHEMA, "item_id": item_id, "condition": condition, "question": question, "evidence": evidence}
        if condition == "full_pixels":
            package["pixel_asset"] = pixel_asset
        validate_package(package); packages.append(package)
    triplet = validate_triplet(packages)
    record = {
        "schema": OUTPUT_SCHEMA,
        "item_id": item_id,
        "source": {"document_id": doc["document_id"], "sha256": source_sha256},
        "program": {"motif_id": motif["id"], "operation": motif["operation"], "target_node_id": motif["target"], "relation": motif["relation"], "color_map": motif["color_map"]},
        "answer": answer,
        "answer_frozen_before_question": True,
        "question": question,
        "provenance_steps": steps,
        "package_hashes": triplet["package_hashes"],
    }
    record["receipt"] = receipt(record)
    return record, packages


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def generate(input_path: str | Path, output_dir: str | Path, *, replace: bool = False) -> dict:
    input_file, destination = Path(input_path), Path(output_dir)
    doc = load_document(input_file)
    source_sha256 = hashlib.sha256(input_file.read_bytes()).hexdigest()
    if destination.exists() and any(destination.iterdir()):
        if not replace:
            raise ValueError("output destination is nonempty; pass replace=True to replace it atomically")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    backup: Path | None = None
    try:
        manifest_items = []
        for motif in doc["motifs"]:
            record, packages = _item(doc, motif, source_sha256)
            base = Path("items") / record["item_id"]
            package_entries = []
            for package in packages:
                rel = base / "packages" / f"{package['condition']}.json"
                _write_json(stage / rel, package)
                package_entries.append({"condition": package["condition"], "path": rel.as_posix(), "sha256": receipt(package)})
            tqa_rel = base / "tqa.json"; _write_json(stage / tqa_rel, record)
            manifest_items.append({"item_id": record["item_id"], "motif_id": record["program"]["motif_id"], "tqa_path": tqa_rel.as_posix(), "tqa_receipt": record["receipt"], "packages": package_entries})
        manifest = {"schema": MANIFEST_SCHEMA, "source": {"document_id": doc["document_id"], "sha256": source_sha256}, "items": manifest_items}
        manifest["receipt"] = receipt(manifest)
        _write_json(stage / "manifest.json", manifest)
        validate_generated(stage, input_file)
        if destination.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.backup-", dir=destination.parent))
            backup.rmdir()
            destination.rename(backup)
        try:
            stage.rename(destination)
        except Exception:
            if backup is not None and backup.exists() and not destination.exists(): backup.rename(destination)
            raise
        if backup is not None: shutil.rmtree(backup)
        return {"status": "PASS", "output": destination.name, "manifest": "manifest.json", "item_count": len(manifest_items), "receipt": manifest["receipt"]}
    except Exception:
        if backup is not None and backup.exists() and not destination.exists(): backup.rename(destination)
        shutil.rmtree(stage, ignore_errors=True)
        raise


def validate_generated(output_dir: str | Path, source_path: str | Path | None = None) -> dict:
    root = Path(output_dir)
    if not root.is_dir() or root.is_symlink(): raise ValueError("generated output must be a real directory")
    if any(path.is_symlink() for path in root.rglob("*")): raise ValueError("generated output may not contain symlinks")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    _object(manifest, {"schema", "source", "items", "receipt"}, {"schema", "source", "items", "receipt"}, "manifest")
    if manifest["schema"] != MANIFEST_SCHEMA or receipt({k: v for k, v in manifest.items() if k != "receipt"}) != manifest["receipt"]:
        raise ValueError("invalid manifest schema or receipt")
    source = _object(manifest["source"], {"document_id", "sha256"}, {"document_id", "sha256"}, "manifest.source")
    _safe_id(source["document_id"], "manifest document_id")
    if not isinstance(source["sha256"], str) or not _SHA256.fullmatch(source["sha256"]): raise ValueError("invalid source digest")
    if not isinstance(manifest["items"], list) or not manifest["items"]: raise ValueError("manifest items must be nonempty")
    doc = None
    if source_path is not None:
        source_file = Path(source_path)
        if hashlib.sha256(source_file.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("source document digest mismatch")
        doc = load_document(source_file)
        if doc["document_id"] != source["document_id"]: raise ValueError("source document identity mismatch")
    seen: set[str] = set()
    seen_motifs: set[str] = set()
    used_paths: set[str] = {"manifest.json"}
    for entry in manifest["items"]:
        _object(entry, {"item_id", "motif_id", "tqa_path", "tqa_receipt", "packages"}, {"item_id", "motif_id", "tqa_path", "tqa_receipt", "packages"}, "manifest item")
        _safe_id(entry["item_id"], "manifest item_id"); _safe_id(entry["motif_id"], "manifest motif_id")
        if entry["item_id"] in seen: raise ValueError("duplicate manifest item")
        seen.add(entry["item_id"])
        if entry["motif_id"] in seen_motifs: raise ValueError("duplicate manifest motif")
        seen_motifs.add(entry["motif_id"])
        if not isinstance(entry["packages"], list) or len(entry["packages"]) != 3: raise ValueError("manifest item must contain exactly three package entries")
        paths = [entry["tqa_path"]] + [p.get("path") if isinstance(p, dict) else None for p in entry["packages"]]
        if any(not isinstance(p, str) or not p for p in paths): raise ValueError("invalid manifest path")
        if any(Path(p).is_absolute() or ".." in Path(p).parts for p in paths): raise ValueError("manifest paths must be portable relative paths")
        if used_paths.intersection(paths) or len(paths) != len(set(paths)): raise ValueError("manifest paths must be unique")
        used_paths.update(paths)
        record = json.loads((root / entry["tqa_path"]).read_text(encoding="utf-8"))
        _validate_record(record)
        if record["receipt"] != entry["tqa_receipt"]: raise ValueError("generated TQA receipt does not match manifest")
        if record["item_id"] != entry["item_id"] or record["program"]["motif_id"] != entry["motif_id"]: raise ValueError("generated TQA identity mismatch")
        if record["source"] != source: raise ValueError("generated TQA source mismatch")
        package_by_condition, expected = [], {}
        for p in entry["packages"]:
            _object(p, {"condition", "path", "sha256"}, {"condition", "path", "sha256"}, "manifest package")
            if p["condition"] not in CONDITIONS or p["condition"] in expected: raise ValueError("invalid or duplicate manifest package condition")
            if not isinstance(p["sha256"], str) or not _SHA256.fullmatch(p["sha256"]): raise ValueError("invalid manifest package hash")
            package = json.loads((root / p["path"]).read_text(encoding="utf-8")); package_by_condition.append(package); expected[p["condition"]] = p["sha256"]
            if package.get("condition") != p["condition"]: raise ValueError("manifest/package condition mismatch")
        validate_triplet(package_by_condition, expected)
        if record["package_hashes"] != expected: raise ValueError("TQA package hashes mismatch")
        if any(p["item_id"] != record["item_id"] or p["question"] != record["question"] for p in package_by_condition): raise ValueError("TQA/package identity mismatch")
        if doc is not None:
            motif = next((m for m in doc["motifs"] if m["id"] == entry["motif_id"]), None)
            if motif is None: raise ValueError("manifest motif absent from source")
            answer, steps = _compute(doc, motif)
            if answer != record["answer"] or steps != record["provenance_steps"]:
                raise ValueError("provenance replay mismatch")
    if doc is not None and seen_motifs != {m["id"] for m in doc["motifs"]}: raise ValueError("manifest does not cover source motifs exactly")
    expected_files = {"manifest.json"} | {p for e in manifest["items"] for p in [e["tqa_path"], *(x["path"] for x in e["packages"])]}
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.is_symlink()}
    if actual_files != expected_files: raise ValueError("output contains missing or stale files")
    return {"status": "PASS", "item_count": len(seen), "receipt": manifest["receipt"]}


def replay_provenance(source_path: str | Path, output_dir: str | Path) -> dict:
    return validate_generated(output_dir, source_path)
