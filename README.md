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

## 6. Reproduce the complete offline software check

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

## 7. Command reference

| Command | Input | Output/check |
|---|---|---|
| `ecm-tqag validate <directory>` | Evidence-package directory | Package report and canonical receipts |
| `ecm-tqag validate-items <directory>` | Constructed-item JSON directory | Item report and receipts |
| `ecm-tqag parse <file>` | JSON or SSE response file | Parsed records; no semantic validation |
| `ecm-tqag run <config>` | Run configuration plus packages | Summary with answer records and receipt |
| `ecm-tqag verify-run <summary>` | Summary, optionally config/packages | Structural and receipt verification |
| `ecm-tqag export-dataset <summary> <output>` | Verified summary | Deterministic JSONL answer output |

Detailed semantics are documented in [`docs/cli.md`](docs/cli.md).

## 8. Repository layout

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
```

### Stage A model-based evaluation artifact

The public artifact at [`artifacts/stage_a_model_evaluation/`](artifacts/stage_a_model_evaluation/) contains de-identified protocol fields for 24 frozen items rated independently by GPT- and Claude-family models. Both runs completed 24/24 locally schema-validated ratings. The included script deterministically regenerates the descriptive agreement summary:

```bash
python3 artifacts/stage_a_model_evaluation/reproduce_stage_a.py
```

These are model-based protocol checks, not human/expert ratings, semantic validation, or factual/legal accuracy. Evidence text, source images, free-text notes, raw provider envelopes, credentials, and restricted materials are excluded.

## 9. Reproducibility and data boundary

The public release contains source code, schemas, documentation, and synthetic fixtures. It does not redistribute textbook PDFs, source-derived chunks, source images, historical model outputs, private experiment records, credentials, or deployment-specific endpoints. Users are responsible for obtaining permission before adding external material and for keeping restricted inputs and outputs outside public repositories.

The software checks structure and provenance completeness. Independent human or domain review is required for semantic/legal correctness, answer quality, educational usefulness, and visual-grounding claims.

## Citation and license

Use the repository metadata in [`CITATION.cff`](CITATION.cff) when citing this software. Code and documentation are released under the [Apache-2.0 License](LICENSE).
