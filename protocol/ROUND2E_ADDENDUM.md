# Round-2e Addendum — minimal arm-neutral D3 repair (frozen before execution)

**Status:** frozen before any round-2e provider call. Parent: round 2c
(`round2c_exploratory_census_20260815T041500Z`, valid) and round 2d
(`round2d_exploratory_census_20260815T044500Z`, SEALED INVALID for arm comparison).

## Why round 2e exists

Round 2d tested defect **D3** (the `correct_option` indexing convention is stated
nowhere in the prompt contract). D3 is real: in round 2c, 14 of 24 MCQ attempts
satisfied `answer == options[correct_option - 1]` (1-based) while only 2 satisfied
the gate's 0-based rule.

But the round-2d **fix** was mis-designed. A ~1000-character instruction block was
appended identically to all three arms. It interacted with the two *terse* arms
only, inducing decoder degeneration: a valid JSON prefix, then hundreds of
whitespace characters, then EOS without closing the object.

| Run | ecm_full | direct | structured |
|---|---|---|---|
| r2c whitespace-degenerate responses | 0/16 | 0/16 | 0/16 |
| r2d whitespace-degenerate responses | 0/16 | **7/16** | **4/16** |

Failure composition shifted accordingly: in r2c the baseline arms failed on genuine
content defects (`quote_non_verbatim`, `mcq_1based_index`); in r2d they failed
overwhelmingly on `empty_required_fields` / `empty_visual_fields`, i.e. degenerate
output. The r2d gate contrast (15 vs 5 vs 6) therefore measures the prompt edit,
not the evidence-contract intervention, and is sealed as invalid for arm comparison.

A labelled sensitivity analysis (append `}}` to the 11 degenerate responses, then
re-apply the UNCHANGED gate) shows all 11 recover syntactically but still fail the
gate, so the sealed as-run counts are unchanged by the pathology. The pathology
corrupts the *comparison*, not the arithmetic.

## What round 2e changes

Prompt text only, reduced to the shortest statement that removes the ambiguity
(~180 characters versus ~1000), so added token mass is negligible relative to each
arm's own instruction and cannot plausibly drive an arm-dependent pathology:

> Quy ước: text_evidence_quote lấy nguyên văn từ VĂN BẢN NGUỒN (không lấy chữ chỉ
> có trong ảnh). Với multiple_choice, correct_option đếm từ 0 (0,1,2,3) và answer
> phải chép nguyên văn options[correct_option].

## What round 2e does NOT change

- the deterministic gate: `correct_option` integer in 0..3, byte-exact
  `answer == options[correct_option]`;
- the no-repair / no-coercion policy;
- judge prompt, seven-field schema, 1--5 scale, arm-blind coding, two judge
  families (`claude-opus-5`, `gpt-5.6-sol`), ITT denominator 16 per arm,
  zero retry / fallback / replacement;
- the 16-chunk Frame A.

Relaxing the gate to also accept 1-based indices is explicitly rejected: it would
be post-hoc gate loosening after observing the data, and it is undecidable whenever
`answer` matches both `options[co]` and `options[co-1]`.

## Prespecified validity check (declared before execution)

Round 2e is valid for arm comparison only if the whitespace-degeneration rate is
low AND not concentrated in the terse arms. If any arm shows a materially higher
degeneration rate than the others, round 2e is sealed invalid exactly as 2d was,
and round 2c remains the reference measurement.

## Frame B status

Frame B (image-necessary chunks) is **infeasible in this sandbox**: only the 16
census chunks are materialized. The "8 unused multimodal chunks" exist as a count
in manifest metadata, with no packages or image bytes on disk. No Frame B claim is
made.
