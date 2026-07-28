"""Offline transport checks and OpenAI-compatible experiment execution."""
from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .core import CONDITIONS, ANSWER_SCHEMA, canonical_bytes, receipt, validate_answer, validate_directory, validate_package

CONFIG_SCHEMA = "ecm-tqag.run-config.v1"
SUMMARY_SCHEMA = "ecm-tqag.run-summary.v1"
MAX_PROVIDER_RESPONSE_BYTES = 10 * 1024 * 1024


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_config(path: str | Path) -> tuple[dict, Path]:
    config_path = Path(path).resolve()
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = {"schema", "name", "packages", "output", "mode", "endpoint", "model", "api_key_env", "conditions", "timeout_seconds"}
    if not isinstance(cfg, dict) or cfg.get("schema") != CONFIG_SCHEMA or set(cfg) - allowed:
        raise ValueError("invalid run config")
    for field in ("name", "packages", "output", "mode"):
        if not isinstance(cfg.get(field), str) or not cfg[field].strip():
            raise ValueError(f"invalid run config field: {field}")
    if cfg["mode"] not in {"offline", "openai-compatible"}:
        raise ValueError("mode must be offline or openai-compatible")
    conditions = cfg.get("conditions", list(CONDITIONS))
    if not isinstance(conditions, list) or not conditions or len(conditions) != len(set(conditions)) or any(c not in CONDITIONS for c in conditions):
        raise ValueError("conditions must be a non-empty unique subset of known conditions")
    cfg["conditions"] = conditions
    timeout = cfg.get("timeout_seconds", 60)
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 600:
        raise ValueError("timeout_seconds must be an integer from 1 to 600")
    cfg["timeout_seconds"] = timeout
    if cfg["mode"] == "openai-compatible":
        for field in ("endpoint", "model", "api_key_env"):
            if not isinstance(cfg.get(field), str) or not cfg[field].strip():
                raise ValueError(f"openai-compatible mode requires {field}")
        if not cfg["endpoint"].startswith(("http://", "https://")):
            raise ValueError("endpoint must be an HTTP(S) URL")
    return cfg, config_path.parent


def config_hash(cfg: dict) -> str:
    # Hash the variable name, never the secret it names.
    return receipt(cfg)


def _content(package: dict) -> list[dict]:
    evidence = package["evidence"]
    text = (
        "Question:\n"
        + package["question"]
        + "\n\nText evidence:\n"
        + evidence["text"]
    )
    if "layout" in evidence:
        text += "\n\nLayout evidence (JSON):\n" + json.dumps(
            evidence["layout"], ensure_ascii=False, sort_keys=True
        )
    blocks: list[dict] = [{"type": "text", "text": text}]
    if package["condition"] == "full_pixels":
        asset = package["pixel_asset"]
        blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{asset['media_type']};base64,{asset['data']}"
                },
            }
        )
    return blocks


def _extract_completion(response: dict) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("provider response lacks choices[0].message.content") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") in {"text", "output_text"}]
        joined = "".join(parts)
        if joined:
            return joined
    raise ValueError("provider response content is not text")


