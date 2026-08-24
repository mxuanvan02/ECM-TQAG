import json
from pathlib import Path

import pytest

from ecm_tqag.cli import main


def test_validate_cli(capsys):
    assert main(["validate", "fixtures/packages"]) == 0
    assert json.loads(capsys.readouterr().out)["package_count"] == 3


def test_contract_eval_and_verify_cli(tmp_path, capsys):
    root = Path(__file__).parents[1]
    output = tmp_path / "contract-report.json"
    assert main([
        "contract-eval",
        str(output),
        str(root / "fixtures/documents/layout.json"),
        str(root / "fixtures/documents/pixel.json"),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PASS_STRUCTURAL_ONLY"
    assert output.is_file()

    assert main(["verify-contract-eval", str(output)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["status"] == "SELF_CONSISTENCY_ONLY"
    assert verified["document_count"] == 2
    assert verified["item_count"] == 2

    assert main([
        "verify-contract-eval", str(output), "--source",
        str(root / "fixtures/documents/layout.json"),
        str(root / "fixtures/documents/pixel.json"),
    ]) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["status"] == "PASS_REPLAY_VERIFIED"


def test_real_inventory_cli(capsys):
    inventory = Path(__file__).parents[2] / "conference_eval/inventory_v1.json"
    if not inventory.is_file():
        pytest.skip(
            "requires the private rights inventory at "
            f"{inventory} (not distributed with this repository)"
        )
    assert main(["validate-real-inventory", str(inventory)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED"
    assert result["blocked_count"] == 35
