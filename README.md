# ECM-TQAG

**Evidence-first construction and structural audit of traceable multimodal textbook question-answering (TQA) items.**

This repository is the reproducible **research-software artifact** for ECM-TQAG. It contains executable contracts, validators, deterministic receipt logic, a command-line runner, JSON Schemas, tests, documentation, and synthetic fixtures. It does **not** contain source textbooks, restricted page images, private experiment records, credentials, or manuscript files.

> **Scope.** The software verifies structural and provenance-recording invariants. A successful verification is not, by itself, evidence of legal or semantic correctness, pedagogical quality, distractor quality, or visual necessity.

## 1. Research pipeline: input → output

```text
Evidence package(s)
  → contract and integrity validation
  → evidence-conditioned request construction
  → offline transport check OR opt-in model call
  → answer record with package receipt
  → run summary with canonical receipt
  → verification and deterministic JSONL export
```

For independently constructed items, the evidence-first path is represented as:

```text
matched evidence motif G_m
  → restricted derivation z
  → answer atoms A + provenance traces Γ
  → four-option question q
  → structural checker C
```

Every answer record carries the item identity, evidence condition, and SHA-256 receipt of the package used to produce it.

## 2. Inputs

### 2.1 Evidence packages

Provide a directory of JSON packages conforming to [`schemas/condition-package.schema.json`](schemas/condition-package.schema.json):

| Field | Required content |
|---|---|
| `schema` | `ecm-tqag.condition-package.v1` |
| `item_id` | Stable identifier using letters, numbers, `.`, `_`, and `-` |
| `question` | Question supplied to the answering/transport stage |
| `condition` | `text_only`, `text_layout`, or `full_pixels` |
| `evidence.text` | Text evidence, 1–10,000 characters |
| `evidence.layout` | Required for `text_layout` and `full_pixels`; typed nodes and edges |
| `pixel_asset` | Required for `full_pixels`; base64 PNG with dimensions, byte length, SHA-256, and provenance |

| Condition | Evidence supplied |
|---|---|
| `text_only` (`T`) | Text only |
| `text_layout` (`TL`) | Text plus declared document structure |
| `full_pixels` (`TLV`) | Text, structure, and visual PNG asset |

External documents must be converted into these packages locally. This repository does not prescribe OCR, layout parsing, or image encoding. Do not commit copyrighted source material without redistribution permission.

### 2.2 Run configuration

Provide a JSON configuration conforming to `ecm-tqag.run-config.v1`, such as [`configs/offline-example.json`](configs/offline-example.json):

```json
{
  "schema": "ecm-tqag.run-config.v1",
  "name": "synthetic-offline-example",
  "packages": "../fixtures/packages",
  "output": "../run-output/summary.json",
  "conditions": ["text_only", "text_layout", "full_pixels"],
  "mode": "offline",
  "timeout_seconds": 60
}
```

Paths are resolved relative to the configuration file unless absolute. `conditions` selects a non-empty subset of the three conditions.

### 2.3 Optional remote-provider settings

Remote execution is opt-in. Copy the non-routable template to an ignored local file:

```bash
cp configs/openai-compatible.template.json configs/openai-compatible.local.json
```

The local configuration requires an HTTPS/HTTP OpenAI-compatible endpoint, a model identifier, the **name** of an environment variable containing the credential, package/output paths, selected conditions, and a timeout. Keep the credential only in the environment; never place it in JSON, Git, logs, or this README. The endpoint receives the selected evidence and, for `full_pixels`, the embedded PNG. Provider behavior, quota, context limits, and image support are provider-specific.

## 3. Outputs

A successful `run` writes the configured summary, containing:

- schema `ecm-tqag.run-summary.v1`;
- run name and mode;
- configuration SHA-256 receipt, which hashes configuration metadata and never the secret value;
- one answer record per selected package/condition;
- each record's item ID, condition, package SHA-256, answer text, and source mode;
- a canonical `summary_sha256` receipt.

`verify-run` returns a JSON PASS record after checking receipts, identities, answer contracts, and (when supplied) package/config membership. `export-dataset` writes deterministic JSON Lines, one validated answer record per line, and reports its dataset SHA-256. Invalid input returns a non-zero exit code and a JSON error record.

For constructed-item records, `validate-items` checks a typed motif, ordered derivation, answer atoms, one provenance trace per atom, four unique choices, answer index, answer text, and rationale. See [`schemas/constructed-item.schema.json`](schemas/constructed-item.schema.json).

## 4. Required equipment and software

### Offline reproduction

No GPU, camera, scanner, or model-serving machine is required. Minimum practical setup:

