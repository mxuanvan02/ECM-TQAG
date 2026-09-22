# Rights and limitations

The executable fixtures are synthetic, original materials provided under Apache-2.0. No source-derived document images, restricted datasets, credentials, private endpoints, or private dependencies are included.

The public repository contains no raw historical model outputs and no source-derived documents or text. It does contain **derived** item-level evaluation records under `experiments/census_5arm_framef/records/`: gate verdicts, graded correct/incorrect booleans, and ordinal rater scores, published so that the reported endpoints are recomputable. That directory's own `RIGHTS_AND_LIMITATIONS.md` lists every withheld field. None of the eight released record files contains a Vietnamese-diacritic character; the builder that emitted them is documented as failing closed on that check, but the builder is not part of this release. The included offline run summary is generated from synthetic fixtures and demonstrates transport and integrity handling only; it is not an evaluation of semantic grounding, model effectiveness, or generalization.

Remote execution is opt-in. The tracked remote configuration is a non-routable template with placeholders only; users must create an ignored local configuration and supply their own endpoint, model identifier, and environment-variable credential.

Users are responsible for confirming redistribution rights before adding external documents or images.
