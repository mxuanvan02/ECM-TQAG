# Rights and limitations

## What this directory contains

Item-level **derived** records: per (chunk, arm) gate verdicts, per-item graded
correct/incorrect decisions for both ablation branches, and per (chunk, arm)
rater scores on five ordinal criteria plus one boolean flag. These are
item-level outputs, and they are published deliberately, because the paper's
endpoints cannot be recomputed without them.

## What this directory does not contain

No source text and no source images:

- page images and figure crops (copyright: University of Law, Hue University);
- raw provider responses;
- `object.text_evidence_quote` -- the verbatim span quoted from a textbook page;
- `object.question`, `object.answer`, `object.visual_evidence` -- generated text
  carrying source terminology; the answer is published as graded booleans;
- `returned.answer` -- the answerer's own text, likewise published as graded
  booleans;
- `object.rationale` from the raters, which quotes the item and its evidence;
- the owner authorisation conversation quoted in the sealed authorisation files.

Every removal is recorded in `records/protocol.json` under `fields_redacted`,
and `MANIFEST.json` under `not_redistributed`.

## Redaction rule

Any string carrying Vietnamese diacritics was treated as source-derived or
private and was not emitted. The builder fails closed on that check, so a
release containing such a string cannot be produced.

## What a passing verification does and does not establish

`verify_reported_quantities.py --check` establishes that every quantity printed
in the manuscript follows arithmetically from these records. It does not
establish semantic correctness of an item, legal accuracy of a quotation,
pedagogical value, or generalisation beyond this frame. Admission certifies that
the declared evidence recomputed against its own source bundle; it does not
certify that the item is a good question.

## Reuse

Anyone adding external documents to this protocol is responsible for confirming
redistribution rights for that material first.
