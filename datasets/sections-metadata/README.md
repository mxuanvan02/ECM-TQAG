# Section dataset — metadata-only companion

`section_dataset_companion.json` describes the section-level ECM input dataset
without carrying any of its copyrighted content.

## What is here

Per contributing document: id, source sha256, page count, sections detected,
units built, and whether it is in scope.

Per chunk: chunk id, document id, question type, condition, split, section
label, ancestor depth, the pages carrying a figure region, the section's page
span, the section's character count, figure cues, and for every figure crop its
dimensions, byte size, sha256 and whether it is an embedded raster or a rendered
vector region. Plus two counts from the figure-text channel: how many words
passed the confidence gate, and how many of those are surplus.

## What is deliberately absent

No section prose. No recognised figure word. No image bytes. The builder that
produces this file refuses to write if any of those appear in its output — a
check on the emitted bytes, not a promise in a comment.

## Why

Source PDFs, extracted prose and figure crops are the copyright of the issuing
institutions and are held under an internal-research basis that does not permit
redistribution. `RIGHTS_AND_LIMITATIONS.md` states that this repository ships no
source-derived document images, and that statement stays true.

The companion exists so the published record is auditable anyway: chunk counts,
gate outcomes, provenance hashes and figure geometry are all verifiable from it,
and the crop hashes let anyone holding the sources confirm they reproduce the
same bytes.

## Frames

Two frames are described, under two readings of the frozen crop rule:

- `frame_d_strict` — embedded rasters only, the frozen operationalisation.
- `frame_d_vector` — any crop on disk, the literal text of the rule.

Neither is pre-registered and neither authorises a paid run. The companion
records `reaches_floor` per frame so a reader can see which counts clear the
pre-registered floor without having to trust a summary.

## Rebuilding

`tools/section_dataset/` holds the full toolchain, including
`build_public_dataset_companion.py`, which regenerates this file from the
private manifest.
