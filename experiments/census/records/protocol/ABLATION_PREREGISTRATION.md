# Text-only ablation of visual necessity — FROZEN BEFORE EXECUTION

**Status:** frozen, prospective. No call is authorized by this document.
Execution requires owner authorization with an explicit USD cap.

**Purpose.** Replace the rated criterion *visual necessity* with a measurement.
The census reports it as a 1–5 rater score whose threshold (3) is a convention.
This ablation asks the question the score is a proxy for: *can the item be
answered without the figure?*

**Parent evidence.** The 50 admitted items of the reported census
(`round4_framec_census_20260816T105300Z`), i.e. every item that passed the
deterministic gate `G`. No new item is generated and no gate is modified.

---

## 1. Design — two branches, paired within item

Each admitted item `i` with source chunk `c(i)` is attempted **twice**, under two
conditions that differ in exactly one respect, the presence of the figure:

- **`TEXT`** (ablation): supply the recognised text layer `T_c` and the question.
  No image, no figure description, no declared quotation, no rationale.
- **`TEXT+IMG`** (control): supply the same `T_c`, the same question, **and** the
  chunk's figure crops from `I_c`.

Both branches use the same generator as the census
(`qwen/qwen3-vl-8b-instruct`), temperature 0, one call per item per branch, zero
retry. Prompt text, schema, and decoding settings are identical between
branches; only the image content blocks differ. Total: 50 × 2 = 100 calls.

The control branch is required for interpretation. Without it, a wrong answer in
`TEXT` is ambiguous between *the item needs the figure* and *the model cannot
answer this item at all*. With it, the two are separable.

## 2. Endpoints (primary)

For branch `b ∈ {TEXT, TEXT+IMG}` let `R_b(i) = 1` iff the returned answer is
correct under the mechanical rule of §3. Define

    Measured visual necessity:   V*(i) = 1 - R_TEXT(i)
    Figure-attributable gain:    G(i)  = R_TEXT+IMG(i) - R_TEXT(i)  ∈ {-1,0,+1}

`V*(i)=1` means the item was not answerable from text alone. `G(i)=+1` is the
stronger statement: the figure is what made the item answerable. Arm-level
quantities are the means of `V*` and of `R_b` over the items of each arm, with
Clopper–Pearson exact 95% intervals.

The paired quantity `G` is summarised over all 50 items by an exact two-sided
McNemar test on the discordant items (`R_TEXT+IMG=1, R_TEXT=0` against the
reverse). This test is within-item and does not depend on the arm structure, so
it is the one comparison here with a defensible denominator; it is nevertheless
reported with its discordance counts and without any claim beyond the 50 items.

## 3. Grading rule (fixed now, applied mechanically)

Grading is deterministic. No model and no human judges correctness.

- **Multiple choice (14 items).** Correct iff the returned option index equals
  the item's `correct_option`. The four options are supplied in their recorded
  order. This is unambiguous. Chance level is 25%, and the measured `R_TEXT` is
  compared against it descriptively.
- **Short answer (36 items).** Let `N'` be `casefold ∘ ws ∘ NFC` (the census
  normaliser of eq. 8 plus case folding, because free-form answers are not
  expected to preserve case). Correct iff
  `N'(gold) ⊆ N'(returned)` or `N'(returned) ⊆ N'(gold)`,
  i.e. containment in either direction after normalisation.

The short-answer rule is lenient by construction: it credits the model whenever
its answer contains the recorded answer or is contained by it. A lenient rule
biases **against** the claim that items are visually necessary, so a high
measured necessity under this rule is conservative.

**Both endpoints are reported separately**, because the multiple-choice subset
is graded without any string heuristic:

- `PRIMARY-ALL`: all 50 items under the rule above.
- `PRIMARY-MCQ`: the 14 multiple-choice items only.

## 4. Arm comparison (secondary, descriptive)

For chunks where two arms both produced an admitted item, `V*` is compared
between arms with an exact two-sided McNemar test on discordant chunks
(16 chunks for ECM vs direct, 11 for ECM vs structured). These counts are far
below the discordance needed for power, so the arm comparison is **descriptive
and carries no significance claim**. The direction is not pre-assumed.

A per-arm reading of `V*` is also confounded in a way that is stated now rather
than discovered later: the arms admit different numbers of items (22, 16, 12),
so each arm's `V*` is measured on a different item set. The arm comparison is
therefore conditional on admission and is reported as such.

## 5. Relation to the rated score (secondary)

Cross-tabulate `V*(i)` against the rated necessity `min_j s_j^(vis)` on the 48
items with both rater records, and report the agreement. This is a validity
check of the rated criterion, not an endpoint. Either outcome is reportable: if
they disagree, the rated criterion is weak evidence; if they agree, the rated
result is corroborated by a mechanical measurement.

## 6. Execution discipline

- One call per item, **zero retry**. A failed call is recorded as
  `TERMINAL_FAILURE` and its item is excluded from the denominator with the
  exclusion reported.
- Per-task claim file with `O_EXCL` and a single run lock, so no task can be
  double-called by concurrent processes.
- Reported cost is accumulated per call and checked against the USD cap before
  each call; if the cap would bind, remaining tasks are written as
  `NOT_ATTEMPTED:budget_cap` rather than overspending.
- The census records, the gate, and the manuscript numbers are not modified by
  this ablation. It adds a measurement; it does not re-analyse the census.

## 7. Pre-committed reporting

The result is reported whatever it shows, including these outcomes:

- If most items are answered from text alone, measured necessity is low, which
  **confirms** the corpus limitation already reported and strengthens it by
  replacing a rated score with a measurement.
- If many items are not answered from text alone, the rated necessity scores
  **understate** necessity, and the manuscript's interpretation of the judged
  endpoint must be softened accordingly.
- If the arms differ in measured necessity, the difference is reported as
  descriptive with its discordance counts.

No outcome licenses relaxing the gate, changing the census, or re-labelling the
judged endpoints as confirmatory.
