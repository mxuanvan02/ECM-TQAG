# Four-arm census and text-only ablation

Released records and analysis code for the ECM–TQAG census reported in the
ACIIDS 2027 submission (Springer LNCS/LNAI). Every quantity in the paper
recomputes from what is in this directory, with no network access and no model
calls.

## Verify the paper's numbers

```bash
cd experiments/census
python3 verify_reported_quantities.py            # print every recomputed quantity
python3 verify_reported_quantities.py --check    # assert them against the paper
```

`--check` exits non-zero if any published value fails to reproduce. It needs
only the Python standard library.

What the script recomputes from the raw task records, rather than reading from a
summary file:

- admission per arm and Clopper–Pearson exact 95% intervals
- the three confirmatory paired contrasts (exact McNemar) and Holm step-down
- the auxiliary GATE-against-DIR contrast
- the thresholded endpoint `V` and the visual-necessity score distribution
- quadratic weighted kappa, exact agreement and within-one agreement per criterion
- the text-only ablation for both answerers, including the pre-registered
  grading rule applied to each response
- the count of admitted items answered correctly in neither branch, printed
  next to `n - text_image` because the two are easily confused and differ
- agreement between the two answerers, and measured against rated necessity
- the mechanical cue scan over the admitted items: how many questions name the
  figure in words, and how many answers repeat at least 20 characters of `T_c`
  verbatim, per arm and in total

The cue scan is a mechanical string test, not a human review, and the paper
reports it as such. Its rules are the two constants at the top of the cue-scan
section of the script: the cue set `hình / sơ đồ / biểu đồ` and the 20-character
floor, both applied under the same normalisation `N` as the quotation gate. It
reads `T_c` from the published frame manifest, so a reviewer can change either
rule and see the counts move.

The failure taxonomy is read from `FAILURE_ATTRIBUTION.json` because tracing a
quotation to its source channel needs the page images, which are not
redistributable (see below).

## Layout

```
code/          the census instrument: gate, contracts, runner, transport, scripts
records/
  protocol/    the frozen prompt and experiment contracts, and the ablation
               preregistration whose sha256 is recorded in ABLATION_REPORT.json
  frame/       the dataset manifest defining the 24-chunk frame
  census/      run plan, preflight, qualification, report, results summary,
               failure attribution, owner authorisation, and 288 task records
  ablation/    ablation report, owner authorisation, call ledger, 272 task records
PROVENANCE.json
```

## Provenance of the code

Published filenames carry no version token, so they read as an instrument rather
than as a snapshot of a working directory. `PROVENANCE.json` records, for every
file, its sha256 and one of three origin states:

- `identical` — bytes match a private working file, whose sha256 is recorded
- `derived` — changed to add the fourth (gate-disclosed) arm, with the line-set
  similarity to its nearest private ancestor
- `new` / `rewritten` — written for this census

The private paths are recorded for audit and are not themselves published.

The census run seals the instrument by hashing `gate.py` and
`prompt_amendment.py` into `plan_sha256`. That value recomputes from the
published code:

```bash
python3 - <<'PY'
import hashlib, json, pathlib
root = pathlib.Path("code")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
binding = json.dumps({
    "instrument": "census_4arm_framec_gate_disclosed_v1",
    "judges": ["claude-opus-5", "gpt-5.6-sol"],
    "superseded_judges": ["claude-sonnet-5", "gpt-5.6-terra"],
    "validator": sha(root / "ecm_tqag/gate.py"),
    "prompt": sha(root / "ecm_tqag/prompt_amendment.py"),
}, sort_keys=True, separators=(",", ":")).encode()
print(hashlib.sha256(binding).hexdigest())
PY
```

This prints `32c5a99720ea65724dead5546c65ba0b8b4f319bbdeda4b0660897f6b885807e`,
the `plan_sha256` in `records/census/ROUND4_PLAN.json`.

## What is not released, and why

- **Scanned page images and figure crops.** Copyright of the University of Law,
  Hue University. Held internally, not redistributed.
- **Raw provider response payloads.** Withheld with the source material they
  quote. The graded outcome of every response is in the task records, so the
  analysis is reproducible without them.
- **Credentials and provider identifiers.**

Task records carry the generated items themselves, including each declared
quotation. The longest such quotation is 690 characters; no record contains a
page's full text layer.

## Scope of the claim

Admission certifies that an item's declared evidence recomputes against its own
source bundle. It does not certify that the item is answerable, pedagogically
sound, or that its figure is necessary. The judged endpoints are secondary and
below their pre-registered floor of 40 chunks, so they carry no significance
claim. The contract-against-disclosure contrast is unresolved at this frame
size and is reported as such.
