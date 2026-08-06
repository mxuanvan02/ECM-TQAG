from __future__ import annotations
import argparse, json
from pathlib import Path
from .core import parse_response, validate_directory
from .constructed import validate_constructed_directory
from .runner import export_dataset, run, verify_run
from .conference_eval import (
    run_adjudicated_statistics,
    run_contract_experiment,
    validate_real_data_inventory,
    verify_contract_report,
)
from .generator import generate, validate_generated
from .construction import validate_construction

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog="ecm-tqag"); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("validate"); p.add_argument("directory",type=Path)
    p=sub.add_parser("validate-items"); p.add_argument("directory",type=Path)
    p=sub.add_parser("parse"); p.add_argument("file",type=Path); p.add_argument("--content-type",default="application/json")
    p=sub.add_parser("run"); p.add_argument("config",type=Path)
    p=sub.add_parser("verify-run"); p.add_argument("summary",type=Path); p.add_argument("--config",type=Path); p.add_argument("--packages",type=Path)
    p=sub.add_parser("export-dataset"); p.add_argument("summary",type=Path); p.add_argument("output",type=Path)
    p=sub.add_parser("generate"); p.add_argument("input",type=Path); p.add_argument("output_dir",type=Path); p.add_argument("--replace",action="store_true")
    p=sub.add_parser("validate-generated"); p.add_argument("output_dir",type=Path); p.add_argument("--source",type=Path)
    p=sub.add_parser("validate-construction"); p.add_argument("record",type=Path)
    p=sub.add_parser("contract-eval"); p.add_argument("output",type=Path); p.add_argument("inputs",type=Path,nargs="+")
    p=sub.add_parser("verify-contract-eval"); p.add_argument("report",type=Path); p.add_argument("--source",type=Path,nargs="+")
    p=sub.add_parser("validate-real-inventory"); p.add_argument("inventory",type=Path)
    p=sub.add_parser("adjudicated-statistics"); p.add_argument("results",type=Path); p.add_argument("output",type=Path); p.add_argument("--validation",type=Path,required=True); p.add_argument("--adjudication",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="validate": result=validate_directory(args.directory)
        elif args.command=="validate-items": result=validate_constructed_directory(args.directory)
        elif args.command=="parse": result={"status":"PASS","records":parse_response(args.file.read_text(encoding="utf-8"),args.content_type)}
        elif args.command=="run": result=run(args.config)
        elif args.command=="verify-run": result=verify_run(args.summary, args.config, args.packages)
        elif args.command=="generate": result=generate(args.input, args.output_dir, replace=args.replace)
        elif args.command=="validate-generated": result=validate_generated(args.output_dir, args.source)
        elif args.command=="validate-construction": result=validate_construction(json.loads(args.record.read_text(encoding="utf-8")))
        elif args.command=="contract-eval": result=run_contract_experiment(args.inputs, args.output)
        elif args.command=="verify-contract-eval": result=verify_contract_report(args.report, sources=args.source)
        elif args.command=="validate-real-inventory":
            result=validate_real_data_inventory(args.inventory)
            print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result["status"] == "ELIGIBLE" else 2
        elif args.command=="adjudicated-statistics": result=run_adjudicated_statistics(args.results, args.output, args.validation, args.adjudication)
        else: result=export_dataset(args.summary, args.output)
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc)})); return 2
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
