# ECM-TQAG final experiment software

This public subproject contains the final six-arm implementation, protocol, tests, controls, and statistics code. The committed dataset is synthetic and rights-cleared, solely for contract verification; the private textbook corpus, page images, provider responses, credentials, and run ledgers are excluded.

## Offline check

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python dry_run.py --manifest dataset/dataset_manifest.json --out runs/freeze_synthetic
```

## Prospective R6 ROI contract

The public-safe R6 successor adds deterministic target-conditioned ROI addressing and synthetic fail-closed tests. See [`R6_ROI_ADDENDUM.md`](R6_ROI_ADDENDUM.md). Paid runners, private corpora, provider responses, run ledgers, safety freezes, and authorization artifacts remain outside this repository.

Live execution requires authorized local data and credentials supplied outside Git.
