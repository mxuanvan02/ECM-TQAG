# Prospective arm-blind human evaluation protocol

**Status:** protocol only; not executed. No human ratings are included or claimed.

## Purpose
Estimate semantic usability separately from deterministic admission. The primary human endpoint is evidence correctness; visual necessity, pedagogical value, language quality, and critical provenance violations are secondary.

## Sampling
Use a stratified sample of released item identifiers, balanced across the five arms and full-gate status. Preserve paired chunks when feasible. Fix the sample and exclusions before revealing arm labels. Copyrighted source material remains inside the authorised environment.

## Raters and blinding
Recruit at least two Vietnamese-law subject-matter experts and one educational-measurement reviewer. Present item, answer, declared quotation, selected crop, and necessary local context through random opaque IDs. Hide arm, gate outcomes, model identity, and other raters' scores. Randomise presentation order independently per rater.

## Rubric
Rate each 1–5:
1. **Evidence correctness:** answer and rationale are fully supported by the displayed evidence.
2. **Visual necessity:** answering correctly requires information from the selected crop rather than the text bundle alone.
3. **Pedagogical value:** item is clear, instructionally useful, and appropriate for the stated type.
4. **Language quality:** Vietnamese wording is grammatical and unambiguous.

Also record binary flags: critical provenance violation; answer appears in question; answer appears in declared quotation; selected-crop mismatch; other fatal flaw. Require a short evidence-linked rationale for scores 1–2 and every fatal flag.

## Primary analysis
Define a usable item prospectively as full deterministic admission **and** evidence-correctness score ≥4 from both subject-matter raters **and** no critical provenance flag. Report arm counts, exact binomial intervals, paired exact McNemar contrasts, and disagreements. This definition must be frozen before ratings begin; it is distinct from the manuscript's post-hoc model-rating endpoint.

## Reliability and adjudication
Report exact agreement and quadratic weighted kappa for ordinal scales. A third blinded adjudicator reviews any evidence-correctness disagreement spanning ≥2 points or any disagreement on a fatal flag. Preserve pre-adjudication ratings and report adjudication frequency.

## Error analysis
Sample admitted and rejected items from every arm. Report arm-blind categories: unsupported answer, wrong crop, quotation mismatch, answer leakage, lexical gate gaming, ambiguous question, pedagogical defect, and other. Do not infer visual necessity solely from lexical overlap.

## Reproducibility
Archive the frozen sampling manifest, randomisation seed, rubric version, blank score sheet, adjudication rules, and analysis code. Public release may contain only opaque IDs and derived ratings unless the rights holder authorises source redistribution.
