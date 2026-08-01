# ECM-TQAG evaluation summary

## Scope

- Matrix: 8 chunks × 3 evidence conditions × 3 methods = 72 cells
- Final parsed: 60/72 (83.3%)
- Final rejected: 12/72 (16.7%)
- Context recovery: 18 cells from two chunks were regenerated after adding only demonstrably adjacent context

## Provenance partitions

| Partition | Records | Parsed | Rejected | Evidence manifest |
|---|---:|---:|---:|---|
| Unaffected/original | 54 | 47 | 7 | original evidence manifest |
| Rerun/augmented | 18 | 13 | 5 | context-augmented evidence manifest |
| Total | 72 | 60 | 12 | mixed, audited by partition |

## Rejection taxonomy

| Scenario | Count | Cells |
|---|---:|---|
| Insufficient evidence | 5 | 5 evidence-incomplete cells |
| Non-literal source grounding | 4 | 4 source-grounding cells |
| ECM answer not bound to executor atom | 2 | 2 ECM cells |
| Invalid ECM evidence anchor | 1 | 1 ECM cell |

The insufficiency cases are evidence-coverage outcomes. The other cases are model-output/contract failures detected by deterministic replay. The two short packages were not padded with unrelated neighbouring text: the French-court package was augmented with its semantically adjacent preceding section, while the securities package remained title-plus-image because no safe adjacent OCR context described that image.

## Interpretation and evaluation boundary

This summary reports structural and provenance validity only. A passed item satisfies the formal construction criteria; it does not establish legal correctness, one-best-answer validity, distractor quality, pedagogical usefulness, or genuine visual necessity. Detailed records, textbook text, and page images remain local pending rights review.