# ECM-TQAG

ECM-TQAG is a reproducible implementation of an **evidence-first protocol for
constructing traceable multimodal textbook question-answering (TQA) items**.
The protocol requires evidence selection and answer derivation before question
wording:

\[
G_m \rightarrow z \rightarrow (A, \Gamma) \rightarrow q \rightarrow \mathcal{C},
\]

where a typed document-graph motif \(G_m\) and restricted program \(z\) yield
answer atoms \(A\) and source-region traces \(\Gamma\); only then is a
multiple-choice question realised and checked by \(\mathcal{C}\).

The accompanying study uses Vietnamese law textbooks from the legal-training
curriculum at the Institute of Open Education and Information Technology, Hue
University. The experimental input comprises eight multimodal textbook chunks
from five textbooks, associated with ten source figures or tables. Each chunk
is represented as three paired evidence packages: text (`T`), text with
document structure (`TL`), and text with document structure and original image
pixels (`TLV`), yielding 24 input packages. Those source-derived inputs are not
redistributed in this repository; the public release contains rights-cleared
synthetic fixtures that exercise the same contracts.

## What this repository provides

- strict condition-package validation for `T`, `TL`, and `TLV` evidence;
- a typed construction-item contract recording a motif, restricted derivation,
  answer atoms, provenance traces, question, options, key, and rationale;
- canonical SHA-256 receipts for package and constructed-item records;
- deterministic dataset export and run-summary verification;
- synthetic fixtures, unit tests, an offline execution configuration, and an
  OpenAI-compatible transport interface for local experiments.

The code validates provenance and structural invariants. It does not itself
certify legal correctness, semantic grounding, or the necessity of a modality.

## Evidence packages

| Symbol | Repository condition | Evidence exposed |
|---|---|---|
| `T` | `text_only` | textual chunk evidence |
| `TL` | `text_layout` | text and declared document structure |
| `TLV` | `full_pixels` | text, structure, and an embedded visual asset |

`TLV` assets are checked for media type, byte length, dimensions, and SHA-256.
Public fixtures contain only synthetic images and no host paths, credentials,
reference corpus files, or source-derived images.

## Constructed-item contract

A valid `ecm-tqag.constructed-item.v1` record includes:

- `motif`: a typed evidence pattern selected from the package;
- `derivation`: a restricted, ordered sequence of operations;
- `answer_atoms`: typed answer components derived before question wording;
- `provenance_trace`: source-region references linked one-to-one to answer
  atoms;
- a four-option question, `answer_index`, verbatim `answer`, and `rationale`.

The contract is deliberately structural: it makes every generated item
inspectable and tamper-evident without treating a receipt as a semantic-quality
score.

## Quick start

```bash
uv sync --extra test
uv run pytest
uv run ecm-tqag validate fixtures/packages
uv run ecm-tqag validate-items fixtures/constructed-items
uv run ecm-tqag run configs/offline-example.json
uv run ecm-tqag verify-run run-output/summary.json --config configs/offline-example.json
uv run ecm-tqag export-dataset run-output/summary.json run-output/dataset.jsonl
```

## Repository layout

```text
src/ecm_tqag/         installable library and CLI
fixtures/packages/    synthetic T/TL/TLV evidence packages
fixtures/constructed-items/
                       synthetic evidence-first constructed TQA item
schemas/              public JSON schemas for packages, items, and receipts
tests/                unit and integration tests
configs/              offline example configuration
docs/                 contract and fixture documentation
tools/                deterministic release-boundary audit
```

## Reproduction and data boundary

All checked-in fixtures and default tests are offline and synthetic. The
repository does not publish textbook PDFs, source-derived chunks, source images,
historical model outputs, private receipts, or credentials. Researchers with
legitimate local access to a corpus can map their material into the documented
package contract and retain their own provenance records. Users are responsible
for confirming redistribution rights before adding any external document or
image.

## License and citation

Code and documentation are licensed under Apache-2.0; see [LICENSE](LICENSE).
See [RIGHTS_AND_LIMITATIONS.md](RIGHTS_AND_LIMITATIONS.md) for release
boundaries and [CITATION.cff](CITATION.cff) for citation metadata.
