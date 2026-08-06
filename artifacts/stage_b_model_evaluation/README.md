# Stage B model-based blinded evaluation

This directory contains de-identified protocol fields from two independent model-family ratings over the same eight-item trace packet.

- GPT family: `gpt-5.6-luna`, 8/8 locally validated responses.
- Claude family: `claude-haiku-4.5`, 8/8 locally validated responses.
- Packet protocol SHA-256: `4e63ad2beae0f90c0df683260e70208f8573d149fc3f20bcfb8ee2df3646602f`.

Run `python3 artifacts/stage_b_model_evaluation/reproduce_stage_b.py` to regenerate the descriptive summary. Free-text notes, evidence, trace text, images, raw provider envelopes, credentials, and restricted textbook material are excluded. These ratings are model-based protocol checks, not human/expert evaluation, semantic validation, or factual/legal accuracy.
