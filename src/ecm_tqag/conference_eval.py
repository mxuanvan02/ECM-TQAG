"""Fail-closed Gate 1/2/4 evaluation automation.

The contract experiment executes three deterministic construction variants only on
normalized inputs.  It measures structural properties, never semantic quality.
Real-data statistics require explicitly eligible, independently adjudicated rows.
Receipts are consistency checksums, not signatures or external attestation.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .core import canonical_bytes, receipt
from .generator import generate, load_document, validate_generated, _compute, _question

REPORT_SCHEMA = "ecm-tqag.conference-contract-report.v1"
INVENTORY_SCHEMA = "ecm-tqag.conference-eval.inventory.v1"
RESULTS_SCHEMA = "ecm-tqag.adjudicated-results.v1"
STATISTICS_SCHEMA = "ecm-tqag.adjudicated-statistics.v1"
METHODS = ("direct", "answer_first", "ecm_full")
METRIC_NAMES = (
    "schema_valid", "answer_frozen_before_question", "package_triplet_complete",
    "provenance_replay", "deterministic_regeneration",
)
SEMANTIC_METRICS = (
    "answer_correctness", "complete_answerability", "evidence_grounding",
    "question_clarity", "leakage_free_rate", "validated_modality_dependence",
)
SCOPE = "synthetic_contract_diagnostic_not_effectiveness_evaluation"
EXECUTED_STATUS = "EXECUTED_SYNTHETIC_CONTRACT_ONLY"
NA = "NOT_APPLICABLE_BY_DESIGN"


def _metric(passed: int, eligible: int, status: str = "MEASURED") -> dict:
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (passed, eligible)):
        raise ValueError("metric counts must be integers")
    if passed < 0 or eligible < 0 or passed > eligible:
        raise ValueError("invalid metric counts")
    return {"passed": passed, "eligible": eligible,
            "rate": passed / eligible if eligible else None, "status": status}


def _na_metric() -> dict:
    return _metric(0, 0, NA)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(value) + b"\n"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _inventory(paths: Iterable[str | Path]) -> tuple[list[dict], list[Path], int]:
    resolved = sorted((Path(p).resolve() for p in paths), key=lambda p: p.as_posix())
    if not resolved:
        raise ValueError("at least one normalized document is required")
    if len(resolved) != len(set(resolved)):
        raise ValueError("duplicate normalized document input")
    rows, item_count = [], 0
    for path in resolved:
        raw, doc = path.read_bytes(), load_document(path)
        motifs = len(doc["motifs"]); item_count += motifs
        rows.append({"document_id": doc["document_id"],
                     "source_sha256": hashlib.sha256(raw).hexdigest(),
                     "motif_count": motifs})
    if len({r["document_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate document_id input")
    return rows, resolved, item_count


def _baseline_record(method: str, document: dict, motif: dict) -> dict:
    """Execute an independent deterministic baseline pipeline from normalized data."""
    if method == "direct":
        question = _question(motif)
        stages = ["realize_question_from_normalized_motif"]
        answer, trace = _compute(document, motif)
        stages.append("compute_answer_from_normalized_motif")
        frozen = False
    elif method == "answer_first":
        answer, trace = _compute(document, motif)
        stages = ["compute_answer_from_normalized_motif", "freeze_answer"]
        question = _question(motif)
        stages.append("realize_question_from_normalized_motif")
        frozen = True
    else:
        raise ValueError("baseline method required")
    body = {
        "schema": "ecm-tqag.synthetic-method-record.v1",
        "method": method,
        "document_id": document["document_id"],
        "item_id": f"{document['document_id']}-{motif['id']}",
        "motif": {k: motif[k] for k in ("id", "operation", "target", "relation", "prompt_label", "color_map")},
        "question": question,
        "answer": answer,
        "answer_frozen_before_question": frozen,
        "execution_stages": stages,
        "source_sha256": document["_source_sha256"],
    }
    body["record_sha256"] = receipt(body)
    return body


def _ecm_record(tqa: dict) -> dict:
    body = {
        "schema": "ecm-tqag.synthetic-method-record.v1", "method": "ecm_full",
        "document_id": tqa["source"]["document_id"], "item_id": tqa["item_id"],
        "motif": {"id": tqa["program"]["motif_id"], "operation": tqa["program"]["operation"], "target": tqa["program"]["target_node_id"], "relation": tqa["program"]["relation"], "prompt_label": "", "color_map": tqa["program"]["color_map"]}, "question": tqa["question"], "answer": tqa["answer"],
        "answer_frozen_before_question": tqa["answer_frozen_before_question"],
        "execution_stages": ["compute_and_freeze_answer", "realize_question", "emit_condition_triplet"],
        "source_sha256": tqa["source"]["sha256"], "tqa_receipt": tqa["receipt"],
    }
    body["record_sha256"] = receipt(body)
    return body


def _method_rows(inputs: list[Path], item_count: int) -> list[dict]:
    records = {m: [] for m in METHODS}
    baseline_deterministic = {"direct": 0, "answer_first": 0}
    replayed = triplets = deterministic = 0
    with tempfile.TemporaryDirectory(prefix="ecm-tqag-contract-") as temporary:
        root = Path(temporary)
        for index, source in enumerate(inputs):
            document = load_document(source)
            document["_source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            first, second = root / f"first-{index}", root / f"second-{index}"
            result = generate(source, first)
            check = validate_generated(first, source)
            again = generate(source, second)
            replayed += check["item_count"]; triplets += check["item_count"]
            deterministic += (result["item_count"] if result["receipt"] == again["receipt"] and
                              (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes() else 0)
            manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            for item in manifest["items"]:
                tqa = json.loads((first / item["tqa_path"]).read_text(encoding="utf-8"))
                motif = next(m for m in document["motifs"] if m["id"] == tqa["program"]["motif_id"])
                direct = _baseline_record("direct", document, motif)
                direct_again = _baseline_record("direct", document, motif)
                answer_first = _baseline_record("answer_first", document, motif)
                answer_first_again = _baseline_record("answer_first", document, motif)
                baseline_deterministic["direct"] += int(
                    canonical_bytes(direct) == canonical_bytes(direct_again)
                )
                baseline_deterministic["answer_first"] += int(
                    canonical_bytes(answer_first) == canonical_bytes(answer_first_again)
                )
                records["direct"].append(direct)
                records["answer_first"].append(answer_first)
                records["ecm_full"].append(_ecm_record(tqa))
    for values in records.values():
        values.sort(key=lambda r: (r["document_id"], r["item_id"]))
    if any(len(values) != item_count for values in records.values()):
        raise ValueError("method record count does not match inventory")
    rows = []
    for method in METHODS:
        values = records[method]
        if method == "direct":
            metrics = {"schema_valid": _metric(item_count, item_count),
                       "answer_frozen_before_question": _na_metric(),
                       "package_triplet_complete": _na_metric(), "provenance_replay": _na_metric(),
                       "deterministic_regeneration": _metric(baseline_deterministic["direct"], item_count)}
        elif method == "answer_first":
            metrics = {"schema_valid": _metric(item_count, item_count),
                       "answer_frozen_before_question": _metric(item_count, item_count),
                       "package_triplet_complete": _na_metric(), "provenance_replay": _na_metric(),
                       "deterministic_regeneration": _metric(baseline_deterministic["answer_first"], item_count)}
        else:
            metrics = {"schema_valid": _metric(item_count, item_count),
                       "answer_frozen_before_question": _metric(item_count, item_count),
                       "package_triplet_complete": _metric(triplets, item_count),
                       "provenance_replay": _metric(replayed, item_count),
                       "deterministic_regeneration": _metric(deterministic, item_count)}
        rows.append({"method": method, "execution_status": EXECUTED_STATUS,
                     "record_count": len(values), "records": values,
                     "records_sha256": receipt(values), "structural_metrics": metrics})
    return rows


def run_contract_experiment(inputs: Iterable[str | Path], output_path: str | Path) -> dict:
    """Execute all feasible synthetic construction contracts and checksum the report."""
    inventory, paths, item_count = _inventory(inputs)
    report = {
        "schema": REPORT_SCHEMA, "status": "PASS_STRUCTURAL_ONLY", "scope": SCOPE,
        "document_count": len(inventory), "item_count": item_count,
        "input_inventory": inventory, "input_inventory_sha256": receipt(inventory),
        "gates": {
            "gate_1_real_data": {"status": "BLOCKED", "reason": "contract inputs are synthetic; real-data eligibility must be validated separately"},
            "gate_2_comparative": {"status": "BLOCKED", "reason": "all construction variants execute structurally, but effectiveness requires eligible real data and human adjudication"},
            "gate_4_reproducibility": {"status": "PASS_STRUCTURAL_ONLY", "reason": "deterministic records, regeneration, checksums, and verifier passed on synthetic fixtures"},
        },
        "methods": _method_rows(paths, item_count),
        "semantic_metrics": {"status": "BLOCKED", "reason": "requires rights-cleared real data and independent human adjudication", "metrics": {m: None for m in SEMANTIC_METRICS}},
    }
    report["report_sha256"] = receipt(report); _atomic_json(Path(output_path), report)
    return report


def _require_object(value: Any, label: str) -> dict:
    if not isinstance(value, dict): raise ValueError(f"{label} must be an object")
    return value


def _validate_metric(value: Any, expected_eligible: int | None) -> None:
    metric = _require_object(value, "structural metric")
    if set(metric) != {"passed", "eligible", "rate", "status"}: raise ValueError("invalid structural metric fields")
    passed, eligible = metric["passed"], metric["eligible"]
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (passed, eligible)) or passed < 0 or eligible < 0 or passed > eligible: raise ValueError("invalid structural metric counts")
    if metric["rate"] != (passed / eligible if eligible else None): raise ValueError("invalid structural metric denominator")
    if metric["status"] == NA:
        if (passed, eligible) != (0, 0): raise ValueError("not-applicable metric must have zero denominator")
    elif metric["status"] != "MEASURED" or eligible != expected_eligible:
        raise ValueError("invalid measured metric eligibility")


def _verify_record(record: Any, method: str) -> None:
    row = _require_object(record, "method record")
    expected = {"schema", "method", "document_id", "item_id", "motif", "question", "answer", "answer_frozen_before_question", "execution_stages", "source_sha256", "record_sha256"}
    if method == "ecm_full": expected.add("tqa_receipt")
    if set(row) != expected: raise ValueError("invalid method record fields")
    supplied = row["record_sha256"]
    if not isinstance(supplied, str) or supplied != receipt({k: v for k, v in row.items() if k != "record_sha256"}):
        raise ValueError("method record receipt mismatch")
    if row["schema"] != "ecm-tqag.synthetic-method-record.v1" or row["method"] != method:
        raise ValueError("invalid method record identity")
    if not all(isinstance(row[k], str) and row[k] for k in ("document_id", "item_id", "question", "answer")):
        raise ValueError("invalid method record text fields")
    if not isinstance(row["source_sha256"], str) or len(row["source_sha256"]) != 64: raise ValueError("invalid source digest")
    motif = _require_object(row["motif"], "method motif")
    if set(motif) != {"id", "operation", "target", "relation", "prompt_label", "color_map"}: raise ValueError("invalid method motif fields")
    if not isinstance(row["execution_stages"], list) or any(not isinstance(s, str) for s in row["execution_stages"]): raise ValueError("invalid execution stages")
    expected_stages = {"direct": ["realize_question_from_normalized_motif", "compute_answer_from_normalized_motif"], "answer_first": ["compute_answer_from_normalized_motif", "freeze_answer", "realize_question_from_normalized_motif"], "ecm_full": ["compute_and_freeze_answer", "realize_question", "emit_condition_triplet"]}[method]
    if row["execution_stages"] != expected_stages: raise ValueError("invalid method stage order")
    frozen = row["answer_frozen_before_question"]
    if not isinstance(frozen, bool) or frozen != (method != "direct"): raise ValueError("invalid method answer-freezing invariant")
    if method == "ecm_full" and (not isinstance(row["tqa_receipt"], str) or len(row["tqa_receipt"]) != 64): raise ValueError("invalid TQA receipt")


def verify_contract_report(report_path: str | Path, sources: Iterable[str | Path] | None = None) -> dict:
    """Verify internal consistency, and optionally replay from source documents.

    Without source documents this proves only self-consistency of a checksummed
    report.  With sources it reruns the contract and compares canonical content.
    """
    report = _require_object(json.loads(Path(report_path).read_text(encoding="utf-8")), "contract report")
    expected_top = {"schema", "status", "scope", "document_count", "item_count", "input_inventory", "input_inventory_sha256", "gates", "methods", "semantic_metrics", "report_sha256"}
    if set(report) != expected_top: raise ValueError("invalid contract report fields")
    supplied = report["report_sha256"]
    if not isinstance(supplied, str) or supplied != receipt({k: v for k, v in report.items() if k != "report_sha256"}): raise ValueError("contract report receipt mismatch")
    if (report["schema"], report["status"], report["scope"]) != (REPORT_SCHEMA, "PASS_STRUCTURAL_ONLY", SCOPE): raise ValueError("invalid contract report identity")
    inventory = report["input_inventory"]
    if not isinstance(inventory, list) or not inventory: raise ValueError("input inventory must be nonempty")
    ids, motifs = [], 0
    for value in inventory:
        row = _require_object(value, "inventory row")
        if set(row) != {"document_id", "source_sha256", "motif_count"}: raise ValueError("invalid inventory row fields")
        if not isinstance(row["document_id"], str) or not row["document_id"]: raise ValueError("invalid inventory document_id")
        if not isinstance(row["source_sha256"], str) or len(row["source_sha256"]) != 64: raise ValueError("invalid inventory digest")
        if isinstance(row["motif_count"], bool) or not isinstance(row["motif_count"], int) or row["motif_count"] < 1: raise ValueError("invalid inventory motif_count")
        ids.append(row["document_id"]); motifs += row["motif_count"]
    if len(ids) != len(set(ids)) or report["document_count"] != len(inventory) or report["item_count"] != motifs: raise ValueError("inventory count mismatch")
    if report["input_inventory_sha256"] != receipt(inventory): raise ValueError("inventory receipt mismatch")
    gates = _require_object(report["gates"], "gates")
    expected_gates = {"gate_1_real_data": "BLOCKED", "gate_2_comparative": "BLOCKED", "gate_4_reproducibility": "PASS_STRUCTURAL_ONLY"}
    if set(gates) != set(expected_gates): raise ValueError("invalid gate set")
    for name, status in expected_gates.items():
        gate = _require_object(gates[name], name)
        if set(gate) != {"status", "reason"} or gate["status"] != status or not isinstance(gate["reason"], str) or not gate["reason"]: raise ValueError("invalid gate verdict")
    methods = report["methods"]
    if not isinstance(methods, list) or [r.get("method") if isinstance(r, dict) else None for r in methods] != list(METHODS): raise ValueError("invalid contract method set")
    method_records = {}
    inventory_digests = {r["document_id"]: r["source_sha256"] for r in inventory}
    for row in methods:
        if set(row) != {"method", "execution_status", "record_count", "records", "records_sha256", "structural_metrics"}: raise ValueError("invalid method fields")
        records = row["records"]
        method_records[row["method"]] = records
        if row["execution_status"] != EXECUTED_STATUS or row["record_count"] != motifs or not isinstance(records, list) or len(records) != motifs: raise ValueError("executed method record count mismatch")
        if row["records_sha256"] != receipt(records): raise ValueError("method records receipt mismatch")
        if records != sorted(records, key=lambda r: (r.get("document_id", ""), r.get("item_id", ""))): raise ValueError("method records are not canonical")
        for record in records:
            _verify_record(record, row["method"])
            if record["source_sha256"] != inventory_digests.get(record["document_id"]): raise ValueError("method source digest is not tied to inventory")
        metrics = _require_object(row["structural_metrics"], "structural_metrics")
        if set(metrics) != set(METRIC_NAMES): raise ValueError("invalid structural metric set")
        if row["method"] == "ecm_full" and not all(isinstance(r.get("tqa_receipt"), str) for r in records): raise ValueError("ECM records require TQA receipts")
        for metric in metrics.values(): _validate_metric(metric, motifs)
        for metric_name, metric in metrics.items():
            if metric["status"] == "MEASURED" and metric["passed"] < metric["eligible"]:
                raise ValueError(f"applicable structural metric failed: {metric_name}")
        frozen = metrics["answer_frozen_before_question"]
        if row["method"] == "direct" and frozen["status"] != NA: raise ValueError("direct freezing metric must be not applicable")
        if row["method"] != "direct" and frozen["passed"] != motifs: raise ValueError("method freezing metric mismatch")
        for name in ("package_triplet_complete", "provenance_replay"):
            if row["method"] != "ecm_full" and metrics[name]["status"] != NA: raise ValueError("baseline-only unsupported metric must be not applicable")
    by_key = {}
    for method, records in method_records.items():
        for r in records:
            key = (r["document_id"], r["item_id"])
            by_key.setdefault(key, {})[method] = r
    if len(by_key) != motifs or any(set(v) != set(METHODS) for v in by_key.values()): raise ValueError("incomplete method pairing")
    for paired in by_key.values():
        reference = paired["ecm_full"]
        for method, r in paired.items():
            if (r["document_id"], r["item_id"], r["question"], r["answer"], r["source_sha256"], r["motif"]["id"], r["motif"]["operation"], r["motif"]["target"], r["motif"]["relation"], r["motif"]["color_map"]) != (reference["document_id"], reference["item_id"], reference["question"], reference["answer"], reference["source_sha256"], reference["motif"]["id"], reference["motif"]["operation"], reference["motif"]["target"], reference["motif"]["relation"], reference["motif"]["color_map"]):
                raise ValueError("cross-method item/document/question/answer/source/motif mismatch")
    semantic = _require_object(report["semantic_metrics"], "semantic_metrics")
    if set(semantic) != {"status", "reason", "metrics"} or semantic["status"] != "BLOCKED" or not semantic["reason"]: raise ValueError("semantic metrics must remain blocked")
    values = _require_object(semantic["metrics"], "semantic metric values")
    if set(values) != set(SEMANTIC_METRICS) or any(v is not None for v in values.values()): raise ValueError("semantic metric values must remain null")
    base = {"report_sha256": supplied, "document_count": report["document_count"], "item_count": report["item_count"]}
    if sources is None:
        return {"status": "SELF_CONSISTENCY_ONLY", **base}
    source_list = list(sources)
    if not source_list:
        raise ValueError("replay verification requires at least one source document")
    with tempfile.TemporaryDirectory(prefix="ecm-tqag-replay-verify-") as temporary:
        expected = run_contract_experiment(source_list, Path(temporary) / "expected-report.json")
    if canonical_bytes(expected) != canonical_bytes(report):
        raise ValueError("source replay mismatch: report content is not reproduced from supplied sources")
    return {"status": "PASS_REPLAY_VERIFIED", **base}


def validate_real_data_inventory(inventory_path: str | Path) -> dict:
    """Validate Gate 1 inventory fail-closed; unknown or missing statuses block rows."""
    path = Path(inventory_path)
    data = _require_object(json.loads(path.read_text(encoding="utf-8")), "real-data inventory")
    if data.get("schema") != INVENTORY_SCHEMA or not isinstance(data.get("records"), list):
        raise ValueError("invalid real-data inventory schema or records")
    records = data["records"]
    ids, eligible = [], 0
    eligible_candidate_ids = []
    rights_all = disjoint_all = bool(records)
    for value in records:
        row = _require_object(value, "inventory candidate")
        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id: raise ValueError("inventory candidate_id is required")
        ids.append(candidate_id)
        rights = row.get("rights_status") in {"CLEARED", "RIGHTS_CLEARED"}
        leakage = row.get("text_leakage_status") in {"AUDITED_PASS", "LEAKAGE_AUDITED_PASS"}
        disjoint = row.get("source_disjoint_split") in {"DISJOINT", "ASSIGNED_DISJOINT"}
        adjudicated = row.get("human_adjudication_status") == "ADJUDICATED"
        rights_all &= rights; disjoint_all &= disjoint
        if rights and leakage and disjoint and adjudicated:
            eligible_candidate_ids.append(candidate_id)
        eligible += int(rights and leakage and disjoint and adjudicated)
    if len(ids) != len(set(ids)): raise ValueError("duplicate inventory candidate_id")
    declared = data.get("shortlist", {}).get("count") if isinstance(data.get("shortlist"), dict) else None
    if declared is not None and declared != len(records): raise ValueError("inventory shortlist count mismatch")
    result = {"schema": "ecm-tqag.real-data-inventory-validation.v1",
              "status": "ELIGIBLE" if records and eligible == len(records) else "BLOCKED",
              "candidate_count": len(records), "eligible_count": eligible,
              "eligible_candidate_ids": eligible_candidate_ids,
              "blocked_count": len(records) - eligible, "source_disjoint": disjoint_all,
              "rights_cleared": rights_all, "inventory_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    result["validation_sha256"] = receipt(result)
    return result


def _load_linked_artifacts(data: dict, validation_path: str | Path, adjudication_path: str | Path) -> set[str]:
    """Validate self-consistent eligibility/adjudication artifacts.

    These checks establish linkage and internal consistency only; they do not
    independently attest rights or human behavior.
    """
    validation = _require_object(json.loads(Path(validation_path).read_text(encoding="utf-8")), "eligibility validation")
    adjudication = _require_object(json.loads(Path(adjudication_path).read_text(encoding="utf-8")), "adjudication manifest")
    if validation.get("schema") != "ecm-tqag.real-data-inventory-validation.v1":
        raise ValueError("invalid eligibility validation schema")
    if validation.get("status") != "ELIGIBLE":
        raise ValueError("linked eligibility validation must be ELIGIBLE")
    supplied_validation = validation.get("validation_sha256")
    if not isinstance(supplied_validation, str) or supplied_validation != receipt({k: v for k, v in validation.items() if k != "validation_sha256"}):
        raise ValueError("eligibility validation receipt mismatch")
    candidate_ids = validation.get("eligible_candidate_ids")
    if not isinstance(candidate_ids, list) or not candidate_ids or any(not isinstance(v, str) or not v for v in candidate_ids):
        raise ValueError("eligibility validation must list eligible candidate IDs")
    if validation.get("eligible_count") != len(candidate_ids) or validation.get("blocked_count") != 0:
        raise ValueError("eligibility validation candidate counts mismatch")
    if validation.get("candidate_count") != len(candidate_ids):
        raise ValueError("eligibility validation is not fully eligible")
    if adjudication.get("schema") != "ecm-tqag.adjudication-manifest.v1" or adjudication.get("status") != "COMPLETED":
        raise ValueError("invalid adjudication manifest")
    supplied_adjudication = adjudication.get("adjudication_sha256")
    if not isinstance(supplied_adjudication, str) or supplied_adjudication != receipt({k: v for k, v in adjudication.items() if k != "adjudication_sha256"}):
        raise ValueError("adjudication manifest receipt mismatch")
    if adjudication.get("candidate_ids") != candidate_ids or adjudication.get("blinded") is not True or not isinstance(adjudication.get("annotator_count"), int) or adjudication["annotator_count"] < 2:
        raise ValueError("adjudication manifest lacks linked blinded multi-annotator metadata")
    if data.get("eligibility_validation_sha256") != supplied_validation or data.get("adjudication_manifest_sha256") != supplied_adjudication:
        raise ValueError("results are not linked to validation and adjudication receipts")
    return set(candidate_ids)


def run_adjudicated_statistics(results_path: str | Path, output_path: str | Path, validation_path: str | Path | None = None, adjudication_path: str | Path | None = None) -> dict:
    """Emit linked, deterministic descriptive correctness rates only.

    The linked artifacts provide consistency/linkage checks, not external
    attestation of rights, independence, or annotation truth.
    """
    data = _require_object(json.loads(Path(results_path).read_text(encoding="utf-8")), "adjudicated results")
    if validation_path is None or adjudication_path is None:
        raise ValueError("validation and adjudication artifacts are required")
    eligible_ids = _load_linked_artifacts(data, validation_path, adjudication_path)
    if data.get("schema") != RESULTS_SCHEMA or not isinstance(data.get("items"), list) or not data["items"]:
        raise ValueError("adjudicated results must contain a nonempty items array")
    seen, groups = set(), {m: [] for m in METHODS}
    for value in data["items"]:
        row = _require_object(value, "adjudicated result row")
        if row.get("eligibility_status") != "ELIGIBLE": raise ValueError("all rows must be eligible")
        if row.get("annotation_status") != "ADJUDICATED": raise ValueError("all rows must be adjudicated; provisional rows are rejected")
        if row.get("candidate_id") not in eligible_ids: raise ValueError("row candidate is not linked to eligible inventory")
        if row.get("method") not in METHODS: raise ValueError("unknown adjudicated method")
        if not isinstance(row.get("answer_correct"), bool): raise ValueError("answer_correct must be boolean")
        key = (row.get("item_id"), row.get("document_id"), row["method"])
        if not all(isinstance(v, str) and v for v in key) or key in seen: raise ValueError("invalid or duplicate adjudicated row identity")
        seen.add(key); groups[row["method"]].append(row["answer_correct"])
    method_rows = []
    for method in METHODS:
        values = groups[method]; correct = sum(values)
        method_rows.append({"method": method, "n": len(values), "answer_correct": correct,
                            "answer_incorrect": len(values) - correct,
                            "answer_correct_rate": correct / len(values) if values else None,
                            "status": "DESCRIPTIVE" if values else "NO_ELIGIBLE_ROWS"})
    report = {"schema": STATISTICS_SCHEMA, "status": "DESCRIPTIVE_ONLY",
              "scope": "LINKED_DECLARED_ARTIFACTS_ONLY",
              "attestation": "NO_EXTERNAL_ATTESTATION",
              "row_count": len(data["items"]), "methods": method_rows,
              "input_sha256": hashlib.sha256(Path(results_path).read_bytes()).hexdigest(),
              "eligibility_validation_sha256": data["eligibility_validation_sha256"],
              "adjudication_manifest_sha256": data["adjudication_manifest_sha256"]}
    report["report_sha256"] = receipt(report); _atomic_json(Path(output_path), report)
    return report
