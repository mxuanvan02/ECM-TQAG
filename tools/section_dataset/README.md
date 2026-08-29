# Section-level dataset toolchain

Acquisition, build, audit and packaging scripts for the section-granularity
multimodal dataset drawn from the law textbook holdings of the University of
Law, Hue University (HUL) catalogue.

The scripts are published; the dataset they build is not. Source PDFs, section
prose and figure crops are the copyright of the issuing institutions and are
held for internal research only. What ships here is the code plus the
metadata-only companion in `datasets/sections-metadata/`.

## Scope

The dataset covers **law textbooks** (*giáo trình luật*). Subject and issuing
institution are resolved from each PDF's own title and foreword pages, not from
its filename or catalogue row. Material outside that scope is relocated intact
rather than deleted, so a scope decision never destroys work.

## Pipeline order

| Stage | Script | What it does |
| --- | --- | --- |
| Discover | `discover_round19_shelf.py` | Paginated read-only OPAC scan filtered by `resourceCollection = "Kệ C2-C8 (Giáo trình)"`. The shelf is the filter; a keyword query would re-impose the author/title substring test this round exists to avoid. |
| Fetch | `fetch_round19_shelf.py` | Staging-only download. Deduplicates by content sha256 against the holdings index, because one textbook can sit under two catalogue uuids across rounds. |
| Build | `extend_datasets_round19.py` | Adds new documents to the page-level and section-level builds with **pinned** doc ids. Existing ids are never re-sorted: a positional id would renumber sealed references. |
| Scope | `apply_law_textbook_scope.py` | Relocates out-of-scope documents to a sibling root, hashing every file before and after so the move is provably lossless. |
| Figure text | `probe_ocr_fidelity.py`, `probe_region_ocr_surplus.py`, `calibrate_figure_ocr_conf.py`, `augment_figure_text.py` | Measures OCR fidelity, then applies OCR to figure regions only, as a separate channel. |
| Package | `build_ecm_input_dataset.py`, `build_public_dataset_companion.py` | Emits the private ECM input manifest and the public metadata-only companion. |
| Audit | `recheck_section_frame_determination.py`, `audit_section_frame_freshness.py`, `quantify_route_e_supply.py` | Independent rechecks. Each exits non-zero on any mismatch. |

## Why the text layer is not rebuilt from OCR

All contributing sources are born-digital (Adobe InDesign, Acrobat, Word
producers) and 86% of figure-bearing pages carry a real text layer. On 24
sampled pages, `tesseract vie+eng` at 300 dpi reaches a median CER of 1.89%
against that layer, retaining 98.3% of accented characters.

The text layer is what the typesetter emitted, so it *is* the reference.
Rebuilding it from OCR would replace an exact source with a lossy copy. OCR is
therefore applied only where the text layer holds nothing: inside figure
regions.

## The figure-text channel, and its contract

`augment_figure_text.py` renders each figure region at 400 dpi and runs
Tesseract in TSV mode to obtain per-word confidence. Words at or above
confidence 90 are kept; a word is *surplus* when it occurs in neither the page
text layer nor the surrounding section prose. Surplus words are what only the
image carries — the precondition for a question to genuinely require the image.

**Figure text is not quotable prose.** At confidence 90 roughly one word in ten
is still an OCR slip on graphical strokes. A verbatim-quote gate must read the
text-layer channel only. The manifests carry this contract as a field, not as
documentation, so a consumer cannot silently ignore it.

Confidence 90 was chosen from a measured sweep rather than assumed. The
calibration report records the full sweep, and records that its own weak
labelling understates precision: rare proper nouns absent from both lexicons
are counted as noise, so verified content such as `Trafalgar`, `Ceuta` and
`1898/QĐ-UBND` sits in the noise bucket.

## Pre-registration

`build_ecm_input_dataset.py` emits two frames under two readings of the frozen
crop rule, and marks both `paid_run_authorised: false`. Neither is a
pre-registered frame. The governing protocol fixes `n` before the first call
and forbids extending a frame after results have been seen; the wider reading
additionally needs its own determination record written before any call. The
builder therefore prepares inputs and refuses to imply authorisation.

## Running

```bash
uv run python tools/section_dataset/<script>.py --help
```

Scripts are read-only by default and write only when passed `--apply` or
`--emit`. They resolve paths relative to a private working sandbox that is not
part of this repository, so they are published as the executable record of how
the dataset was built rather than as a turnkey rebuild.
