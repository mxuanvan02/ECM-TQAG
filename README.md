# ECM-TQAG

ECM-TQAG is an offline reference implementation for constructing traceable multimodal textbook-question-answering (TQA) records from a documented normalized-document representation. It also supports evaluation of the resulting records under progressively richer evidence conditions:

- **T** (`text_only`): text evidence
- **TL** (`text_layout`): text plus layout or structure
- **TLV** (`full_pixels`): text, layout, and an embedded visual asset

The repository provides a standard-library implementation, strict JSON validation, canonical SHA-256 receipts, executable synthetic examples, and tests. Construction and validation run offline without network access, API credentials, proprietary software, or source-derived images. Deterministic integrity checks are reported separately from semantic judgments made by an answering model.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
pytest
ecm-tqag validate fixtures/packages
ecm-tqag run configs/offline-example.json
ecm-tqag verify-run run-output/summary.json --config configs/offline-example.json
ecm-tqag export-dataset run-output/summary.json run-output/dataset.jsonl
ecm-tqag generate fixtures/documents/layout.json run-output/generated-layout
```

The package can also be used directly from a checkout with `PYTHONPATH=src`.

## End-to-end generator

`generate` accepts the versioned `ecm-tqag.normalized-document.v2` JSON contract
(`schemas/normalized-document.schema.json`). A document contains typed nodes,
typed directed edges, and one or more deterministic motifs. One item and one
matched T/TL/TLV triplet are produced for each motif. The answer is computed
from a layout relation or decoded PNG pixels before the question is realized.
The output includes a portable manifest, package hashes, and replayable steps.

```bash
ecm-tqag generate fixtures/documents/layout.json run-output/generated-layout
# A nonempty destination is rejected; use --replace only when replacement is intended.
ecm-tqag validate-generated run-output/generated-layout --source fixtures/documents/layout.json
ecm-tqag validate run-output/generated-layout/items/layout-demo-m-layout/packages

ecm-tqag generate fixtures/documents/pixel.json run-output/generated-pixel
ecm-tqag validate-generated run-output/generated-pixel --source fixtures/documents/pixel.json
```

`text_only` contains text evidence, `text_layout` adds the normalized layout,
and `full_pixels` adds the validated base64 PNG. The three packages share the
same item identifier and question; their text and layout evidence are matched
where applicable. The included inputs are small synthetic examples. The
implementation deliberately supports only the documented normalized contract
and a bounded RGB PNG decoder; it is not a PDF, OCR, or general image system.

## Layout

```text
src/ecm_tqag/       installable library and CLI
fixtures/            synthetic, rights-cleared T/TL/TLV packages
schemas/             JSON Schema for public condition packages
tests/               unit and integration tests
configs/              example offline experiment configuration
docs/                neutral usage and data notes
run-output/           synthetic offline execution summary
```

## Package contract

Every fixture declares `schema`, `item_id`, `condition`, and evidence metadata. TLV packages embed a tiny synthetic PNG and must include matching byte length, dimensions, and SHA-256. Public packages may not contain host paths, credentials, or hidden reference answers. Validation is deterministic and produces a canonical receipt hash. The `run` command defaults only when explicitly configured for offline mode; OpenAI-compatible mode requires an endpoint, model, and the name of an environment variable containing a credential. Outputs are atomically replaced and `verify-run` checks their canonical receipt and every answer contract. With `--config`, it recomputes the config hash (including `api_key_env`, never its secret), package hashes, and condition membership. Use `--packages DIR` to override the config package directory. `validate` scans nested JSON files recursively and ignores symlinks.

## Reproduction and scope

The end-to-end example starts from a normalized-document JSON file and produces new TQA records. For each specified motif, the generator computes an answer from the documented text/layout or pixel evidence, formulates a question, creates matched `text_only`, `text_layout`, and `full_pixels` packages, and writes a manifest containing package hashes and replayable provenance. `validate-generated` recomputes the source digest, validates the package triplet, and replays the recorded computation.

The included documents are small synthetic examples. They demonstrate the construction interface and output format, not benchmark performance or semantic accuracy. The implementation supports the documented normalized-document contract and a bounded RGB/RGBA PNG decoder; it is not a general PDF, OCR, or image-understanding system. The optional answering-model commands operate on packages and may require a configured endpoint and credential; their responses are not expected to be identical across providers or model versions.

For the basic construction path:

```bash
ecm-tqag generate fixtures/documents/layout.json run-output/generated-layout --replace
ecm-tqag validate-generated run-output/generated-layout --source fixtures/documents/layout.json

