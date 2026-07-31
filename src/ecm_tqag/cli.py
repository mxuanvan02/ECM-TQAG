from __future__ import annotations
import argparse, json
from pathlib import Path
from .core import parse_response, validate_directory
from .constructed import validate_constructed_directory
from .runner import export_dataset, run, verify_run

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog="ecm-tqag"); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("validate"); p.add_argument("directory",type=Path)
    p=sub.add_parser("validate-items"); p.add_argument("directory",type=Path)
    p=sub.add_parser("parse"); p.add_argument("file",type=Path); p.add_argument("--content-type",default="application/json")
    p=sub.add_parser("run"); p.add_argument("config",type=Path)
    p=sub.add_parser("verify-run"); p.add_argument("summary",type=Path); p.add_argument("--config",type=Path); p.add_argument("--packages",type=Path)
    p=sub.add_parser("export-dataset"); p.add_argument("summary",type=Path); p.add_argument("output",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=="validate": result=validate_directory(args.directory)
        elif args.command=="validate-items": result=validate_constructed_directory(args.directory)
        elif args.command=="parse": result={"status":"PASS","records":parse_response(args.file.read_text(encoding="utf-8"),args.content_type)}
        elif args.command=="run": result=run(args.config)
        elif args.command=="verify-run": result=verify_run(args.summary, args.config, args.packages)
        else: result=export_dataset(args.summary, args.output)
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc)})); return 2
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
