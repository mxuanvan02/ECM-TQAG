import json
from ecm_tqag.cli import main

def test_validate_cli(capsys):
    assert main(["validate", "fixtures/packages"]) == 0
    assert json.loads(capsys.readouterr().out)["package_count"] == 3