ecm-tqag generate fixtures/documents/pixel.json run-output/generated-pixel --replace
ecm-tqag validate-generated run-output/generated-pixel --source fixtures/documents/pixel.json
```

The generated directories contain `manifest.json`, one TQA record per motif, and three condition-specific package files per record. A successful validation prints `status: PASS` and the number of generated items. The older package-level commands (`validate`, `run`, `verify-run`, and `export-dataset`) remain available for evaluating preconstructed packages.

## Conference contract diagnostic

The repository includes a deterministic, structural-only diagnostic for checking the
conference-evaluation contract on the two synthetic normalized documents:

```bash
ecm-tqag contract-eval run-output/conference-contract-report.json \
  fixtures/documents/layout.json fixtures/documents/pixel.json
ecm-tqag verify-contract-eval run-output/conference-contract-report.json
```

This command executes deterministic `direct`, `answer_first`, and `ecm_full`
construction contracts from the actual normalized motifs. It validates schemas,
answer-freezing order, deterministic records/checksums, and—for `ecm_full` only—the
package triplet and provenance replay. Unsupported baseline metrics are explicitly
`NOT_APPLICABLE_BY_DESIGN`. It does **not** run an answering model or human semantic
evaluation. The report marks real-data eligibility and comparative effectiveness as
`BLOCKED`; only the synthetic structural reproducibility contract may report
`PASS_STRUCTURAL_ONLY`.

Contract verification has two explicit levels:

```bash
# Checks only the report's internal consistency; output is SELF_CONSISTENCY_ONLY.
ecm-tqag verify-contract-eval run-output/conference-contract-report.json

# Replays all contract construction from the supplied source documents.
# Only this path can output PASS_REPLAY_VERIFIED.
ecm-tqag verify-contract-eval run-output/conference-contract-report.json \
  --source fixtures/documents/layout.json fixtures/documents/pixel.json
```

A SHA-256 receipt is only a consistency checksum. A report can be internally
self-consistent after its contents are resealed; source replay is therefore required
for the stronger structural verification verdict. Neither verdict establishes
semantic correctness, benchmark effectiveness, modality necessity, or baseline
superiority. Gate 1 inventory validation and fail-closed descriptive statistics are
also executable:

```bash
# BLOCKED returns exit code 2; parse the JSON status explicitly.
ecm-tqag validate-real-inventory ../conference_eval/inventory_v1.json

ecm-tqag adjudicated-statistics adjudicated-results.json statistics.json \
  --validation eligibility-validation.json \
  --adjudication adjudication-manifest.json
```

Statistics require a checksum-linked Gate 1 validation artifact and adjudication
manifest, plus candidate membership, blinded status, and at least two declared
annotators. Provisional, blocked, unlinked, or self-contained status-only rows are
rejected. Accepted output is `DESCRIPTIVE_ONLY` with scope
`LINKED_DECLARED_ARTIFACTS_ONLY` and attestation `NO_EXTERNAL_ATTESTATION`: these
checks establish internal consistency and linkage, not proof of rights clearance,
independent human behavior, or annotation truth. SHA-256 values are consistency
checksums, not signatures. Consequently this report is not evidence of answer
correctness, modality necessity, baseline superiority, or generalization.

## License

Code and documentation are licensed under Apache-2.0; see [LICENSE](LICENSE). See [RIGHTS_AND_LIMITATIONS.md](RIGHTS_AND_LIMITATIONS.md) for data boundaries.

## Citation

See [CITATION.cff](CITATION.cff).

## Development

```bash
uv sync --extra test
uv run pytest
uv build --wheel
uv run --isolated --no-project --with dist/ecm_tqag-1.5.0-py3-none-any.whl ecm-tqag validate fixtures/packages
uv run --isolated --no-project --with dist/ecm_tqag-1.5.0-py3-none-any.whl ecm-tqag run configs/offline-example.json
uv run --isolated --no-project --with dist/ecm_tqag-1.5.0-py3-none-any.whl ecm-tqag verify-run run-output/summary.json --config configs/offline-example.json
```

The repository contains the implementation, schemas, and synthetic examples. Running the offline configuration generates `run-output/summary.json`; this summary records execution on the included fixtures and is not a benchmark result or a source-derived dataset.

## Security

Please do not add credentials, private package names, absolute local paths, or source-derived media to public fixtures. Report security issues privately to the repository maintainers.
