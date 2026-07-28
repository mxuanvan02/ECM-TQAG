# ECM-TQAG

ECM-TQAG is an offline, code-centric experiment repository for evaluating whether a question is answerable under progressively richer evidence conditions:

- **T** (`text_only`): text evidence
- **TL** (`text_layout`): text plus layout or structure
- **TLV** (`full_pixels`): text, layout, and an embedded visual asset

The repository provides a small standard-library implementation, strict JSON package validation, canonical SHA-256 receipts, JSON/SSE response parsing, executable synthetic fixtures, and tests. It does not require network access, API credentials, proprietary software, or source-derived images. The final study workflow is machine-only: no human annotation, review, or adjudication is used. Deterministic integrity results are reported separately from fallible, prompt-relative machine semantic judgments.

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
```

The package can also be used directly from a checkout with `PYTHONPATH=src`.

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

All included checks are offline. The synthetic fixture is an executable example, not a benchmark claim. The release contains no source-derived pilot outputs, item-level predictions, private receipts, or external annotation records. No external corpus or retrieval baseline is presented as an ICTC result.

Run the deterministic release-boundary policy audit with:

```bash
python tools/machine_semantic_audit.py --repo . --output machine-policy-audit.json
```

Despite its name, this script performs only deterministic string and release-boundary checks; it does not automate or certify semantic truth.

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

No manuscript or submission package is part of this repository. The repository is code plus synthetic, rights-cleared fixtures and schemas. Running the offline configuration generates `run-output/summary.json`; the generated summary is a reproducibility result for those fixtures, not a released source-derived dataset or a benchmark result. No commit or remote publication is performed by the local verification workflow.

## Security

Please do not add credentials, private package names, absolute local paths, or source-derived media to public fixtures. Report security issues privately to the repository maintainers.
