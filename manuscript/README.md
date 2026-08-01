# ECM-TQAG manuscript package

This directory contains the public manuscript source and publication figures for **ECM-TQAG: An Evidence-First Protocol for Traceable Multimodal Textbook Question Construction**.

## Contents

- `main.tex` — IEEE conference manuscript source
- `references.bib` — bibliography
- `ecm_tqag_architecture.pdf` — unified architecture and evaluation figure
- `diagnostic_answerability.pdf` — diagnostic figure
- `main.pdf` — compiled manuscript
- `manuscript_guide.md` — section-by-section interpretation guide
- `results_summary.md` — public evaluation summary

## Build

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The associated research-software repository, synthetic fixtures, schemas, and validators are available at:

<https://github.com/mxuanvan02/ECM-TQAG>

Source textbooks, page images, detailed model records, and other restricted materials are not redistributed in this package.
