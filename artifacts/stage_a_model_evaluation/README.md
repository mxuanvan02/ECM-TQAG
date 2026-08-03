# Stage A model-based blinded evaluation

This directory contains de-identified, record-level ratings from two independently run model families over the same 24-item frozen packet, plus a deterministic summary script.

- GPT family: `gpt-5.6-luna`, 24/24 locally validated responses.
- Claude family: `claude-haiku-4.5`, 24/24 locally validated responses.
- Packet SHA-256: `ef68612891484e1d41bc5b96e75e5a499a58ccb4152f9827e1f5a1812bd3fe3a`.

Free-text notes, evidence content, source images, raw provider envelopes, credentials, and restricted textbook material are not redistributed. The rows preserve blind identifiers and protocol fields only.

Run:

```bash
python3 artifacts/stage_a_model_evaluation/reproduce_stage_a.py
```

The reported agreement is descriptive agreement between model-based evaluators. It is not human/expert evaluation, semantic validation, factual or legal accuracy, or a substitute for adjudication.
