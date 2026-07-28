#!/usr/bin/env python3
"""Deterministic release-boundary and manuscript semantic-policy audit.

This audit checks strings and file classes. It does not make semantic judgments.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

TEXT_SUFFIXES={".md",".tex",".py",".json",".toml",".yml",".yaml",".cff",".txt"}
MEDIA_SUFFIXES={".jpg",".jpeg",".png",".tif",".tiff",".pdf"}
FORBIDDEN={
 "revoked_artifact": re.compile(r"ECM_TQAG_EVIDENCE_EXAMPLES_20260728",re.I),
 "forbidden_aag_counts": re.compile(r"\b(?:5741|2371)\b"),
 "forbidden_baseline": re.compile(r"\bBM25\b",re.I),
 "human_workflow_claim": re.compile(r"(?:two independent annotators|third-reviewer adjudication|reserved for human review|obtain human reviews)",re.I),
 "secret": re.compile(r"(?:gho_|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"),
 "absolute_private_path": re.compile(r"/(?:home|workspace|Users)/[A-Za-z0-9_.-]+/"),
}
ALLOWED_MEDIA={
 "fixtures/tiny-grid.png", # optional future synthetic fixture
}

def sha(p:Path)->str:
 return hashlib.sha256(p.read_bytes()).hexdigest()

def audit(repo:Path, manuscript:Path|None)->dict:
 findings=[]; checked=[]
 roots=[repo]
 for root in roots:
  for p in sorted(root.rglob("*")):
   if not p.is_file() or any(x in p.parts for x in {".git",".venv","build","dist","__pycache__",".pytest_cache","src/ecm_tqag.egg-info"}): continue
   rel=p.relative_to(repo).as_posix(); checked.append(rel)
   if rel == "tools/machine_semantic_audit.py": continue
   if p.suffix.lower() in MEDIA_SUFFIXES and rel not in ALLOWED_MEDIA:
    findings.append({"rule":"unexpected_media","file":rel})
   if p.suffix.lower() in TEXT_SUFFIXES:
    text=p.read_text("utf-8",errors="replace")
    for name,rx in FORBIDDEN.items():
     if rx.search(text): findings.append({"rule":name,"file":rel})
 if manuscript:
  text=manuscript.read_text("utf-8")
  checked.append(str(manuscript))
  for name,rx in FORBIDDEN.items():
   if rx.search(text): findings.append({"rule":name,"file":"MANUSCRIPT"})
  required=["machine-only","fallible machine semantic judgments","no external human annotator"]
  for phrase in required:
   if phrase.lower() not in text.lower(): findings.append({"rule":"missing_machine_only_disclosure","phrase":phrase,"file":"MANUSCRIPT"})
 return {"schema":"ecm-tqag.machine-policy-audit.v1","audit_kind":"deterministic-string-and-boundary-check","semantic_validation":False,"checked_file_count":len(checked),"findings":findings,"status":"PASS" if not findings else "FAIL","repo_tree_digest":hashlib.sha256("\n".join(f"{x}\0{sha(repo/x)}" for x in checked if not x.startswith("/") and (repo/x).is_file()).encode()).hexdigest()}

def main()->int:
 ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,default=Path(".")); ap.add_argument("--manuscript",type=Path); ap.add_argument("--output",type=Path)
 a=ap.parse_args(); result=audit(a.repo.resolve(),a.manuscript.resolve() if a.manuscript else None); payload=json.dumps(result,indent=2,sort_keys=True)+"\n"
 if a.output: a.output.write_text(payload)
 print(payload,end=""); return result["status"]!="PASS"
if __name__=="__main__": raise SystemExit(main())
