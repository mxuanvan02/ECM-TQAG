import json
from pathlib import Path

import pytest

from ecm_tqag.core import receipt
from ecm_tqag.conference_eval import (
    run_adjudicated_statistics,
    run_contract_experiment,
    validate_real_data_inventory,
    verify_contract_report,
)

ROOT = Path(__file__).parents[1]
LAYOUT = ROOT / "fixtures/documents/layout.json"
PIXEL = ROOT / "fixtures/documents/pixel.json"


def _linked_artifacts(candidate_ids):
    validation = {
        "schema": "ecm-tqag.real-data-inventory-validation.v1",
        "status": "ELIGIBLE",
        "candidate_count": len(candidate_ids),
        "eligible_count": len(candidate_ids),
        "blocked_count": 0,
        "eligible_candidate_ids": candidate_ids,
        "source_disjoint": True,
        "rights_cleared": True,
        "inventory_sha256": "a" * 64,
    }
    validation["validation_sha256"] = receipt(validation)
    adjudication = {
        "schema": "ecm-tqag.adjudication-manifest.v1",
        "status": "COMPLETED",
        "candidate_ids": candidate_ids,
        "blinded": True,
        "annotator_count": 2,
    }
    adjudication["adjudication_sha256"] = receipt(adjudication)
    return validation, adjudication


def test_contract_experiment_is_deterministic_and_blocks_semantic_claims(tmp_path):
    output = tmp_path / "report.json"
    first = run_contract_experiment([LAYOUT, PIXEL], output)
    first_bytes = output.read_bytes()
    second = run_contract_experiment([LAYOUT, PIXEL], output)

    assert first == second
    assert output.read_bytes() == first_bytes
    assert first["status"] == "PASS_STRUCTURAL_ONLY"
    assert first["scope"] == "synthetic_contract_diagnostic_not_effectiveness_evaluation"
    assert first["document_count"] == 2
    assert first["item_count"] == 2
    assert [row["method"] for row in first["methods"]] == [
        "direct", "answer_first", "ecm_full"
    ]
    assert first["gates"]["gate_1_real_data"]["status"] == "BLOCKED"
    assert first["gates"]["gate_2_comparative"]["status"] == "BLOCKED"
    assert first["gates"]["gate_4_reproducibility"]["status"] == "PASS_STRUCTURAL_ONLY"
    assert first["semantic_metrics"]["status"] == "BLOCKED"
    assert all(value is None for value in first["semantic_metrics"]["metrics"].values())
    assert len(first["input_inventory_sha256"]) == 64
    assert len(first["report_sha256"]) == 64
    assert verify_contract_report(output)["status"] == "SELF_CONSISTENCY_ONLY"
    replayed = verify_contract_report(output, sources=[LAYOUT, PIXEL])
    assert replayed["status"] == "PASS_REPLAY_VERIFIED"


def test_structural_metrics_have_explicit_denominators(tmp_path):
    report = run_contract_experiment([LAYOUT, PIXEL], tmp_path / "report.json")
    rows = {row["method"]: row for row in report["methods"]}

    assert rows["direct"]["execution_status"] == "EXECUTED_SYNTHETIC_CONTRACT_ONLY"
    assert rows["answer_first"]["execution_status"] == "EXECUTED_SYNTHETIC_CONTRACT_ONLY"
    assert rows["ecm_full"]["execution_status"] == "EXECUTED_SYNTHETIC_CONTRACT_ONLY"
    assert rows["direct"]["record_count"] == 2
    assert rows["answer_first"]["record_count"] == 2
    assert rows["ecm_full"]["record_count"] == 2

    for row in rows.values():
        for metric in row["structural_metrics"].values():
            assert set(metric) == {"passed", "eligible", "rate", "status"}
            if metric["eligible"]:
                assert metric["rate"] == metric["passed"] / metric["eligible"]
            else:
                assert metric["rate"] is None

    assert rows["direct"]["structural_metrics"]["schema_valid"]["passed"] == 2
    assert rows["direct"]["structural_metrics"]["answer_frozen_before_question"]["passed"] == 0
    assert rows["direct"]["structural_metrics"]["package_triplet_complete"]["status"] == "NOT_APPLICABLE_BY_DESIGN"
    assert rows["answer_first"]["structural_metrics"]["answer_frozen_before_question"]["passed"] == 2
    assert rows["answer_first"]["structural_metrics"]["provenance_replay"]["status"] == "NOT_APPLICABLE_BY_DESIGN"
    assert rows["ecm_full"]["structural_metrics"]["package_triplet_complete"]["passed"] == 2
    assert rows["ecm_full"]["structural_metrics"]["provenance_replay"]["passed"] == 2