def _answer(package: dict, package_sha256: str, mode: str, cfg: dict) -> dict:
    if mode == "offline":
        answer = "OFFLINE_TRANSPORT_CHECK"
        source = "offline"
    else:
        key = os.environ.get(cfg["api_key_env"])
        if not key:
            raise ValueError(f"missing API key environment variable: {cfg['api_key_env']}")
        body = canonical_bytes({
            "model": cfg["model"],
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Answer the question using only the supplied evidence. Return a concise answer."},
                {"role": "user", "content": _content(package)},
            ],
        })
        request = urllib.request.Request(
            cfg["endpoint"], data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=cfg["timeout_seconds"]) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                    raise ValueError("provider response exceeds 10 MiB limit")
                provider = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(f"provider HTTP error: {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("provider request or response failed") from exc
        answer = _extract_completion(provider)
        source = "openai-compatible"
    record = {
        "schema": ANSWER_SCHEMA,
        "item_id": package["item_id"],
        "condition": package["condition"],
        "package_sha256": package_sha256,
        "answer": answer,
        "source": source,
    }
    validate_answer(record)
    return record


def run(config_path: str | Path) -> dict:
    cfg, base = load_config(config_path)
    package_dir = (base / cfg["packages"]).resolve() if not Path(cfg["packages"]).is_absolute() else Path(cfg["packages"])
    output = (base / cfg["output"]).resolve() if not Path(cfg["output"]).is_absolute() else Path(cfg["output"])
    report = validate_directory(package_dir)
    selected = {c for c in cfg["conditions"]}
    records = []
    for package_report in report["packages"]:
        if package_report["condition"] not in selected:
            continue
        package = json.loads((package_dir / package_report["path"]).read_text(encoding="utf-8"))
        validate_package(package)
        records.append(_answer(package, package_report["package_sha256"], cfg["mode"], cfg))
    if not records:
        raise ValueError("no packages matched configured conditions")
    summary = {
        "schema": SUMMARY_SCHEMA,
        "name": cfg["name"],
        "mode": cfg["mode"],
        "config_sha256": config_hash(cfg),
        "record_count": len(records),
        "records": records,
    }
    summary["summary_sha256"] = receipt(summary)
    _atomic(output, canonical_bytes(summary) + b"\n")
    return summary


def export_dataset(summary_path: str | Path, output_path: str | Path) -> dict:
    """Verify a run summary and export its records as deterministic JSON Lines."""
    verification = verify_run(summary_path)
    summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    rows = b"".join(canonical_bytes(record) + b"\n" for record in summary["records"])
    output = Path(output_path)
    _atomic(output, rows)
    return {
        "status": "PASS",
        "record_count": verification["record_count"],
        "dataset_sha256": receipt(rows.decode("utf-8")),
        "output": str(output),
    }


def verify_run(summary_path: str | Path, config_path: str | Path | None = None,
               package_dir: str | Path | None = None) -> dict:
    obj = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    allowed = {"schema", "name", "mode", "config_sha256", "record_count", "records", "summary_sha256"}
    if not isinstance(obj, dict) or set(obj) != allowed:
        raise ValueError("invalid run summary fields")
    supplied = obj.pop("summary_sha256")
    if obj.get("schema") != SUMMARY_SCHEMA or not isinstance(supplied, str) or supplied != receipt(obj):
        raise ValueError("run receipt mismatch")
    if obj.get("mode") not in {"offline", "openai-compatible"} or not isinstance(obj.get("name"), str):
        raise ValueError("invalid run summary")
    if not isinstance(obj.get("config_sha256"), str) or len(obj["config_sha256"]) != 64:
        raise ValueError("invalid config receipt")
    if obj.get("record_count") != len(obj.get("records", [])):
        raise ValueError("record count mismatch")
    cfg = None
    if config_path is not None:
        cfg, base = load_config(config_path)
        if config_hash(cfg) != obj["config_sha256"]:
            raise ValueError("config receipt mismatch")
        if cfg["name"] != obj["name"] or cfg["mode"] != obj["mode"]:
            raise ValueError("summary identity does not match config")
        if package_dir is None:
            package_dir = (base / cfg["packages"]).resolve() if not Path(cfg["packages"]).is_absolute() else Path(cfg["packages"])
    package_index = None
    if package_dir is not None:
        package_index = {(r["item_id"], r["condition"]): r for r in validate_directory(package_dir)["packages"]}
    identities = []
    for record in obj["records"]:
        validate_answer(record)
        identity = (record["item_id"], record["condition"])
        if cfg is not None and record["condition"] not in cfg["conditions"]:
            raise ValueError("answer condition is not selected by config")
        if package_index is not None:
            package = package_index.get(identity)
            if package is None or package["package_sha256"] != record["package_sha256"]:
                raise ValueError("answer package receipt mismatch")
        identities.append(identity)
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate answer identity")
    if cfg is not None and package_index is not None:
        expected = {(i, c) for i, c in package_index if c in cfg["conditions"]}
        if set(identities) != expected:
            raise ValueError("summary condition membership mismatch")
    return {"status": "PASS", "summary_sha256": supplied, "record_count": obj["record_count"]}
