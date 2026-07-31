# Public synthetic fixtures

All fixtures in this directory are synthetic, rights-cleared material created for
this repository. They demonstrate the three paired evidence conditions for one
item: `T` (text), `TL` (text plus document structure), and `TLV` (text,
structure, and pixels). The `TLV` package embeds a programmatically generated
2×2 PNG as base64, allowing a clean clone to run offline.

The companion record in `../constructed-items/` demonstrates an
`ecm-tqag.constructed-item.v1` item. It records a motif, ordered derivation,
answer atoms, one source reference per atom, four choices, an answer index, and
a rationale.

```bash
uv run ecm-tqag validate fixtures/packages
uv run ecm-tqag validate-items fixtures/constructed-items
```

The reported SHA-256 receipts identify exact JSON content and support integrity
checking. They are not semantic-quality measurements.
