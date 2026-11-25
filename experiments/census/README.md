# Four-arm census and text-only ablation

Released records and analysis code for the ECM–TQAG census reported in the
ACIIDS 2027 submission (Springer LNCS/LNAI). Every quantity in the paper
recomputes from what is in this directory, with no network access and no model
calls.

## Verify the paper's numbers

```bash
cd experiments/census
python3 verify_reported_quantities.py            # print every recomputed quantity
python3 verify_reported_quantities.py --check    # assert them against the paper
```

`--check` exits non-zero if any published value fails to reproduce. It needs
only the Python standard library.

What the script recomputes from the raw task records, rather than reading from a
summary file:

- admission per arm and Clopper–Pearson exact 95% intervals
- the three confirmatory paired contrasts (exact McNemar) and Holm step-down
- the auxiliary GATE-against-DIR contrast
- the thresholded endpoint `V` and the visual-necessity score distribution
- quadratic weighted kappa, exact agreement and within-one agreement per criterion
- the text-only ablation for both answerers, including the pre-registered
  grading rule applied to each response
- agreement between the two answerers, and measured against rated necessity

The failure taxonomy is read from `FAILURE_ATTRIBUTION.json` because tracing a
quotation to its source channel needs the page images, which are not
redistributable (see below).

## Layout

```
code/          the census instrument: gate, contracts, runner, transport, scripts
records/
  protocol/    the frozen prompt contract and ablation preregistration
  frame/       the dataset manifest defining the 24-chunk frame
  census/      run plan, preflight, qualification, report, results summary,
               failure attribution, and 288 task records
  ablation/    ablation report and 272 task records
```


## What is not released, and why

- **Scanned page images and figure crops.** Copyright of the University of Law,
  Hue University. Held internally, not redistributed.
- **Raw provider response payloads.** Withheld with the source material they
  quote. The graded outcome of every response is in the task records, so the
  analysis is reproducible without them.
- **Credentials and provider identifiers.**

Task records carry the generated items themselves, including each declared
quotation. The longest such quotation is 690 characters; no record contains a
page's full text layer.

## Scope of the claim

Admission certifies that an item's declared evidence recomputes against its own
source bundle. It does not certify that the item is answerable, pedagogically
sound, or that its figure is necessary. The judged endpoints are secondary and
below their pre-registered floor of 40 chunks, so they carry no significance
claim. The contract-against-disclosure contrast is unresolved at this frame
size and is reported as such.
