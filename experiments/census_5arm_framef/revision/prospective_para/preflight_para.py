#!/usr/bin/env python3
"""PARA arm preflight — CHECK MODE ONLY. Makes no model call and writes nothing.

The PARA arm is the control the ACIIDS revision names in Implications: a prompt
that asks only for the answer to be worded so it does not appear verbatim in the
declared quotation, with no division-of-labour clause and no ordering. If such a
prompt matched the contract on admission, G_6 would be measuring rewording.

This script decides whether that run is executable on this machine. It checks
every precondition and prints a verdict. It never calls a provider, never spends
money, and never writes into a sealed record.

Usage:
    python3 preflight_para.py                  # check with defaults
    python3 preflight_para.py --bundle DIR     # point at the Frame-F bundle
    python3 preflight_para.py --json           # machine-readable verdict

Exit code 0 = every precondition met (run is executable).
Exit code 1 = at least one blocker (run is NOT executable).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------- declared hashes
# These come from records/protocol.json in the published Frame-F release. They
# pin the exact modules the sealed census used. A mismatch means the module on
# disk is NOT the one that produced the published numbers.
DECLARED = {
    "gate_module": "7f18b0c9ee4543e851985bb00748caf0b3b522098c4199b7a9bb901362db0828",
    "prompt_module": "689ec92df45c3afc8dae47be2b8de00b0e149319a3ba9ae1749f4d4f948da467",
    "frame_manifest": "5e667745e7ba5b1989bdfd7cd2ba36bb84eca420062a0f693a2cd8f9d552d943",
    "census_prereg": "20695651ad624d370a908101a1039f6baddf5723cf99f07b064f7c3ca2832635",
}

# Generator held constant across arms, per the manuscript's Experimental Design.
GENERATOR_SLUG = "qwen/qwen3-vl-8b-instruct"
DECODING = {"temperature": 0, "max_tokens": 1024, "greedy": True}
FRAME_N = 60  # one call per unit; PARA adds exactly 60 attempts

REF_DEFAULT = Path(__file__).resolve().parents[1] / "reference"


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class Check:
    """One precondition. `blocker=True` means the run cannot proceed without it."""

    def __init__(self, name: str, blocker: bool = True) -> None:
        self.name = name
        self.blocker = blocker
        self.ok = False
        self.detail = ""
        self.evidence = ""

    def set(self, ok: bool, detail: str, evidence: str = "") -> "Check":
        self.ok, self.detail, self.evidence = ok, detail, evidence
        return self

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "blocker": self.blocker,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def check_gate_module(ref_dir: Path) -> Check:
    c = Check("gate module byte-identical to sealed census")
    path = ref_dir / "ecm_v2_gates.py"
    got = sha256_file(path)
    if got is None:
        return c.set(False, f"absent: {path}")
    if got == DECLARED["gate_module"]:
        return c.set(True, "sha256 matches protocol.json", f"{got[:16]}...")
    return c.set(False, "sha256 MISMATCH against protocol.json",
                 f"got {got[:16]}... want {DECLARED['gate_module'][:16]}...")


def check_prompt_module(ref_dir: Path) -> Check:
    # This preflight covers the 60-call extension that compares PARA directly
    # with the sealed ECM arm. That comparison requires the sealed prompt builder;
    # otherwise ECM must be rerun in the same batch (a different, 120-call design).
    c = Check("prompt module byte-identical to sealed census", blocker=True)
    path = ref_dir / "ecm_v2_prompt.py"
    got = sha256_file(path)
    if got is None:
        return c.set(False, f"absent: {path}")
    if got == DECLARED["prompt_module"]:
        return c.set(True, "sha256 matches protocol.json", f"{got[:16]}...")
    return c.set(
        False,
        "sha256 MISMATCH: this is a different revision of the prompt module "
        "than the one the sealed census used, so a PARA arm built on it is not "
        "directly comparable to the published arms",
        f"got {got[:16]}... want {DECLARED['prompt_module'][:16]}...",
    )


def check_bundle(bundle: Path | None) -> list[Check]:
    """Frame-F conditioning bundle: page text, structural regions, figure crops."""
    out: list[Check] = []
    c_dir = Check("Frame-F bundle directory")
    if bundle is None:
        out.append(c_dir.set(False, "not supplied (--bundle DIR)"))
        return out
    if not bundle.is_dir():
        out.append(c_dir.set(False, f"not a directory: {bundle}"))
        return out
    out.append(c_dir.set(True, str(bundle)))

    c_man = Check("frame manifest byte-identical to sealed frame")
    cands = list(bundle.rglob("dataset_manifest.json")) + list(bundle.rglob("*manifest*.json"))
    hit = next((p for p in cands if sha256_file(p) == DECLARED["frame_manifest"]), None)
    if hit is not None:
        out.append(c_man.set(True, "sha256 matches", str(hit)))
    else:
        out.append(c_man.set(
            False,
            f"no manifest under {bundle} hashes to the sealed frame manifest "
            f"({len(cands)} candidate(s) examined)",
        ))

    c_img = Check("figure crops present")
    imgs = [p for p in bundle.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    out.append(c_img.set(bool(imgs), f"{len(imgs)} image file(s) found"))

    c_txt = Check("conditioning text present")
    txts = [p for p in bundle.rglob("*") if p.suffix.lower() in {".txt", ".json", ".jsonl", ".md"}]
    out.append(c_txt.set(bool(txts), f"{len(txts)} text file(s) found"))
    return out


def check_api_key() -> Check:
    c = Check("OPENROUTER_API_KEY reachable in this shell")
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return c.set(False, "not set; export it before the paid run")
    # Never print any portion of a credential, even in local preflight output.
    return c.set(True, "set (value redacted)")


def check_network() -> Check:
    c = Check("openrouter.ai reachable", blocker=False)
    if shutil.which("curl") is None:
        return c.set(False, "curl not installed")
    try:
        r = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "15",
             "https://openrouter.ai/api/v1/models"],
            capture_output=True, text=True, timeout=25,
        )
        code = r.stdout.strip()
        return c.set(code.startswith("2"), f"HTTP {code}")
    except Exception as exc:  # noqa: BLE001
        return c.set(False, f"probe failed: {exc}")


def check_prereg_written(out_dir: Path) -> Check:
    """Validate the prospective protocol actually shipped with this supplement."""
    c = Check("PARA pre-registration sealed before any call")
    path = out_dir / "PARA_PREREGISTRATION.json"
    if not path.is_file():
        return c.set(False, f"absent: {path} — write and hash it before running")
    digest = sha256_file(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return c.set(False, f"present but unparseable: {exc}")

    missing: list[str] = []
    required_top = {
        "schema", "status", "written_before_first_call", "arm_definition",
        "execution_parameters_inherited_from_sealed_census", "endpoint",
        "stopping_and_integrity_rules", "blockers_outstanding_at_sealing_time",
    }
    missing.extend(sorted(required_top - set(doc)))
    arm = doc.get("arm_definition", {})
    endpoint = doc.get("endpoint", {})
    execution = doc.get("execution_parameters_inherited_from_sealed_census", {})
    if not isinstance(arm, dict) or not arm.get("name") or not arm.get("prompt_construction_rule"):
        missing.append("arm_definition.name/prompt_construction_rule")
    if not isinstance(endpoint, dict) or not endpoint.get("primary") or not endpoint.get("test"):
        missing.append("endpoint.primary/test")
    if not isinstance(execution, dict) or execution.get("planned_paid_calls") != FRAME_N:
        missing.append(f"execution_parameters...planned_paid_calls={FRAME_N}")
    if doc.get("status") != "SEALED_BEFORE_ANY_CALL" or doc.get("written_before_first_call") is not True:
        missing.append("sealed-before-call status")
    if missing:
        return c.set(False, "missing or invalid fields: " + ", ".join(missing))
    return c.set(True, f"sealed, sha256 {digest[:16]}...", str(path))


def main() -> int:
    ap = argparse.ArgumentParser(description="PARA arm preflight (check mode only)")
    ap.add_argument("--bundle", type=Path, default=None,
                    help="Frame-F conditioning bundle directory (text + crops)")
    ap.add_argument("--ref", type=Path, default=REF_DEFAULT,
                    help="directory holding ecm_v2_gates.py / ecm_v2_prompt.py")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    out_dir = Path(__file__).resolve().parent
    checks: list[Check] = [
        check_gate_module(args.ref),
        check_prompt_module(args.ref),
        *check_bundle(args.bundle),
        check_api_key(),
        check_network(),
        check_prereg_written(out_dir),
    ]

    blockers = [c for c in checks if c.blocker and not c.ok]
    warnings = [c for c in checks if not c.blocker and not c.ok]
    verdict = {
        "executable": not blockers,
        "n_blockers": len(blockers),
        "n_warnings": len(warnings),
        "planned_calls": FRAME_N,
        "generator": GENERATOR_SLUG,
        "decoding": DECODING,
        "checks": [c.as_dict() for c in checks],
    }

    if args.json:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
        return 0 if not blockers else 1

    print("PARA arm preflight — CHECK MODE (no model call, nothing written)\n")
    for c in checks:
        mark = "ok  " if c.ok else ("BLOCK" if c.blocker else "warn ")
        print(f"  [{mark}] {c.name}")
        if c.detail:
            print(f"          {c.detail}")
        if c.evidence:
            print(f"          evidence: {c.evidence}")
    print()
    print(f"planned paid calls if executed: {FRAME_N} "
          f"({GENERATOR_SLUG}, temp 0, {DECODING['max_tokens']}-token cap)")
    print()
    if blockers:
        print(f"VERDICT: NOT executable — {len(blockers)} blocker(s)")
        for c in blockers:
            print(f"  - {c.name}: {c.detail}")
        if warnings:
            print(f"\nalso {len(warnings)} warning(s):")
            for c in warnings:
                print(f"  - {c.name}: {c.detail}")
        return 1
    print("VERDICT: executable — every precondition met")
    if warnings:
        print(f"\n{len(warnings)} warning(s) that do not block but affect comparability:")
        for c in warnings:
            print(f"  - {c.name}: {c.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