def test_verifier_rejects_tampering(tmp_path):
    output = tmp_path / "report.json"
    run_contract_experiment([LAYOUT, PIXEL], output)
    report = json.loads(output.read_text())
    report["item_count"] = 999
    output.write_text(json.dumps(report))

    try:
        verify_contract_report(output)
    except ValueError as exc:
        assert "receipt" in str(exc)
    else:
        raise AssertionError("tampered report was accepted")


def test_verifier_rejects_invalid_resealed_report(tmp_path):
    from ecm_tqag.core import receipt

    output = tmp_path / "report.json"
    run_contract_experiment([LAYOUT, PIXEL], output)
    report = json.loads(output.read_text())
    report["methods"][0]["record_count"] = 999
    report["report_sha256"] = receipt({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    output.write_text(json.dumps(report))

    try:
        verify_contract_report(output)
    except ValueError as exc:
        assert "baseline" in str(exc) or "method" in str(exc)
    else:
        raise AssertionError("invalid resealed report was accepted")


REAL_INVENTORY = ROOT.parent / "conference_eval/inventory_v1.json"


@pytest.mark.skipif(
    not REAL_INVENTORY.is_file(),
    reason="conference_eval/inventory_v1.json is a restricted Gate-1 inventory kept outside this public repository (see README section 9); this check runs only where that private input is present",
)
def test_real_data_inventory_is_fail_closed():
    inventory = REAL_INVENTORY
    result = validate_real_data_inventory(inventory)

    assert result["status"] == "BLOCKED"
    assert result["candidate_count"] == 35
    assert result["eligible_count"] == 0
    assert result["eligible_candidate_ids"] == []
    assert result["blocked_count"] == 35
    assert result["source_disjoint"] is False
    assert result["rights_cleared"] is False


def test_statistics_reject_provisional_or_ineligible_rows(tmp_path):
    provisional = {
        "schema": "ecm-tqag.adjudicated-results.v1",
        "items": [
            {
                "item_id": "candidate-1",
                "document_id": "doc-1",
                "method": "ecm_full",
                "eligibility_status": "BLOCKED",
                "annotation_status": "PROVISIONAL",
                "answer_correct": True,
            }
        ],
    }
    source = tmp_path / "provisional.json"
    source.write_text(json.dumps(provisional), encoding="utf-8")

    with pytest.raises(ValueError, match="eligible|adjudicated|provisional|validation"):
        run_adjudicated_statistics(source, tmp_path / "statistics.json")


def test_statistics_are_deterministic_descriptive_only(tmp_path):
    candidate_ids = ["c1", "c2"]
    validation, adjudication = _linked_artifacts(candidate_ids)
    validation_path = tmp_path / "validation.json"
    adjudication_path = tmp_path / "adjudication.json"
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    adjudication_path.write_text(json.dumps(adjudication), encoding="utf-8")
    source = tmp_path / "adjudicated.json"
    source.write_text(json.dumps({
        "schema": "ecm-tqag.adjudicated-results.v1",
        "eligibility_validation_sha256": validation["validation_sha256"],
        "adjudication_manifest_sha256": adjudication["adjudication_sha256"],
        "items": [
            {"item_id": "i1", "document_id": "d1", "candidate_id": "c1", "method": "direct",
             "eligibility_status": "ELIGIBLE", "annotation_status": "ADJUDICATED",
             "answer_correct": True},
            {"item_id": "i1", "document_id": "d1", "candidate_id": "c2", "method": "answer_first",
             "eligibility_status": "ELIGIBLE", "annotation_status": "ADJUDICATED",
             "answer_correct": False},
        ],
    }), encoding="utf-8")
    output = tmp_path / "stats.json"
    first = run_adjudicated_statistics(source, output, validation_path, adjudication_path)
    first_bytes = output.read_bytes()
    second = run_adjudicated_statistics(source, output, validation_path, adjudication_path)
    assert first == second and output.read_bytes() == first_bytes
    assert first["status"] == "DESCRIPTIVE_ONLY"
    assert first["methods"][0]["answer_correct_rate"] == 1.0
    assert first["methods"][1]["answer_correct_rate"] == 0.0
    assert first["methods"][2]["status"] == "NO_ELIGIBLE_ROWS"


def test_statistics_accepts_only_linked_declared_artifacts(tmp_path):
    candidate_ids = ["c1", "c2"]
    validation, adjudication = _linked_artifacts(candidate_ids)
    validation_path = tmp_path / "validation.json"
    adjudication_path = tmp_path / "adjudication.json"
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    adjudication_path.write_text(json.dumps(adjudication), encoding="utf-8")
    source = tmp_path / "linked.json"
    source.write_text(json.dumps({
        "schema": "ecm-tqag.adjudicated-results.v1",
        "eligibility_validation_sha256": validation["validation_sha256"],
        "adjudication_manifest_sha256": adjudication["adjudication_sha256"],
        "items": [
            {"item_id": "i1", "document_id": "d1", "candidate_id": "c1", "method": "direct",
             "eligibility_status": "ELIGIBLE", "annotation_status": "ADJUDICATED", "answer_correct": True},
        ],
    }), encoding="utf-8")
    output = tmp_path / "stats.json"
    result = run_adjudicated_statistics(source, output, validation_path, adjudication_path)
    assert result["scope"] == "LINKED_DECLARED_ARTIFACTS_ONLY"
    assert result["status"] == "DESCRIPTIVE_ONLY"


def test_statistics_rejects_unlinked_status_strings(tmp_path):
    source = tmp_path / "declared-only.json"
    source.write_text(json.dumps({
        "schema": "ecm-tqag.adjudicated-results.v1",
        "items": [{
            "item_id": "i1", "document_id": "d1", "method": "direct",
            "eligibility_status": "ELIGIBLE", "annotation_status": "ADJUDICATED",
            "answer_correct": True,
        }],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="validation|receipt|linked|attestation"):
        run_adjudicated_statistics(source, tmp_path / "stats.json")


def test_verifier_rejects_resealed_failed_structural_metric(tmp_path):
    from ecm_tqag.core import receipt
    output = tmp_path / "report.json"
    run_contract_experiment([LAYOUT, PIXEL], output)
    report = json.loads(output.read_text(encoding="utf-8"))
    metric = report["methods"][2]["structural_metrics"]["provenance_replay"]
    metric["passed"] = 0
    metric["rate"] = 0.0
    report["report_sha256"] = receipt({k: v for k, v in report.items() if k != "report_sha256"})
    output.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="failed|provenance"):
        verify_contract_report(output)


def test_replay_verifier_rejects_fully_resealed_forged_answers(tmp_path):
    output = tmp_path / "report.json"
    run_contract_experiment([LAYOUT, PIXEL], output)
    report = json.loads(output.read_text(encoding="utf-8"))
    for method in report["methods"]:
        for record in method["records"]:
            record["answer"] = "adversarially changed"
            record["record_sha256"] = receipt({
                key: value for key, value in record.items() if key != "record_sha256"
            })
        method["records_sha256"] = receipt(method["records"])
    report["report_sha256"] = receipt({
        key: value for key, value in report.items() if key != "report_sha256"
    })
    output.write_text(json.dumps(report), encoding="utf-8")

    assert verify_contract_report(output)["status"] == "SELF_CONSISTENCY_ONLY"
    with pytest.raises(ValueError, match="source replay mismatch|not reproduced"):
        verify_contract_report(output, sources=[LAYOUT, PIXEL])
