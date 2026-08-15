# Round-2 Exploratory Protocol (Hướng C) — prospective, offline draft

**Status:** DRAFT, offline-only. `paid_execution_ready=false`, `provider_qualified=false`,
no provider call is authorized by this document. Execution requires a separate
owner authorization with an explicit USD cap, per project convention.

**Parent evidence:** successor exploratory census
`runs/successor_full_census_20260814T213500Z` (round 1) and the fresh
three-call qualification (3/3 PASS). Round 1 remains the published evidence;
nothing in this document reinterprets or repairs round-1 records.

## 1. Motivation (two measurement defects, quantified offline)

Round-1 analysis (this sandbox, `audit_failure_modes3.py`,
`audit_round2_sim.py`, control-tested against the project's own
`validate_generation` oracle, 14/14 passing generations clean) identified two
measurement defects that inflate the terminal-failure denominator without
reflecting the prompt intervention:

- **D1 — over-strict verbatim/answer gates (specification artifacts).**
  Of the 32 output-contract failures, 4 are recoverable from the retained raw
  responses under a repaired contract with no change to model behavior:
  2 near-miss quotes that differ only by Unicode normalization/whitespace
  (`norm_near_miss`), and 2 in-order elisions (`"..."`-style omission whose
  retained fragments appear in source order). The remaining 28 (14
  image-derived quotes absent from the OCR text; 14 MCQ answer/option
  inconsistencies) are genuine model contract failures requiring regeneration.
- **D2 — text-sufficient corpus caps visual necessity.** 18 of 27 judge
  records score `visual_necessity < 3`; judge rationales uniformly state the
  prose alone suffices. Per-chunk round-1 necessity means range 1.17–3.50;
  chunks 48/66/230 are text-sufficient, chunks 44/4/35/33 show partial
  image-necessity. The source pool contains 24 multimodal chunks; the census
  frame used 16, so at most 8 unused multimodal chunks exist for an
  image-necessary frame, and the current manifest retains only the 16 census
  packages (a round-2 builder must rebuild TLV packages from the source pool).

## 2. Repaired contract (D1), frozen before any round-2 call

1. Verbatim gate: NFC-normalize and collapse whitespace on both quote and
   source before the substring test (exact match remains required on the
   normalized strings; no repair, no translation, no aliasing).
2. Elision tolerance: a quote whose maximal retained fragments (split on the
   model's elision markers) each appear in the source, in order and
   non-overlapping, passes as `elided_verbatim`; reported separately from
   `exact_verbatim` in the accounting.
3. MCQ answer rule unchanged (`answer == options[correct_option]`, byte-exact
   on the option text); the prompt schema text is amended to state explicitly
   that `answer` must repeat the full option string and that
   `text_evidence_quote` must be drawn from the supplied text channel, not
   from image-visible labels.
4. All other gates (schema exactness, image-hash census membership,
   non-empty fields, ITT accounting, zero retry/replacement) unchanged.

Expected offline effect on retained round-1 responses (simulation only):
gate pass 6/5/3 -> 7/7/4 of 16. Round-2 paid execution must regenerate the 28
non-recoverable failures; the simulation is a lower-bound illustration, not a
prediction.

## 3. Frame (D2)

- **Frame A (same 16 chunks):** measures the D1 repair under identical
  evidence; preserves round-1 pairing for descriptive comparison.
- **Frame B (image-necessary, optional):** rebuild TLV packages from the
  source pool; inclusion requires a prescreened image-necessity criterion to
  be specified and frozen BEFORE execution (e.g., image carries at least one
  answer-relevant atom absent from the OCR text, verified offline where
  possible). With only 8 unused multimodal chunks available, Frame B is
  underpowered for contrasts and is measurement-only.

## 4. Execution order (each phase gated, fail-closed)

1. Phase 0 (offline, free): implement repaired validator + unit tests against
   retained round-1 responses; rebuild Frame A/B packages; independent review.
2. Phase 1: fresh three-call qualification under the repaired contract
   (3 calls). STOP on first failure.
3. Phase 2: Frame A census, 48 generation attempts; judge attempts only for
   generation-passing candidates (2 x passes). Zero retry/replacement; ITT
   denominator 16 per arm; declared exploratory round 2 (round-1 results were
   observed, so no confirmatory claim attaches to round 2).
4. Phase 3 (optional, separately authorized): Frame B measurement.

## 5. Accounting and boundaries

- Hard USD cap and call cap to be set in the owner authorization; round-1
  realized known cost was USD 0.018549 for 76 executed attempts.
- Missing cost remains unknown, never zero. Copyrighted images, credentials,
  and raw responses stay outside the manuscript directory.
- Round 2, if executed, is reported as a distinct exploratory instrument
  revision; the manuscript's round-1 numbers are not edited to match it.
