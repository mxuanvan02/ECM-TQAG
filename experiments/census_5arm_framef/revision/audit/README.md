# Synthetic audit tests

These tests use invented Vietnamese strings only; they contain no textbook content. They exercise the byte-identical historical gate module under `para_arm/reference/ecm_v2_gates.py`.

Run from the revision root:

```bash
python3 -m unittest discover -s audit_tests -p 'test_*.py' -v
```

The fixtures verify ordinary pass/fail behaviour and document two scope limits: G6 does not inspect question text, and G7/G8 receive a chunk-level lettering pool rather than selected-crop lettering. A passing limitation test is evidence of the implemented scope, not evidence that the limitation has been repaired.
