# ECM-TQAG final experiment software

This public subproject contains the final six-arm implementation, protocol, tests, controls, and statistics code. The committed dataset is synthetic and rights-cleared, solely for contract verification; the private textbook corpus, page images, provider responses, credentials, and run ledgers are excluded.

## Offline check

```bash
python -m pip install -e ".[test]"
python -m pytest -q
python dry_run.py --manifest dataset/dataset_manifest.json --out runs/freeze_synthetic
```

Live execution requires authorized local data and credentials supplied outside Git.
