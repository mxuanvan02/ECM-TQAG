# ECM–TQAG ICTC 2026 — submission package

Four-page IEEE conference manuscript presenting ECM–TQAG as a method:
an evidence contract on one multimodal generation call, made checkable by
a deterministic verifier, and measured by a paired three-arm census.

## Contents

- `main.tex` — abstract, introduction and related work, method, experimental
  setup, conclusion, data availability and limitations
- `results/final_results.tex` — gate admission, primary endpoint,
  confirmatory contrasts, failure structure, judged vectors, instrument
  robustness (second-round replication)
- `results/final_discussion.tex` — discussion
- `figure_ecm_tqag_method.pdf` / `.py` — Fig. 1, the method composition
  (conditioning bundle, arm prompt, contracted call, gate, blind dual
  judging), plus its generator script
- `references.bib`, `IEEEtran.cls`, `IEEEtran.bst` — bibliography and template

## Build

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Produces a 4-page US-letter PDF, no overfull or underfull warnings.

## Contribution

The contribution is the ECM–TQAG method: evidence support and visual
dependence are stated as a contract on the generation call, and that
contract is made verifiable by recomputing the declared evidence tuple
against the per-chunk source bundle. The method is specified together with
the derived intention-to-test endpoint it is measured by, so a paired
contrast that varies only the prompt attributes any endpoint difference to
the contract alone.

The bounded census finds that the contract improves gate admission
(6/16 vs. 5/16 and 3/16) while end-to-end valid yield stays at 0–1/16 for
every arm, with the visual necessity of the source images as the binding
constraint. No superiority, equivalence, or population-generalisation
claim is made.

A prospective second round re-executed the same frame after two
measurement-validity corrections that leave the gate and the endpoint
unchanged: substituted judge families, and a prompt statement of the
option-indexing convention the frozen contract had left unspecified.
Admission rose in every arm (12/16, 7/16, 10/16) and the ECM margin over
the structured prompt narrowed from 6-vs-3 to 12-vs-10, so part of the
first-round structural advantage was an artefact of our own
specification. The endpoint conclusion replicated: valid yield stayed at
or below 1/16 in every arm and judged visual necessity stayed low.

## Manuscript content scope

The manuscript reports scientific content only: task and motivation,
method, analysis frame and endpoints, observed results with denominators
and uncertainty, failure structure, and interpretation boundaries.

Internal execution and process material is excluded from the manuscript and
kept in the private execution records: provider cost accounting,
authorisation chains, provider-qualification reporting, retry and
interruption bookkeeping, internal infrastructure and routing, and internal
run identifiers. Excluding this material changes no reported scientific
value.

## Evidence boundary

All reported numbers derive from the executed 16-chunk censuses.
Copyrighted page images, credentials, and raw provider responses are not
distributed.

Two execution attempts are excluded from the manuscript and sealed as
non-evidence in the private records: one whose transport ledger showed
duplicate paid calls for the same tasks, and one whose reported arm
contrast was invalidated by a pre-declared validity check. Neither
contributes any reported value.
