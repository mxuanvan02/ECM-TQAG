# Command-line interface

The commands below operate on explicitly supplied files and directories. They do not contact a network unless `run` is given an `openai-compatible` configuration.

## Validate condition packages

```bash
ecm-tqag validate fixtures/packages
```

`validate` recursively checks JSON files below the specified directory. It enforces the package contract, condition-specific evidence rules, embedded-PNG integrity, and canonical package digests.

## Parse a response file

```bash
ecm-tqag parse response.json
ecm-tqag parse response.sse --content-type text/event-stream
```

`parse` accepts JSON objects/arrays or SSE `data:` events and ignores a terminal `[DONE]` marker. It performs parsing only; it does not validate provider semantics.

## Run an experiment

```bash
ecm-tqag run configs/offline-example.json
```

Offline mode validates request construction and output/receipt handling without claiming model quality. `openai-compatible` mode requires an explicit HTTPS or HTTP endpoint, model name, and the name of an environment variable containing the credential. The configured endpoint is trusted by the user and receives the evidence packages and authorization header; do not use an untrusted endpoint.

## Verify a generated summary

```bash
ecm-tqag verify-run ../run-output/summary.json
```

`verify-run` checks the summary's canonical digest, structural contract, answer contracts, and duplicate identities. It is an integrity check for that summary. It does not independently re-run a remote model or establish semantic correctness.

Successful commands return zero. Invalid input or failed verification returns a nonzero status and a JSON error record.
