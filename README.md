# ECM–TQAG

Evidence-Contracted Multimodal Generation of Textbook Question–Answer Items
from Scanned Documents.

> **Superseded, and not submitted.** This tree holds the three-arm ICTC 2026
> manuscript and its public evidence. It was not submitted; the work was carried
> forward into a four-arm census on branch
> [`experiments/census-4arm`](../../tree/experiments/census-4arm), which is the
> version submitted (to ACIIDS 2027) and the one that ships a recomputation
> harness. See [`ERRATA.md`](ERRATA.md) for a mislabelled failure class in this
> manuscript and for what this release can and cannot recompute.

ECM–TQAG states evidence support as a *contract* on a single multimodal
generation call and makes that contract checkable by a deterministic verifier
that recomputes the declared evidence tuple against the per-chunk source
bundle. The contract is evaluated in a paired three-arm census in which the
prompt is the only quantity that varies.

## Layout

```
manuscript/   4-page IEEE conference manuscript (LaTeX source + built PDF)
instrument/   validator, census harnesses, aggregators, unit tests
protocol/     prospectively frozen protocol and its addenda
evidence/     sealed run reports, round ledger, corpus-prevalence audit,
              round-4 census report and audits (identifiers redacted)
```

## Build the manuscript

```bash
cd manuscript
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Produces a 4-page US-letter PDF with no undefined references and no
overfull/underfull boxes.

## Results summary

Primary evidence is the paired three-arm census over 24 figure-bearing chunks
drawn from scanned holdings of the University of Law, Hue University
(`round4_framec_census_20260816T105300Z`), one generation call per chunk and
arm, no retry or replacement. The measured outcome is mechanical admission,
decided by the verifier alone: the returned evidence tuple (question type,
verbatim text quotation, planned answer, figure hash) must recompute against
the chunk's own bundle.

| Arm | Mechanical admission |
|---|---|
| ECM (contracted) | 22/24 (0.92) |
| Direct | 16/24 (0.67) |
| Structured, no contract | 12/24 (0.50) |

Both paired contrasts are significant under exact McNemar tests with Holm
adjustment at family-wise alpha = 0.05 (p = 0.031 and p = 0.006). The
mechanism is visible in the failure structure: the dominant failure without
the contract is quotation of text rendered only inside the page image, which
no recognised text supports; it occurs ten times without the contract and
never with it.

The secondary, exploratory semantic endpoint (two arm-blind model judges)
does not separate the arms: in this material the figures largely restate
adjacent prose, so judged visual necessity is low in every arm. This is
reported as a result, not a shortfall.

## Rights and limitations

Source material is held by the University of Law, Hue University, for internal
research only. This repository contains no page images, no figure crops, no
raw provider responses, and no credentials. Chunk identifiers in the evidence
are opaque codes; the private mapping is not published. Admission certifies
source consistency, not truth, legal correctness, or pedagogical value.
