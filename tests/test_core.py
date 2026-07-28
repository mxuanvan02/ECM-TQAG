import json
from pathlib import Path
import pytest
from ecm_tqag import parse_response, validate_directory, validate_package

FIXTURES = Path(__file__).parents[1] / "fixtures" / "packages"

def test_all_public_conditions_validate():
    result = validate_directory(FIXTURES)
    assert result["package_count"] == 3
    assert {p["condition"] for p in result["packages"]} == {"text_only", "text_layout", "full_pixels"}

def test_sse_and_json_parsing():
    assert parse_response('{"ok": true}')[0]["ok"] is True
    assert parse_response('data: {"n": 1}\n\ndata: [DONE]\n', "text/event-stream") == [{"n": 1}]

def test_rejects_path_and_wrong_schema():
    package = json.loads((FIXTURES / "example-t.json").read_text())
    package["source_path"] = "relative/private/file"
    with pytest.raises(ValueError): validate_package(package)
    package.pop("source_path")
    package["schema"] = "wrong"
    with pytest.raises(ValueError): validate_package(package)
