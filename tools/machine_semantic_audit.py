#!/usr/bin/env python3
"""Deterministic release-boundary and manuscript semantic-policy audit.

This audit checks strings and file classes. It does not make semantic judgments.

INPUT
  --repo PATH        repository root to audit (default: the current directory)
  --manuscript PATH  optional manuscript file, additionally scanned and required to
                     carry the machine-only disclosure phrases
  --output PATH      optional; also write the payload there
  No network access, no credentials, no configuration file. Standard library only.

OUTPUT
  stdout  the audit payload as JSON: schema, audit_kind, semantic_validation (always
          false -- this audit checks strings and file classes and makes no semantic
          judgment), status, repo_tree_digest, checked_file_count and findings.
  file    the same payload at --output when given. The committed receipt
          machine-policy-audit.json is regenerated with
          `python tools/machine_semantic_audit.py --repo . --output machine-policy-audit.json`.
          The receipt is excluded from repo_tree_digest so regeneration is stable; every
          other text file is hashed into it, so editing any file in the repository
          changes the digest and the receipt must be regenerated in the same commit.

EXIT CODES
  0  status == PASS, i.e. findings is empty
  1  at least one finding (main returns the boolean status != PASS, which SystemExit
     turns into 1). Each finding names its rule and file, e.g. unexpected_media,
     absolute_private_path, secret, forbidden_baseline, revoked_artifact,
     human_workflow_claim, invalid_public_config_json, public_remote_endpoint,
     public_remote_model, missing_machine_only_disclosure.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

TEXT_SUFFIXES={".md",".tex",".py",".json",".toml",".yml",".yaml",".cff",".txt"}
MEDIA_SUFFIXES={".jpg",".jpeg",".png",".tif",".tiff",".pdf"}
REMOTE_TEMPLATE_ENDPOINT="https://api.example.invalid/v1/chat/completions"
REMOTE_TEMPLATE_MODEL="MODEL_NAME_PLACEHOLDER"
FORBIDDEN={
 "revoked_artifact": re.compile(r"ECM_TQAG_EVIDENCE_EXAMPLES_20260728",re.I),
 "forbidden_aag_counts": re.compile(r"\b(?:5741|2371)\b"),
 "forbidden_baseline": re.compile(r"\bBM25\b",re.I),
 "human_workflow_claim": re.compile(r"(?:two independent annotators|third-reviewer adjudication|reserved for human review|obtain human reviews)",re.I),
 "secret": re.compile(r"(?:gho_|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"),
 "absolute_private_path": re.compile(r"/(?:home|workspace|Users)/[A-Za-z0-9_.-]+/"),
}
# The committed audit receipt records this digest, so it cannot also be an input
# to it: hashing it in makes the digest change on every write, so no committed
# receipt could ever match and the file is unsatisfiable by construction. It is
# excluded from the digest ONLY -- it is still scanned for forbidden strings and
# secrets like any other text file.
RECEIPT="machine-policy-audit.json"
# Directory components never counted as repository content. Matching is per path
# component, so an entry containing a separator could never match: the previous
# "src/ecm_tqag.egg-info" literal silently excluded nothing, and the editable
# install's egg-info files entered the digest. A reviewer who follows README
# section 7 after `pip install -e .` therefore computed a different digest from
# the committed receipt, which made the receipt irreproducible.
EXCLUDED_PARTS={".git",".venv","build","dist","__pycache__",".pytest_cache",
                "ecm_tqag.egg-info"}
ALLOWED_MEDIA={
 "fixtures/tiny-grid.png", # optional future synthetic fixture
 # Rights-cleared synthetic contract fixture for the six-arm experiment.
 # Verified synthetic, not source-derived: 96x96 RGB, IDAT 27760/27648 bytes
 # (compression ratio 0.996) with 9210-9215 distinct colours per 9216 pixels
 # -- incompressible noise, whereas a page or figure crop compresses 5-50x and
 # reuses colours. Each file is content-bound by sha256 and byte size in
 # experiments/six_arm/dataset/dataset_manifest.json, so untracking it would
 # break that fixture. Listed individually on purpose: an unexpected new image
 # in this directory must still raise unexpected_media.
 "experiments/six_arm/dataset/images/synthetic_diagram_01.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_02.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_03.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_04.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_05.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_06.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_07.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_08.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_09.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_10.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_11.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_12.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_13.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_14.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_15.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_16.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_17.png",
 "experiments/six_arm/dataset/images/synthetic_diagram_18.png",
}

def sha(p:Path)->str:
 return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(repo:Path, manuscript:Path|None)->dict:
 findings=[]; checked=[]
 roots=[repo]
 for root in roots:
  for p in sorted(root.rglob("*")):
   if not p.is_file() or any(part in EXCLUDED_PARTS for part in p.parts): continue
   rel=p.relative_to(repo).as_posix(); checked.append(rel)
   if rel == "tools/machine_semantic_audit.py": continue
   if p.suffix.lower() in MEDIA_SUFFIXES and rel not in ALLOWED_MEDIA:
    findings.append({"rule":"unexpected_media","file":rel})
   if p.suffix.lower() in TEXT_SUFFIXES:
    text=p.read_text("utf-8",errors="replace")
    for name,rx in FORBIDDEN.items():
     if rx.search(text): findings.append({"rule":name,"file":rel})
 for p in sorted((repo / "configs").glob("*.json")):
  try:
   cfg=json.loads(p.read_text("utf-8"))
  except json.JSONDecodeError:
   findings.append({"rule":"invalid_public_config_json","file":p.relative_to(repo).as_posix()}); continue
  if cfg.get("mode") == "openai-compatible":
   rel=p.relative_to(repo).as_posix()
   if cfg.get("endpoint") != REMOTE_TEMPLATE_ENDPOINT:
    findings.append({"rule":"public_remote_endpoint","file":rel})
   if cfg.get("model") != REMOTE_TEMPLATE_MODEL:
    findings.append({"rule":"public_remote_model","file":rel})
 if manuscript:
  text=manuscript.read_text("utf-8")
  checked.append(str(manuscript))
  for name,rx in FORBIDDEN.items():
   if rx.search(text): findings.append({"rule":name,"file":"MANUSCRIPT"})
  required=["machine-only","fallible machine semantic judgments","no external human annotator"]
  for phrase in required:
   if phrase.lower() not in text.lower(): findings.append({"rule":"missing_machine_only_disclosure","phrase":phrase,"file":"MANUSCRIPT"})
 return {"schema":"ecm-tqag.machine-policy-audit.v1","audit_kind":"deterministic-string-and-boundary-check","semantic_validation":False,"checked_file_count":len(checked),"findings":findings,"status":"PASS" if not findings else "FAIL","repo_tree_digest":hashlib.sha256("\n".join(f"{x}\0{sha(repo/x)}" for x in checked if not x.startswith("/") and (repo/x).is_file() and x != RECEIPT).encode()).hexdigest()}

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,default=Path(".")); ap.add_argument("--manuscript",type=Path); ap.add_argument("--output",type=Path)
 a=ap.parse_args(); result=audit(a.repo.resolve(),a.manuscript.resolve() if a.manuscript else None); payload=json.dumps(result,indent=2,sort_keys=True)+"\n"
 if a.output: a.output.write_text(payload)
 print(payload,end=""); return result["status"]!="PASS"
if __name__=="__main__": raise SystemExit(main())
