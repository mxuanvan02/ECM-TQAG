import json
from pathlib import Path
import pytest
from ecm_tqag import validate_answer, validate_package, verify_run
from ecm_tqag.runner import export_dataset, run

ROOT = Path(__file__).parents[1]
PKG = ROOT / "fixtures/packages/example-t.json"

def package():
    return json.loads(PKG.read_text())

def test_strict_unknown_and_condition_invariants():
    p = package(); p["unexpected"] = 1
    with pytest.raises(ValueError): validate_package(p)
    p = package(); p["evidence"]["layout"] = {"nodes": ["a"], "edges": []}
    with pytest.raises(ValueError): validate_package(p)
    p = package(); p["condition"] = "full_pixels"
    with pytest.raises(ValueError): validate_package(p)

def test_answer_validation_rejects_empty_and_unknown_fields():
    a = {"schema":"ecm-tqag.answer.v1", "item_id":"x", "condition":"text_only", "package_sha256":"0" * 64, "answer":"ok", "source":"test"}
    assert validate_answer(a)["item_id"] == "x"
    with pytest.raises(ValueError): validate_answer({**a, "answer":""})
    with pytest.raises(ValueError): validate_answer({**a, "extra":True})

def test_offline_run_and_tamper_detection(tmp_path):
    cfg = tmp_path / "config.json"; output = tmp_path / "summary.json"
    cfg.write_text(json.dumps({"schema":"ecm-tqag.run-config.v1", "name":"test", "packages":str(ROOT / "fixtures/packages"), "output":str(output), "mode":"offline"}))
    result = run(cfg)
    assert result["record_count"] == 3
    assert verify_run(output)["status"] == "PASS"
    data = json.loads(output.read_text()); data["records"][0]["answer"] = "tampered"
    output.write_text(json.dumps(data))
    with pytest.raises(ValueError): verify_run(output)

def test_export_dataset_is_deterministic(tmp_path):
    cfg = tmp_path / "config.json"; summary = tmp_path / "summary.json"; dataset = tmp_path / "dataset.jsonl"
    cfg.write_text(json.dumps({"schema":"ecm-tqag.run-config.v1", "name":"export", "packages":str(ROOT / "fixtures/packages"), "output":str(summary), "mode":"offline"}))
    run(cfg)
    result = export_dataset(summary, dataset)
    assert result["status"] == "PASS"
    assert result["record_count"] == 3
    assert dataset.read_text().count("\n") == 3


def test_openai_mode_requires_explicit_credentials(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"schema":"ecm-tqag.run-config.v1", "name":"test", "packages":str(ROOT / "fixtures/packages"), "output":str(tmp_path / "out.json"), "mode":"openai-compatible", "endpoint":"http://127.0.0.1:1/v1/chat/completions", "model":"test", "api_key_env":"ECM_TEST_MISSING"}))
    with pytest.raises(ValueError, match="API key"):
        run(cfg)

def test_sse_multiline_and_done():
    from ecm_tqag import parse_response
    assert parse_response("event: message\ndata: {\"x\":\ndata: 1}\n\ndata: [DONE]\n", "text/event-stream") == [{"x": 1}]
    with pytest.raises(ValueError): parse_response("not sse", "text/event-stream")

def test_verify_run_recomputes_config_and_packages(tmp_path):
    cfg = tmp_path / "config.json"; out = tmp_path / "summary.json"
    cfg.write_text(json.dumps({"schema":"ecm-tqag.run-config.v1", "name":"verify", "packages":str(ROOT / "fixtures/packages"), "output":str(out), "mode":"offline", "conditions":["text_only"]}))
    run(cfg)
    assert verify_run(out, cfg)["status"] == "PASS"
    changed = json.loads(cfg.read_text()); changed["name"] = "changed"; cfg.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="config receipt"):
        verify_run(out, cfg)

def test_recursive_directory_validation(tmp_path):
    nested = tmp_path / "nested"; nested.mkdir()
    nested.joinpath("package.json").write_text(PKG.read_text())
    from ecm_tqag import validate_directory
    assert validate_directory(tmp_path)["packages"][0]["path"] == "nested/package.json"
