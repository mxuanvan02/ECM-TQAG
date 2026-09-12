# PARA rewording-only control — prospective protocol

**Status: not executed. No PARA result is reported in the manuscript.**

`PARA_PREREGISTRATION.json` specifies a sixth, post-census arm intended to test whether a minimal literal-avoidance instruction reproduces ECM's improvement at G6 without evidence planning or division-of-labour language.

Run `python3 preflight_para.py --json` in check mode. It performs no model call and writes nothing. The current supplement is intentionally expected to return a non-zero status because a valid 60-call extension requires: (1) the exact copyrighted Frame-F bundle; (2) the sealed prompt module matching SHA-256 `689ec92d...`; and (3) an execution credential supplied at run time. The available prompt module has a different hash. Running PARA with it and comparing against the sealed ECM arm would not be a valid sixth-arm extension.

The byte-identical historical gate module is included for audit and synthetic tests. It must not be edited: its SHA-256 is bound by the released protocol. Credentials are never printed by the preflight.
