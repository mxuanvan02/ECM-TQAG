# Public fixtures

The fixture set is entirely synthetic and created for this repository. It represents one item under T, TL, and TLV conditions. The 2×2 PNG in the TLV JSON is programmatically generated and embedded as base64 so a clean clone is self-contained.

Run validation with:

```bash
ecm-tqag validate fixtures/packages
```

A successful report contains three packages and a deterministic `package_sha256` receipt for each package. These receipts identify exact JSON content; they are not model-quality measurements.
