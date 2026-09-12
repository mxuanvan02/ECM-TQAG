# ACIIDS strong-revision audit supplement

This directory adds rights-cleared analysis and audit materials for the ACIIDS manuscript revision. It does **not** modify the sealed five-arm records or their `MANIFEST.json`.

## Contents

- `verify_revision_quantities.py`: recomputes the post-hoc revision analyses from `../records/` only, including exact admission intervals, answer-in-question sensitivity, and admission-plus-correctness sensitivity.
- `reference/ecm_v2_gates.py`: byte-identical historical gate implementation, retained under its protocol-bound SHA-256.
- `reference/ecm_v2_prompt.py`: available prompt reference revision; its hash does not match the sealed census prompt hash, as documented by the PARA preflight.
- `audit/`: synthetic, rights-cleared fixtures and tests documenting the implemented scope of G6–G8.
- `prospective_para/`: a no-call preflight and prospective rewording-only control protocol. **Not executed; no result is reported.**
- `human_evaluation/`: prospective arm-blind expert-evaluation protocol and blank score sheet. **Protocol only; no ratings are reported.**

## Reproduce

From `experiments/census_5arm_framef`:

```bash
python3 verify_reported_quantities.py --check
python3 revision/verify_revision_quantities.py --check
python3 -m unittest discover -s revision/audit -p 'test_*.py' -v
python3 revision/prospective_para/preflight_para.py --json
```

Expected results are 119/119 original quantities, 122/122 revision quantities, and 5/5 synthetic tests. The PARA preflight is expected to exit non-zero without the exact sealed prompt revision, authorised Frame-F bundle, and runtime credential; it performs no provider call and writes nothing.

## Interpretation limits

The historical G6 test checks literal answer absence from the declared quotation and does not inspect question text. Historical G7/G8 receive chunk-level figure lettering rather than a verified selected-crop mapping. Passing the synthetic limitation tests documents this implemented scope; it does not repair or validate the underlying construct.
