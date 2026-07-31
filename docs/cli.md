# Command-line interface

The commands below operate on explicitly supplied files and directories. They do
not contact a network unless `run` is given an `openai-compatible`
configuration.

## Validate evidence packages

```bash
ecm-tqag validate fixtures/packages
```

`validate` recursively checks JSON files below the specified directory. It
enforces the `T`, `TL`, and `TLV` package contract, condition-specific evidence
rules, embedded-PNG integrity, and canonical package receipts.

## Validate evidence-first constructed items

```bash
ecm-tqag validate-items fixtures/constructed-items
```

`validate-items` checks the structural ECM–TQAG item contract: a typed motif,
an ordered derivation, answer atoms, one provenance trace per atom, four unique
choices, an answer index, an answer matching that index, and a rationale. It
returns a canonical receipt for every item. This command verifies structural and
provenance completeness; it does not determine factual or legal correctness.

## Parse a response file

```bash
ecm-tqag parse response.json
ecm-tqag parse response.sse --content-type text/event-stream
```

`parse` accepts JSON objects/arrays or SSE `data:` events and ignores a
terminal `[DONE]` marker. It performs parsing only; it does not validate provider
semantics.

## Run an experiment

```bash
ecm-tqag run configs/offline-example.json
```

Offline mode validates request construction and output/receipt handling without
claiming model quality. `openai-compatible` mode requires an explicit HTTP(S)
endpoint, model name, and the name of an environment variable containing the
credential. The configured endpoint is trusted by the user and receives the
evidence packages and authorization header; do not use an untrusted endpoint.

## Verify a generated summary

```bash
ecm-tqag verify-run run-output/summary.json --config configs/offline-example.json
ecm-tqag export-dataset run-output/summary.json run-output/dataset.jsonl
```

`verify-run` checks the summary's canonical receipt, structural contract, answer
contracts, and duplicate identities. `export-dataset` verifies first and then
writes deterministic JSON Lines. Neither command independently re-runs a remote
model or establishes semantic correctness.

Successful commands return zero. Invalid input or failed verification returns a
nonzero status and a JSON error record.
