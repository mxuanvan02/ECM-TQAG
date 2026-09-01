# Frame-F census: released records

Derived records for the five-arm, 60-section census and its two text-only
ablations, as reported in the ECM-TQAG submission to ACIIDS 2027. Every quantity
the paper states recomputes from this directory alone, with no network access,
no model calls, and no dependency outside the Python standard library.

## Recompute the paper's numbers

```bash
python3 verify_reported_quantities.py          # print every recomputed quantity
python3 verify_reported_quantities.py --check  # also assert them against the paper
```

`--check` exits non-zero if any published quantity fails to reproduce, so the
script doubles as a regression test on these records.

## What is here

| File | Holds |
| --- | --- |
| `records/admission_decisions.json` | per (chunk, arm): the eight gate conditions as booleans, which conditions failed, and whether the five provenance conditions alone passed |
| `records/ablation_generator_answerer.json` | the pre-registered ablation: per item and branch, whether the answer was graded correct, at every F1 threshold that run's report tabulates |
| `records/ablation_independent_answerer.json` | the replication under an answerer from an unrelated family, same shape |
| `records/judged_scores.json` | per (chunk, arm): both raters' five ordinal scores and the critical-provenance flag |
| `records/frame_strata.json` | per chunk: figure role, question type, conditioning length |
| `records/answer_in_question.json` | per item: whether the recorded answer sits inside its own question wording, with its G6 status and whether it cleared all eight conditions |
| `records/withdrawn_results.json` | the symmetric re-grading that withdrew an earlier result of ours; recomputed from sealed records with no new calls |
| `records/protocol.json` | the three pre-registrations, the three execution authorisations, and the route-deviation record, each with the sha256 of the sealed file |
| `MANIFEST.json` | sha256 and byte length of every file here |

## Why decisions rather than text

The source is copyrighted law textbooks. Each sealed generation record carries a
verbatim quotation from a page, and each rater record quotes the item it scored,
so neither can be redistributed. Each endpoint the paper reports is a function of
*decisions* rather than of the words behind them: admission is a conjunction of
eight booleans, the ablation endpoints are functions of one graded boolean per
branch, and the judged endpoints are functions of five integers and one flag.
Grading was therefore performed against the sealed records, using the grading
function imported from the sealed runner, and the resulting decisions are what
appears here. See `RIGHTS_AND_LIMITATIONS.md` for exactly what is and is not
included.

## Threshold grids differ between the two runs

The two ablations do not tabulate the same F1 grid: the pre-registered run
reports seven thresholds, the replication nine. Each file is graded on the grid
its own sealed report tabulates, and `verify_reported_quantities.py` compares the
two answerers only on the seven thresholds both tabulate. Widening the sealed
run's grid after the fact would be re-analysis of a sealed record, which its
pre-registration lists as invalidating.

## Limits

These records establish that the reported quantities follow from the sealed
evidence. They do not establish that an admitted item is pedagogically useful,
that a rater's score is correct, or that any rate generalises beyond this
60-section frame from one institution's holdings.
