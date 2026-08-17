# ECM–TQAG — submission package

IEEE conference manuscript presenting ECM–TQAG: a protocol for generating
evidence-grounded multimodal question–answer items from scanned documents,
together with the paired three-arm experiment that measures it.

## Contents

- `main.tex` — abstract, introduction and related work, method, experimental
  setup, conclusion, data availability
- `results/final_results.tex` — census outcomes, mechanical admission,
  failure structure
- `results/final_discussion.tex` — discussion and limitations
- `figure_ecm_tqag_method.pdf` / `.py` — Fig. 1, the data pipeline and
  architecture in one icon-style schematic (scanned corpus, OCR, figure
  crops, bundle, arm prompt, contracted call, gate, admission, blind
  judging), plus its generator script
- `references.bib`, `IEEEtran.cls`, `IEEEtran.bst` — bibliography and template

## Build

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

A clean rebuild reports no undefined citations or references and no overfull or
underfull boxes.

## Contribution

The contribution is the ECM–TQAG protocol: evidence support and visual
dependence are stated as a contract on the generation call, and that contract
is made verifiable by recomputing the declared evidence tuple against the
per-chunk source bundle. The protocol is specified together with the endpoints
it is measured by, so a paired contrast that varies only the prompt attributes
any endpoint difference to the contract alone.

Two endpoints are reported, and they answer different questions.

Mechanical admission is decided by the verifier alone, with no rater in the
loop. The contract raises it from 0.67 and 0.50 to 0.92, and both paired
contrasts are rejected under Holm control at family α = 0.05. The mechanism is
visible in the failures: the dominant failure without the contract is a
quotation copied from lettering rendered inside the page image, which no
recognised text supports. It occurs ten times without the contract and never
with it.

The derived endpoint, which additionally requires two blind judges to score
evidence correctness, visual necessity and answerability at 3 or above, does not
separate the arms. Judged visual necessity is low in every arm, and in this
material figures largely restate adjacent prose rather than carry information
absent from it. A contract on the generation call cannot create a dependence the
source pages do not contain. This is reported as a result, not as a shortfall.

The judged criteria are secondary and exploratory: inter-rater agreement is
modest and they are not calibrated against blinded human ratings.

## Manuscript content scope

The manuscript reports scientific content only: task and motivation, protocol,
analysis frame and endpoints, observed results with denominators and
uncertainty, failure structure, and interpretation boundaries.

Internal execution material is excluded from the manuscript and kept in the
private execution records: cost accounting, authorisation chains, provider
routing and identifiers, and retry or interruption bookkeeping. Excluding this
material changes no reported scientific value.

## Evidence boundary

All reported numbers derive from the executed census over the 24-chunk frame.
Source material is held by the University of Law, Hue University; page images,
credentials, and raw provider responses are not distributed.
