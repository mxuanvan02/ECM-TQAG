# ECM–TQAG

Evidence-Contracted Multimodal Generation of Textbook Question–Answer Items
from Scanned Documents (ICTC 2026 submission package).

ECM–TQAG states evidence support and visual dependence as a *contract* on a
single multimodal generation call, and makes that contract checkable by a
deterministic verifier that recomputes the declared evidence tuple against the
per-chunk source bundle. The contract is evaluated in a paired three-arm census
in which the prompt is the only quantity that varies.

## Layout

```
manuscript/   4-page IEEE conference manuscript (LaTeX source + built PDF)
instrument/   round-2 validator, census harnesses, aggregators, unit tests
protocol/     prospectively frozen protocol and its two addenda
evidence/     sealed run reports, round ledger, corpus-prevalence audit
```

## Build the manuscript

```bash
cd manuscript
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Produces a 4-page US-letter PDF with no undefined references and no
overfull/underfull boxes.

## Results summary

Primary evidence is the round-1 census (`successor_full_census_20260814T213500Z`),
16 chunks × 3 arms, intention-to-test denominator 16 per arm:

| Arm | Gate admission | Valid yield | 95% CP CI |
|---|---|---|---|
| ECM full | 6/16 | 0/16 | [0.000, 0.206] |
| Direct | 5/16 | 1/16 | [0.002, 0.302] |
| Structured no-contract | 3/16 | 0/16 | [0.000, 0.206] |

Neither confirmatory contrast rejected its null (exact McNemar, Holm-adjusted,
*p* = 1.000 both).

A prospective replication (`round2e_...`) repaired two measurement defects
without altering the gate or the endpoint, and substituted both judge families
after a provider outage. Admission rose to 12/16, 7/16, 10/16 while valid yield
stayed at or below 1/16 in every arm. The ECM margin over the structured prompt
narrowed from 6-vs-3 to 12-vs-10, so a substantial part of the round-1
structural advantage was an artefact of an unstated indexing convention in our
own contract rather than an effect of the intervention.

## Reproducibility and honesty of the evidence trail

`evidence/ROUND_LEDGER.json` records every executed round with an explicit
validity status, including the rounds that must **not** be read as evidence:

- **round 2** — quarantined. Two concurrent writers issued 152 paid calls for 84
  tasks; 68 tasks were double-called and 4 of those disagreed between their two
  calls, violating the zero-retry rule. Root cause: the transport ledger
  de-duplicates in-process only. Fixed by an `flock` run lock plus an `O_EXCL`
  per-task claim.
- **round 2b** — generation valid, endpoint void. The Claude judge route returned
  HTTP 503 on 17 of 18 calls, so only 1 of 18 candidates received both judges.
- **round 2d** — invalid for arm comparison. A pre-declared validity check found
  that a long clarification appended identically to all three arms induced
  arm-dependent decoder degeneration (7/16 direct and 4/16 structured
  whitespace-degenerate responses, 0/16 ECM), inflating the ECM margin. The
  repair was redesigned in minimal, arm-neutral form for round 2e, which passed
  the same check at 0/16 in every arm.

Each of these is sealed in place under `evidence/runs/<run>/` rather than
deleted.

## Corpus prevalence audit

`evidence/CORPUS_PREVALENCE.json` quantifies the binding constraint on a
denominator independent of the census. Across four complete Vietnamese-law
textbooks classified page by page, 4 of 2167 pages carry a diagram at all
(0.185%, exact 95% interval [0.050%, 0.472%]); screening vector-rich candidate
pages raises the yield only to 31 of 437 (7.1%, [4.9%, 9.9%]). Diagram presence
is necessary but not sufficient for visual necessity, so these rates bound from
above the fraction of this material on which a multimodal-necessity criterion
could be met.

Intervals use exact Clopper–Pearson by beta inversion, cross-checked against the
project's own finite-sum implementation at *n* = 16 and *n* = 30 (maximum
absolute difference 4.2e-16). The project implementation overflows at corpus
scale and was deliberately left unmodified.

## Not distributed

Copyrighted textbook page images, the dataset manifest containing verbatim
source excerpts, raw provider responses, credentials, and provider cost and
authorisation records are excluded from this repository.
