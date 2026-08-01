# ECM-TQAG manuscript guide and evaluation interpretation

This guide accompanies the manuscript and explains what each section establishes, how the evaluation is constructed, and how every reported number should be interpreted.

## 1. Abstract

The abstract states the central claim narrowly: ECM-TQAG is a protocol for constructing traceable multimodal textbook MCQs. It does not claim to be a document encoder, an answering model, or a proof of legal or pedagogical quality. The key distinction is between model-proposed evidence structure and deterministic construction checks.

## 2. Introduction

The introduction motivates the problem: textbook evidence is distributed across prose, layout, tables, diagrams, and images. The research need is not merely to attach an image, but to preserve an inspectable path from source evidence to answer and question. The contribution is therefore framed as traceable construction, not as a general benchmark score or a claim that every generated item is educationally valid.

## 3. Construction protocol

A package contains text (`T`), declared structure/layout (`L`), visual regions or page images (`V`), metadata, and source provenance. The three evidence conditions are:

- `T`: extracted text only;
- `TL_struct`: text plus declared document structure;
- `TLV`: text, structure, and attached image pixels.

The ECM-TQAG path is:

1. the planner proposes a typed, source-bound graph and motif request;
2. deterministic code checks the graph and matches it against the closed motif catalogue;
3. the matcher compiles the accepted motif into a restricted program;
4. the executor derives answer atoms and their provenance trace;
5. the isolated realizer writes one four-option MCQ from the locked construction only;
6. the audit replays the construction and checks the final item.

The model does not supply the program, answer atoms, or trace. This is why the protocol can test whether the final answer is mechanically derived from the accepted graph rather than merely asserted by the model.

## 4. Compared construction methods

The 72-cell evaluation compares three methods under the same chunk and evidence-condition design:

- **Direct**: generates an MCQ from a directly supported proposition. It tests ordinary proposition-to-question generation under the selected evidence condition.
- **Answer-first**: declares and grounds an answer before writing the question and distractors. It tests whether fixing the answer first improves answer/question consistency without using ECM graph execution.
- **ECM-TQAG**: constructs a typed evidence graph, matches a motif, executes a restricted program, and realizes the MCQ from executor-derived atoms. It tests the additional value of executable derivation and provenance checks.

The methods are compared as construction protocols. The current evaluation does not claim that one method is superior in legal correctness or educational usefulness because those outcomes require independent review.

## 5. Experimental design and every number

The design is a full factorial matrix:

- **8 chunks**: selected source contexts from **5 Vietnamese law textbooks**;
- **3 evidence conditions**: `T`, `TL_struct`, and `TLV`;
- **3 methods**: Direct, Answer-first, and ECM-TQAG;
- **72 cells**: `8 × 3 × 3`.

A cell is one chunk-condition-method combination. Direct and Answer-first each issue one model request per cell, so they contribute `24 + 24 = 48` requests. ECM-TQAG has one planning request per cell and a realization request only if planning passes deterministic checks. It therefore has up to 48 requests and uses 96 requests when all 24 ECM plans reach realization. The actual request count can be lower when a plan is rejected before realization; request count is not a quality score.

## 6. Context recovery and provenance partitions

Two packages were identified as lacking sufficient semantic context because of OCR/chunk boundaries. Only the 18 cells using those packages were regenerated after adding demonstrably adjacent context. The other 54 cells were retained unchanged.

- **Retained evidence**: 54 cells; 47 passed and 7 were rejected.
- **Context-recovered evidence**: 18 cells; 13 passed and 5 were rejected.
- **Combined result**: 72 cells; 60 passed and 12 were rejected.
- **Pass rate**: `60/72 = 83.3%`.
- **Rejection rate**: `12/72 = 16.7%`.

The two partitions have different evidence digests. Each was audited against its own evidence description before combination. This is a provenance safeguard: it prevents a valid old record from being reported as invalid merely because it was checked against a later evidence package.

Context recovery was conservative. The French-court diagram package received semantically adjacent preceding context. The securities package remained title-plus-image because no safe adjacent OCR context described that image; unrelated neighbouring text was not inserted merely to increase the pass rate.

## 7. Meaning of the 12 rejections

The reported taxonomy assigns each rejected cell to its first failed criterion. The categories are operational diagnoses, not judgments about the underlying textbook or law.

### 7.1 Insufficient evidence — 5 cells

Four cells concern a title-and-image-only source package, and one concerns a long legal-text package. The supplied package did not provide enough source-bound evidence for the requested construction. The result identifies an evidence-coverage limitation for that package.

### 7.2 Non-literal source grounding — 4 cells

Three cells concern a long legal-text package, and one concerns the context-recovered French-court diagram package. A graph node or evidence anchor paraphrased the source instead of reproducing a contiguous literal span. The criterion protects provenance: a semantically plausible paraphrase is not accepted as a literal source anchor.

### 7.3 ECM answer not bound to executor atom — 2 cells

The two cells concern legal-text packages. The selected option could not be matched to the atom actually returned by the restricted program. This criterion prevents a realizer from changing the answer after deterministic execution.

### 7.4 Invalid ECM evidence anchor — 1 cell

The cell concerns a legal-text package. The final anchor did not equal the graph node locked during construction. This criterion prevents the realizer from silently replacing the evidence used by the executor.

Thus, **5 rejections diagnose evidence coverage** and **7 diagnose model-output or contract compliance**. None of the 12 categories is a direct measure of legal correctness, distractor quality, one-best-answer validity, pedagogy, or genuine visual necessity.

## 8. Mechanical evaluation criteria

The deterministic audit checks:

1. package identity and evidence digest;
2. record shape and required fields;
3. four distinct answer choices;
4. answer/selected-choice agreement where applicable;
5. source-bound graph node IDs and node modalities;
6. typed graph edges and role-relation correspondence;
7. closed-catalog motif predicates;
8. exact compiler output for the accepted motif;
9. executor-derived answer atoms;
10. atom-to-trace correspondence;
11. construction receipt and SHA-256 integrity;
12. program-step trace and provenance descriptors;
13. exact locked graph-node anchors; and
14. the requirement that ECM under `TLV` bind a visual node.

A passed cell means that these structural and provenance conditions were replayed successfully. It does not mean that the graph relation is legally correct, that the answer is the unique best answer, that distractors are good, that the item is pedagogically useful, or that the image is genuinely necessary for a human respondent.

## 9. Limitations and interpretation

The corpus is a reproducible feasibility evaluation, not a generalization study. The graph is initially proposed by a language model, so literal binding and deterministic execution cannot by themselves prove the truth of a model-proposed relation or legal claim. Independent legal and educational review remains necessary. Visual-node binding is also weaker than a counterfactual visual-dependence test.

## 10. Final reading of the result

The defensible conclusion is:

> Under the stated evidence packages and deterministic construction contract, 60 of 72 cells produced structurally valid, provenance-replayable records. Twelve cells were rejected for identifiable evidence or contract reasons. The result demonstrates feasibility of traceable construction and exposes failure modes; it does not establish legal or pedagogical quality of the generated questions.
