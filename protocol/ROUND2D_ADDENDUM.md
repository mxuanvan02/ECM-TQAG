# Round-2d addendum — D3 prompt-convention repair (frozen before execution)

**Frozen:** 2026-08-15, before any round-2d provider call.
**Status at freeze:** no round-2d call has been made.

## Why a round 2d exists

Round 2c executed cleanly (84 paid calls, 84 tasks, zero duplicate/orphan/retry,
36/36 judge calls HTTP 200) and its numbers are sealed. Re-deriving the 30
generation failures from the retained raw responses then exposed a THIRD
specification defect, distinct from D1 (verbatim gate) and D2 (corpus):

**D3 — the `correct_option` indexing convention was never stated to the model.**

Of 24 MCQ attempts in round 2c:

| pattern | count |
|---|---|
| `answer == options[correct_option - 1]` (1-based) | 14 |
| `answer == options[correct_option]` (0-based, what the gate requires) | 2 |
| `answer` matched no option (genuine model error) | 4 |
| other index error, incl. out-of-range values 4 and 14 | 4 |

`official/PROMPT_SCHEMA_CONTRACT.json` contains zero occurrences of "0-based",
"1-based", "index", "chi so" or "danh so". Its JSON schema declares only
`correct_option: integer`. The 0..3 range and the
`answer == options[correct_option]` equality appear ONLY inside the
`local_validation` block — validator-side, never in the instruction sent to the
model. The model was asked for an unqualified integer, chose the natural human
convention, and was failed by a gate that silently assumed the other one.

This is an instrument defect, not a model-capability limit. It also means the
round-1/2b/2c MCQ failure counts partly measure our own under-specification.

## What round 2d changes

**Prompt text only** (`round2/round2d_prompt.py`, `PROMPT_CLARIFICATION_V2`):

1. `text_evidence_quote` must come from the text channel, not from image-visible
   labels (carried over from round 2/2c).
2. MCQ: options carry no ordinal prefixes ("A.", "(1)", "1-").
3. MCQ: `correct_option` is explicitly declared **0-based**, values 0..3 only.
4. MCQ: `answer` must repeat `options[correct_option]` character for character;
   bare letter labels are forbidden.
5. Field names must never appear as values (round 2c leaked the literal string
   `"text_evidence_quote"` into `options`).
6. Plus an explicit self-check instruction before returning.

## What round 2d deliberately does NOT change

- **The deterministic gate is untouched.** `correct_option` must still be an
  integer in 0..3 and `answer` must still equal `options[correct_option]`
  byte-for-byte. Relaxing the gate to also accept 1-based indices *after*
  observing that most attempts used them would be post-hoc gate loosening, and
  it is undecidable whenever `answer` matches both `options[co]` and
  `options[co-1]`.
- Judge prompt, seven-field judgement schema, 1--5 scale, arm-blind candidate
  coding, ITT accounting, zero retry/fallback/replacement: all unchanged.
- Judge families remain the round-2c substitutes (claude-opus-5, gpt-5.6-sol),
  so round 2d is directly comparable to round 2c on both stages.

## Inference status (stated before seeing results)

Round 2d is **exploratory**, and more weakly so than round 2c: D3 was identified
from round-2c outcomes, so round 2d is a post-hoc instrument repair evaluated on
the same 16-chunk frame. It licenses NO confirmatory claim. Its purpose is
measurement validity: to separate "model cannot comply" from "we never said what
compliance meant".

Expected direction: MCQ-related generation failures should fall substantially.
`visual_necessity` should NOT improve, because D2 (text-sufficient corpus) is
untouched and is a property of the corpus, not the prompt. If hard-valid yield
stays at 0, that is the informative result: it localises the bottleneck in the
corpus rather than in output formatting.

## Frame B remains unavailable

An image-necessary frame cannot be built in this sandbox: only the 16 census
chunks are materialised. The manifest's `legacy_subset.chunk_count = 8` and
`source_pool.multimodal_chunks = 24` are metadata counts; no packages, image
files, or evidence text exist for the other 8 chunks. Frame B therefore requires
the raw corpus and is out of scope here.
