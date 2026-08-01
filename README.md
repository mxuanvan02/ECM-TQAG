# ECM-TQAG

ECM-TQAG is research software for **evidence-first construction of traceable multimodal textbook question-answering (TQA) items**. It provides public contracts, validators, deterministic receipts, and synthetic fixtures for implementing and auditing the construction process; it is not a release of the source textbook corpus or experimental model outputs.

The method represents a construction path as

\[
G_m \rightarrow z \rightarrow (A, \Gamma) \rightarrow q \rightarrow \mathcal{C},
\]

where a matched document-graph motif \(G_m\) and a restricted derivation \(z\) produce answer atoms \(A\) and item-level provenance traces \(\Gamma\) before a multiple-choice question \(q\) is realised and checked by \(\mathcal{C}\).

## Research artifact scope

This repository implements three methodological artifacts:

1. **Source-grounded evidence representation.** Evidence packages encode text (`T`), text with document structure (`TL`), and text with structure plus a visual asset (`TLV`) while retaining package identity and integrity receipts.
2. **Evidence-first item contract.** A constructed item records its motif, restricted derivation, answer atoms, one provenance trace per atom, four answer choices, answer index, answer text, and rationale.
3. **Deterministic structural verification.** Validators check package and item contracts, canonical SHA-256 receipts, run summaries, and deterministic exports.

The implementation verifies structural and provenance-recording invariants. It does not independently establish semantic correctness, legal accuracy, pedagogical value, distractor quality, or whether a modality is necessary for an item.

## Installation

Requires Python 3.10 or later. The commands below use [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra test
```

Alternatively:

```bash
python -m pip install -e '.[test]'
```

## Reproduce the offline checks

All fixtures committed to this repository are synthetic and the default workflow is offline.

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

The offline runner exercises request construction, receipt generation, and verification. It does not call a model or make a network request.

## Optional remote execution

Remote execution is opt-in. No endpoint, API key, or model identifier is stored in the repository. Start from the intentionally non-routable template:

```bash
cp configs/openai-compatible.template.json configs/openai-compatible.local.json
```

Edit only the local copy: replace the endpoint and model placeholders, and choose the name of an environment variable that holds the credential. Export that variable in your shell, then run:

```bash
uv run ecm-tqag run configs/openai-compatible.local.json
```

`*.local.json`, private configuration files, and `.env` files are ignored by Git. Never commit credentials or a deployment-specific endpoint. In `openai-compatible` mode, the configured endpoint receives the selected evidence package and authorization header; use only an endpoint you trust.

## Evidence conditions

| Symbol | Repository condition | Exposed evidence |
|---|---|---|
| `T` | `text_only` | textual chunk evidence |
| `TL` | `text_layout` | text and declared document structure |
| `TLV` | `full_pixels` | text, structure, and an embedded visual asset |

`TLV` assets are checked for media type, byte length, dimensions, and SHA-256. The committed fixtures use only synthetic, rights-cleared content.

## Core commands

| Command | Purpose |
|---|---|
| `ecm-tqag validate <directory>` | Validate `T`, `TL`, and `TLV` evidence packages and their receipts. |
| `ecm-tqag validate-items <directory>` | Validate constructed-item structure and atom--trace correspondence. |
| `ecm-tqag parse <file>` | Parse JSON or server-sent-event response payloads. |
| `ecm-tqag run <config>` | Run an offline transport check or an explicitly configured remote experiment. |
| `ecm-tqag verify-run <summary>` | Verify a run summary, receipts, and package identities. |
| `ecm-tqag export-dataset <summary> <output>` | Verify a summary and write deterministic JSON Lines. |

Detailed command semantics are in [docs/cli.md](docs/cli.md). Public JSON Schemas are in [schemas/](schemas/).

## Repository layout

```text
src/ecm_tqag/                Installable library and command-line interface
schemas/                     JSON Schemas for packages, items, receipts, and runs
fixtures/packages/           Synthetic T/TL/TLV evidence packages
fixtures/constructed-items/  Synthetic traceable constructed item
configs/                     Offline config and non-routable remote template
tests/                       Unit and integration tests
docs/                        CLI and fixture documentation
tools/                       Deterministic release-boundary audit
```

## Data governance and reproducibility boundary

The public release contains code, schemas, documentation, and synthetic fixtures only. It does not redistribute textbook PDFs, source-derived chunks, source images, historical model outputs, private experiment records, endpoints, or credentials. Researchers using external material are responsible for obtaining redistribution permission and for maintaining provenance records for their local data.

See [RIGHTS_AND_LIMITATIONS.md](RIGHTS_AND_LIMITATIONS.md) for the release boundary.

## Citation

Use the repository metadata in [CITATION.cff](CITATION.cff) when citing this software. The associated manuscript source is distributed separately from this code repository.

## License

Code and documentation are released under the [Apache-2.0 License](LICENSE).

## Manuscript

The public manuscript source, compiled PDF, figures, evaluation guide, and results summary are available in [`manuscript/`](manuscript/). The manuscript package is intentionally separate from the software implementation and contains no source textbook corpus, page images, private model records, credentials, or restricted data.