- Linux, macOS, or Windows with a shell;
- Python **3.10 or later**;
- [`uv`](https://docs.astral.sh/uv/) (recommended) or Python `pip`;
- approximately 1 GB free disk and 2 GB RAM for the synthetic workflow.

The offline workflow makes no network request and uses only the synthetic, rights-cleared fixtures committed here.

### Remote execution

Additionally required:

- network access to a trusted endpoint;
- an OpenAI-compatible provider and available model;
- multimodal model support when using `full_pixels`;
- a valid environment-supplied credential and provider quota.

The runner is CPU-light and does not require a local GPU. Local-model hardware requirements are determined by that model and are not bundled by this repository.

### Preparing visual input

For `full_pixels`, provide a valid PNG embedded in the package. The package records media type, byte length, dimensions, SHA-256, and provenance. Any upstream scanner, OCR, layout parser, or image encoder is outside this repository; retain rights documentation for external material.

## 5. Installation

Using `uv`:

```bash
uv sync --extra test
```

Using `pip`:

```bash
python -m pip install -e '.[test]'
```

This installs the `ecm-tqag` command-line entry point.

## 6. Quick start: input → TQA output

There are two supported workflows:

### A. Generate a TQA item from a normalized document (offline)

Prepare one JSON document that follows
[`schemas/normalized-document.schema.json`](schemas/normalized-document.schema.json).
It must contain a document ID, typed layout nodes/edges, and at least one
supported evidence motif. Then run:

```bash
ecm-tqag generate path/to/document.json output/
ecm-tqag validate-generated output/ --source path/to/document.json
```

The command writes a generated TQA item, matched evidence packages for
`text_only`, `text_layout`, and `full_pixels` when available, and a manifest
with SHA-256 receipts. The included examples are runnable immediately:

```bash
ecm-tqag generate fixtures/documents/layout.json run-output/generated-layout
```

This workflow is deterministic and uses no model or network. It is intended
for the documented normalized JSON input, not for arbitrary PDF files.

### B. Run an answerer on evidence packages (offline or with a model)

Prepare a directory of JSON evidence packages following
[`schemas/condition-package.schema.json`](schemas/condition-package.schema.json),
then create a run configuration containing:

- `packages`: the package directory;
- `conditions`: one or more of `text_only`, `text_layout`, `full_pixels`;
- `output`: where to write the run summary;
- `mode`: `offline` or `openai-compatible`.

Run it with:

```bash
ecm-tqag run path/to/config.json
ecm-tqag verify-run path/to/summary.json --config path/to/config.json
ecm-tqag export-dataset path/to/summary.json path/to/dataset.jsonl
```

In `offline` mode, the runner validates the packages and produces a
structural test answer; it does not call a model. In `openai-compatible` mode,
add `endpoint`, `model`, and `api_key_env` to the config, export the named API
key in the environment, and run the same command:

```bash
export ECM_TQAG_API_KEY='your-key'
ecm-tqag run configs/openai-compatible.local.json
```

The output is a JSON summary containing one answer record per package and
condition, package/config receipts, and a summary SHA-256.

## 7. Reproduce the complete offline software check

Run from the repository root:

```bash
uv run pytest
uv run ecm-tqag validate fixtures/packages
uv run ecm-tqag validate-items fixtures/constructed-items
uv run ecm-tqag run configs/offline-example.json
uv run ecm-tqag verify-run run-output/summary.json \
  --config configs/offline-example.json
uv run ecm-tqag export-dataset run-output/summary.json run-output/dataset.jsonl
python tools/machine_semantic_audit.py --repo . --output machine-policy-audit.json
```

Successful commands return exit code `0`; malformed input or failed verification returns non-zero. The offline runner does not call a model or make a network request.

## 8. Command reference

| Command | Input | Output/check |
|---|---|---|
| `ecm-tqag validate <directory>` | Evidence-package directory | Package report and canonical receipts |
| `ecm-tqag validate-items <directory>` | Constructed-item JSON directory | Item report and receipts |
| `ecm-tqag parse <file>` | JSON or SSE response file | Parsed records; no semantic validation |
| `ecm-tqag run <config>` | Run configuration plus packages | Summary with answer records and receipt |
| `ecm-tqag verify-run <summary>` | Summary, optionally config/packages | Structural and receipt verification |
| `ecm-tqag export-dataset <summary> <output>` | Verified summary | Deterministic JSONL answer output |

Detailed semantics are documented in [`docs/cli.md`](docs/cli.md).

### 7.1 End-to-end generator

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

### 7.2 Conference contract diagnostic

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

## 9. Repository layout

```text
src/ecm_tqag/                Installable library and CLI
schemas/                     JSON Schemas for packages, items, receipts, and runs
fixtures/packages/           Synthetic T/TL/TLV evidence packages
fixtures/constructed-items/  Synthetic traceable constructed item
configs/                     Offline config and non-routable remote template
tests/                       Unit and integration tests
docs/                        CLI, fixture, and reproducibility documentation
tools/                       Deterministic release-boundary audit
artifacts/stage_a_model_evaluation/
                             De-identified Stage A ratings and reproducible model-family agreement summary
artifacts/stage_b_model_evaluation/
                             De-identified Stage B trace ratings and reproducible agreement summary
```

### Stage A and Stage B model-based evaluation artifacts

The public artifacts at [`artifacts/stage_a_model_evaluation/`](artifacts/stage_a_model_evaluation/) and [`artifacts/stage_b_model_evaluation/`](artifacts/stage_b_model_evaluation/) contain de-identified protocol fields from independent GPT- and Claude-family ratings. Both model families completed 24/24 locally schema-validated Stage A ratings and 8/8 Stage B trace ratings. The included scripts deterministically regenerate the descriptive agreement summaries:

```bash
python3 artifacts/stage_a_model_evaluation/reproduce_stage_a.py
python3 artifacts/stage_b_model_evaluation/reproduce_stage_b.py
```

These are model-based protocol checks, not human/expert ratings, semantic validation, or factual/legal accuracy. Evidence text, trace text, source images, free-text notes, raw provider envelopes, credentials, and restricted materials are excluded.

## 10. Reproducibility and data boundary

The public release contains source code, schemas, documentation, and synthetic fixtures. It does not redistribute textbook PDFs, source-derived chunks, source images, historical model outputs, private experiment records, credentials, or deployment-specific endpoints. Users are responsible for obtaining permission before adding external material and for keeping restricted inputs and outputs outside public repositories.

The software checks structure and provenance completeness. Independent human or domain review is required for semantic/legal correctness, answer quality, educational usefulness, and visual-grounding claims.

## 11. Citation and license

Use the repository metadata in [`CITATION.cff`](CITATION.cff) when citing this software. Code and documentation are released under the [Apache-2.0 License](LICENSE).
