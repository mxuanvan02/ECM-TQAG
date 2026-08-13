# Prospective R6 addendum — target-conditioned ROI OCR

## Status

Prospective offline remediation only. This public document grants no provider or paid-execution authorization.

## Root cause

Symbolic occurrence IDs alone do not provide a spatial referent when several visible primitives share a collection. The successor contract therefore conditions each observation on a preregistered source region instead of asking a model to infer which whole-image primitive the identifier denotes.

## Successor contract

1. Each request addresses exactly one preregistered occurrence with a non-null `canonical_target_id`.
2. A deterministic ROI is derived only from that occurrence's sealed `source_bbox`, using fixed padding and clipping to `[0,1]`.
3. Only ROI pixels are provider-visible. Neither `semantic_label`, `canonical_target_id`, nor the original global bbox appears in request text or JSON Schema.
4. The observation contains literal OCR text and a tight bbox in ROI-normalized coordinates.
5. The bbox is mapped affinely back to full-crop normalized coordinates.
6. Semantic equality and geometry are checked fail-closed against the sealed registry before projection into the closed v3.5 replay shape.
7. Fuzzy matching, translation, alias repair, union/containment rescue, retry, fallback, and validator weakening are outside this contract.

## Claim boundary

R6 geometry is local refinement conditional on a frozen target region, not independent whole-image target discovery. Semantic OCR remains independently testable because the sealed label is not exposed in the provider-visible payload.

## Public reproducibility boundary

The public repository includes the ROI contract and synthetic tests only. It excludes private source records and images, credentials, provider responses, run ledgers, paid-execution safety freezes, cost audits, and authorization artifacts. Passing the public tests does not constitute provider qualification or paid-run authorization.
