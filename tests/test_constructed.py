import json
from pathlib import Path

import pytest

from ecm_tqag import validate_constructed_directory, validate_constructed_item
from ecm_tqag.cli import main

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "constructed-items"


def item():
    return json.loads((FIXTURES / "synthetic-rights-cleared-001.json").read_text())


def test_public_constructed_item_validates():
    report = validate_constructed_directory(FIXTURES)
    assert report["status"] == "PASS"
    assert report["constructed_item_count"] == 1
    assert report["items"][0]["item_id"] == "synthetic-rights-cleared-001"


def test_constructed_item_enforces_answer_and_trace_contract():
    record = item()
    assert validate_constructed_item(record)["item_id"] == record["item_id"]

    record = item()
    record["answer"] = "Four"
    with pytest.raises(ValueError, match="indexed choice"):
        validate_constructed_item(record)

    record = item()
    record["provenance_trace"] = []
    with pytest.raises(ValueError, match="one record per answer atom"):
        validate_constructed_item(record)

    record = item()
    record["choices"][3] = record["choices"][2]
    with pytest.raises(ValueError, match="choices must be unique"):
        validate_constructed_item(record)


def test_validate_items_cli(capsys):
    assert main(["validate-items", str(FIXTURES)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["constructed_item_count"] == 1
