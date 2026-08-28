# Errata and status notice — ICTC 2026 release

**Status: superseded, and not submitted.** This release describes a three-arm
census (24 chunks, 72 chunk–arm attempts) of run
`round4_framec_census_20260816T105300Z`. The work was carried forward into a
four-arm census with a gate-disclosed control arm, a two-answerer ablation, and a
recomputation harness, released on branch
[`experiments/census-4arm`](../../tree/experiments/census-4arm). The manuscript in
this branch was not submitted; the four-arm manuscript is the one submitted, to
ACIIDS 2027.

This file is additive. No manuscript byte, evidence file, or record in this
release has been altered.

## 1. Mislabelled failure class in `results/final_results.tex`

The Results section states:

> The remaining four quotations are composed or paraphrased rather than copied,
> spread across the three arms.

That label is not what the release's own evidence says. In
`evidence/round4/ROUND4_FAILURE_ATTRIBUTION_AUDIT.json`, those four attempts are
classified `unresolved`, with:

- `definition`: "Quote absent from text layer and not recovered by crop OCR
  (overlap 0.0-0.17)."
- `caveat`: "Probably also image-quoting: two are syllogism conclusion lines and
  one is a diagram label, which tesseract failed to read off the diagram. NOT
  counted as confirmed image-quoting because the OCR evidence is absent."
- `by_arm`: direct 2, `ecm_full` 1, `structured_no_contract` 1

The count of four is correct. The label asserts a determination the record
explicitly declines to make, and it runs in the paper's favour: "composed or
paraphrased" reads as a wording failure, whereas the record's own stated guess is
image-rendered quotation — the failure mode the contract exists to prevent — and
one of the four sits in the contract arm.

Wording that the evidence supports:

> The remaining four quotations were recovered from neither the text layer nor an
> optical reading of the figure crops, so their channel is unresolved; the audit
> notes that image-rendered text is the likely source of three of them.

The taxonomy totals are unaffected: 18 quotation violations decompose as 10
image-quoting (direct 4, structured 6, contracted 0), 4 case-only false rejects,
and these 4 unresolved.

## 2. The headline p-values are not recomputable from this release alone

The manuscript reports exact McNemar p = 0.031 against the direct arm and
p = 0.006 against the structured arm. Those tests need the per-chunk admission
matrix. `evidence/round4/ROUND4_REPORT.json` publishes only the per-arm marginals
(`generation_pass_per_arm`: contracted 22, direct 16, structured 12) and no
per-chunk admission list, so a reader holding this release can confirm the
marginals but cannot reconstruct the discordant pairs behind either p-value.

The `contrasts` field in that report is *not* the admission contrast. It carries
the secondary judged endpoint (both entries p = 1.0), which is a different
quantity from the mechanical admission contrasts quoted in the manuscript.
Reading `contrasts` as the admission test would be a misreading of the file.

The four-arm branch does not have this gap: it ships the per-chunk task records
and `verify_reported_quantities.py`, which recomputes every reported quantity
from those records and asserts it, exiting non-zero on any mismatch.

## 3. What was checked and does hold

Recomputed against this release's own evidence: admission marginals 22/16/12,
the 18/2/2 split of the 22 terminal failures, quote classes 8 exact and 42
normalised of 50 admitted, the three failure splits above, and the case-folding
counterfactual 23/17/14. The item-quality audit in
`evidence/round4/ROUND4_ITEM_QUALITY_AUDIT.json` carries its own status flag,
`ASSISTANT_READING_NOT_THE_PREREGISTERED_HUMAN_REVIEW`, and its per-item records
are withheld from the public release, so its measures cannot be independently
recomputed here either.
