#!/usr/bin/env python3
"""Text-only vs text+image ablation over the admitted items of the reported census.

Frozen design: ABLATION_PREREGISTRATION.md (sha256 recorded in ABLATION_REPORT.json)
Authorization : runs/ablation_visual_necessity/OWNER_AUTHORIZATION.json

WHAT THIS MEASURES
  The census reports visual necessity as a 1-5 rater score with a threshold of
  3, a convention. This ablation replaces the rated score with a measurement:
  for every admitted item, answer it (a) from the recognised text alone and
  (b) from the same text plus the item's own figure crops. An item answered
  from text alone did not require the figure. The paired branch is what makes
  a text-only failure interpretable: without it, a failure could equally mean
  the item is broken.

DISCIPLINE (carried over from the census instrument)
  * zero retry, no fallback, one call per (item, branch)
  * cross-process run lock + O_EXCL per-task claim, so no task is double-called
  * reported cost accumulated per call and checked against the USD cap BEFORE
    each call; if the cap would bind, remaining tasks are recorded as
    NOT_ATTEMPTED:budget_cap instead of overspending
  * grading is deterministic (no model, no human judges correctness)
  * the census records, the gate, and the manuscript numbers are not modified

PHASES
  --phase preflight : 0 calls, offline. Verifies items, frame, image integrity,
                      authorization binding, prereg hash, and grading rules.
  --phase run       : up to 100 calls (50 items x 2 branches). Resumable.
  --phase analyse   : 0 calls. Grades recorded responses and writes the report.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import mimetypes
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.credentials import runtime_key_file
from ecm_tqag.run.ledger import RunLedger
from ecm_tqag.run.transport import OpenAITransport, TransportConfig, load_response_sidecar
from ecm_tqag.stats.intervals import clopper_pearson

GENERATOR = "qwen/qwen3-vl-8b-instruct"
# Second, independent answerer family. Reusing the generator confounds the
# measured endpoint with self-consistency; reusing a rater would break the
# measured-vs-rated agreement check, since the two would share a model.
ANSWERERS = (GENERATOR, "google/gemini-2.5-flash")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

RUN_DIR = ROOT / "runs" / "ablation_2answerer_20260824T130000Z"
CENSUS_DIR = ROOT / "runs" / "census_4arm_framec_20260824T120000Z"
MANIFEST = ROOT / "dataset_framec" / "dataset_manifest_rule4_20260816T105100Z.json"
PREREG = (ROOT.parent / "user_data" / "ECM-TQAG_ACIIDS2027"
          / "ABLATION_PREREGISTRATION.md")

BRANCHES = ("text_only", "text_image")
ARMS_REPORTED = ("ecm_full", "gate_disclosed", "direct", "structured_no_contract")
# 2 answerer families x 2 branches x the admitted items, plus a small spare.
CALL_CAP = 276


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blocked(reason: str) -> RuntimeError:
    return RuntimeError("BLOCKED_ABLATION:" + reason)


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def load_admitted() -> list[dict[str, Any]]:
    """The 50 items that passed the deterministic gate in the reported census."""
    out = []
    for path in sorted((CENSUS_DIR / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text())
        tid = rec.get("task_id", "")
        if not tid.startswith("generation::"):
            continue
        if rec.get("status") != "COMPLETE" or not rec.get("gates_passed"):
            continue
        obj = rec.get("object") or {}
        parts = tid.split("::")
        chunk = "::".join(parts[2:5])
        arm = parts[5]
        out.append({
            "item_id": f"{chunk}::{arm}",
            "chunk_id": chunk,
            "arm": arm,
            "question_type": obj["question_type"],
            "question": obj["question"],
            "gold_answer": obj["answer"],
            "options": obj.get("options"),
            "correct_option": obj.get("correct_option"),
        })
    return sorted(out, key=lambda r: r["item_id"])


def load_frame() -> dict[str, dict[str, Any]]:
    data = json.loads(MANIFEST.read_text())
    return {p["chunk_id"]: p for p in data["packages"]}


def image_parts(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Attach the chunk's own crops, re-verifying bytes and hash as the census did."""
    parts = []
    for image in package["evidence"]["images"]:
        path = ROOT / image["path"]
        raw = path.read_bytes()
        if len(raw) != image["bytes"] or sha256_bytes(raw) != image["sha256"]:
            raise blocked("IMAGE_INTEGRITY:" + image["path"])
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append({"type": "image_url", "image_url": {
            "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"}})
    return parts


# --------------------------------------------------------------------------
# request construction (identical across branches except for the image parts)
# --------------------------------------------------------------------------
SYSTEM = ("Bạn trả lời câu hỏi dựa trên tài liệu được cung cấp. "
          "Chỉ trả về JSON theo schema. Không giải thích.")


def response_format(question_type: str) -> dict[str, Any]:
    if question_type == "multiple_choice":
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["option_index"],
                  "properties": {"option_index": {"type": "integer",
                                                  "minimum": 0, "maximum": 3}}}
        name = "ablation_mcq"
    else:
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["answer"],
                  "properties": {"answer": {"type": "string", "minLength": 1}}}
        name = "ablation_short_answer"
    return {"type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema}}


def build_payload(item: Mapping[str, Any], package: Mapping[str, Any],
                  branch: str) -> dict[str, Any]:
    text = package["evidence"]["text"]
    lines = [f"NGUỒN (văn bản nhận dạng của trang):\n{text}", "",
             f"CÂU HỎI: {item['question']}"]
    if item["question_type"] == "multiple_choice":
        opts = "\n".join(f"{i}. {o}" for i, o in enumerate(item["options"]))
        lines += ["", f"CÁC PHƯƠNG ÁN:\n{opts}",
                  "", "Trả về option_index của phương án đúng."]
    else:
        lines += ["", "Trả về answer là câu trả lời ngắn."]
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(lines)}]
    if branch == "text_image":
        content += image_parts(package)
    return {"messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": content}],
            "temperature": 0, "max_tokens": 512,
            "response_format": response_format(item["question_type"])}


# --------------------------------------------------------------------------
# deterministic grading (frozen in the preregistration, section 3)
# --------------------------------------------------------------------------
def normalise(value: str) -> str:
    """casefold o ws o NFC: the census normaliser plus case folding."""
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def graded_correct(item: Mapping[str, Any], returned: Mapping[str, Any]) -> bool:
    if item["question_type"] == "multiple_choice":
        return returned.get("option_index") == item["correct_option"]
    got, gold = normalise(str(returned.get("answer", ""))), normalise(item["gold_answer"])
    if not got or not gold:
        return False
    return gold in got or got in gold


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------
def acquire_lock(run_dir: Path):
    run_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(run_dir / ".RUN_LOCK", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        raise blocked("CONCURRENT_RUN") from exc
    return fd


def claim(run_dir: Path, task_id: str) -> bool:
    """O_EXCL per-task claim: a second writer fails closed instead of re-calling."""
    path = run_dir / "state" / "claims" / (sha256_bytes(task_id.encode()) + ".claim")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    os.write(fd, task_id.encode())
    os.close(fd)
    return True


def task_path(run_dir: Path, task_id: str) -> Path:
    return run_dir / "state" / "tasks" / (sha256_bytes(task_id.encode()) + ".json")


def save_task(run_dir: Path, record: Mapping[str, Any]) -> None:
    path = task_path(run_dir, record["task_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True))
    os.replace(tmp, path)


def require_authorization(usd_cap: float) -> dict[str, Any]:
    auth = json.loads((RUN_DIR / "OWNER_AUTHORIZATION.json").read_text())
    if float(auth["usd_hard_cap"]) != float(usd_cap):
        raise blocked("AUTHORIZATION_CAP_MISMATCH")
    digest = sha256_bytes(PREREG.read_bytes())
    if digest != auth["preregistration_sha256"]:
        raise blocked("PREREGISTRATION_CHANGED_AFTER_AUTHORIZATION")
    return auth


def preflight(items, frame) -> dict[str, Any]:
    if not items:
        raise blocked("ITEM_COUNT:0")
    missing = [i["chunk_id"] for i in items if i["chunk_id"] not in frame]
    if missing:
        raise blocked("CHUNK_NOT_IN_FRAME")
    for item in items:
        package = frame[item["chunk_id"]]
        image_parts(package)                      # integrity re-verified offline
        build_payload(item, package, "text_only")
        build_payload(item, package, "text_image")
        if item["question_type"] == "multiple_choice":
            if not isinstance(item["correct_option"], int) or len(item["options"]) != 4:
                raise blocked("MCQ_SHAPE")
    return {"items": len(items),
            "tasks": len(items) * len(BRANCHES) * len(ANSWERERS),
            "answerers": list(ANSWERERS),
            "mcq": sum(i["question_type"] == "multiple_choice" for i in items),
            "short_answer": sum(i["question_type"] != "multiple_choice" for i in items),
            "preregistration_sha256": sha256_bytes(PREREG.read_bytes())}


def run(items, frame, *, usd_cap: float) -> dict[str, Any]:
    auth = require_authorization(usd_cap)
    lock = acquire_lock(RUN_DIR)
    freeze = auth["preregistration_sha256"]
    ledger = RunLedger(RUN_DIR / "ledger.jsonl", freeze_sha256=freeze,
                       cap=CALL_CAP, retry_reserve=0)
    spent = 0.0
    for path in sorted((RUN_DIR / "state" / "tasks").glob("*.json")):
        spent += float(json.loads(path.read_text()).get("reported_cost_usd") or 0.0)

    config = None
    counts = {"complete": 0, "resumed": 0, "failed": 0, "not_attempted": 0}
    try:
        with runtime_key_file("OPENROUTER_API_KEY") as key_file:
            configs = {
                model: TransportConfig(provider="openrouter", model=model,
                                       base_url=OPENROUTER_URL, api_key_file=key_file,
                                       allow_fallbacks=False, max_retries=0,
                                       timeout_sec=300)
                for model in ANSWERERS
            }
            transport = OpenAITransport(ledger)
            for item in items:
                package = frame[item["chunk_id"]]
                for answerer, branch in ((a, b) for a in ANSWERERS for b in BRANCHES):
                    config = configs[answerer]
                    task_id = f"ablation::{answerer}::{branch}::{item['item_id']}"
                    if task_path(RUN_DIR, task_id).exists():
                        counts["resumed"] += 1
                        continue
                    if spent >= usd_cap:
                        save_task(RUN_DIR, {"task_id": task_id,
                                            "status": "NOT_ATTEMPTED",
                                            "reason": "budget_cap"})
                        counts["not_attempted"] += 1
                        continue
                    if not claim(RUN_DIR, task_id):
                        continue
                    payload = build_payload(item, package, branch)
                    meta = {"phase": "ablation", "branch": branch,
                            "answerer": answerer,
                            "item_id": item["item_id"], "arm": item["arm"],
                            "question_type": item["question_type"]}
                    terminal = transport.call(config, payload, metadata=meta)
                    record: dict[str, Any] = {"task_id": task_id, "branch": branch,
                                              "answerer": answerer,
                                              "item_id": item["item_id"],
                                              "arm": item["arm"],
                                              "question_type": item["question_type"]}
                    if terminal.get("outcome") != "OK" or terminal.get("http_status") != 200:
                        record.update(status="TERMINAL_FAILURE",
                                      reason=str(terminal.get("outcome")))
                        counts["failed"] += 1
                        save_task(RUN_DIR, record)
                        continue
                    body = load_response_sidecar(ledger.path.parent, terminal)
                    usage = body.get("usage") or {}
                    cost = usage.get("cost")
                    cost = float(cost) if isinstance(cost, (int, float)) else None
                    if cost:
                        spent += cost
                    try:
                        content = body["choices"][0]["message"]["content"]
                        returned = json.loads(content)
                    except Exception:
                        record.update(status="TERMINAL_FAILURE", reason="UNDECODABLE")
                        counts["failed"] += 1
                        save_task(RUN_DIR, record)
                        continue
                    record.update(status="COMPLETE", returned=returned,
                                  reported_cost_usd=cost)
                    counts["complete"] += 1
                    save_task(RUN_DIR, record)
    finally:
        os.close(lock)
    return {"counts": counts, "spent_usd": round(spent, 6), "usd_cap": usd_cap}


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------
def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact conditional test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    from math import comb
    hi = max(b, c)
    tail = sum(comb(n, i) for i in range(hi, n + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def analyse(items) -> dict[str, Any]:
    """Per-answerer analysis.

    The endpoint is computed independently for each answerer family, and the two
    are then compared. Pooling them would hide the very confound this run exists
    to expose: the original ablation used the generator as its own answerer, so a
    high text-only score could reflect self-consistency rather than the item.
    """
    by_item = {i["item_id"]: i for i in items}
    graded: dict[str, dict[str, dict[str, Any]]] = {a: {} for a in ANSWERERS}
    for path in sorted((RUN_DIR / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text())
        if rec.get("status") != "COMPLETE":
            continue
        item = by_item.get(rec["item_id"])
        answerer = rec.get("answerer")
        if item is None or answerer not in graded:
            continue
        graded[answerer].setdefault(rec["item_id"], {})[rec["branch"]] = graded_correct(
            item, rec["returned"])

    def ci(successes: int, n: int) -> list[float]:
        if n <= 0:
            return [0.0, 0.0]
        out = clopper_pearson(successes, n)
        return [round(out["lower"], 4), round(out["upper"], 4)]

    report: dict[str, Any] = {
        "schema": "ecm-tqag.ablation.visual-necessity.v2-two-answerers",
        "preregistration_sha256": sha256_bytes(PREREG.read_bytes()),
        "answerers": list(ANSWERERS),
        "generator_is_first_answerer": ANSWERERS[0] == GENERATOR,
        "per_answerer": {},
    }

    necessity_by_answerer: dict[str, dict[str, bool]] = {}
    for answerer in ANSWERERS:
        paired = {k: v for k, v in graded[answerer].items() if set(v) == set(BRANCHES)}
        block: dict[str, Any] = {
            "n_items_with_both_branches": len(paired),
            "branch_accuracy": {}, "necessity": {}, "by_arm": {}, "mcq_only": {},
        }
        for branch in BRANCHES:
            k = sum(1 for v in paired.values() if v[branch])
            block["branch_accuracy"][branch] = {
                "correct": k, "n": len(paired),
                "rate": round(k / len(paired), 4) if paired else None,
                "ci95": ci(k, len(paired))}

        necessary = {k: (not v["text_only"]) and v["text_image"] for k, v in paired.items()}
        necessity_by_answerer[answerer] = necessary
        k = sum(necessary.values())
        # Discordant pairs of the paired table, for the exact test.
        b = sum(1 for v in paired.values() if v["text_image"] and not v["text_only"])
        c = sum(1 for v in paired.values() if v["text_only"] and not v["text_image"])
        block["necessity"] = {
            "definition": "text_image correct AND text_only incorrect",
            "visually_necessary": k, "n": len(paired),
            "rate": round(k / len(paired), 4) if paired else None,
            "ci95": ci(k, len(paired)),
            "discordant_image_only": b,
            "discordant_text_only": c,
            "p_two_sided_exact_mcnemar": round(exact_mcnemar(b, c), 4)}

        for arm in ARMS_REPORTED:
            ids = [k for k in paired if by_item[k]["arm"] == arm]
            if not ids:
                continue
            block["by_arm"][arm] = {
                "n": len(ids),
                "text_only_correct": sum(paired[i]["text_only"] for i in ids),
                "text_image_correct": sum(paired[i]["text_image"] for i in ids),
                "visually_necessary": sum(necessary[i] for i in ids)}

        mcq = [k for k in paired if by_item[k]["question_type"] == "multiple_choice"]
        if mcq:
            block["mcq_only"] = {
                "n": len(mcq),
                "text_only_correct": sum(paired[i]["text_only"] for i in mcq),
                "text_image_correct": sum(paired[i]["text_image"] for i in mcq),
                "visually_necessary": sum(necessary[i] for i in mcq)}
        report["per_answerer"][answerer] = block

    # Cross-answerer agreement on the measured endpoint. Disagreement here is the
    # quantity that tells whether the single-answerer figure was answerer-specific.
    if len(ANSWERERS) == 2:
        a, b_ans = ANSWERERS
        shared = sorted(set(necessity_by_answerer[a]) & set(necessity_by_answerer[b_ans]))
        both = sum(1 for k in shared if necessity_by_answerer[a][k] and necessity_by_answerer[b_ans][k])
        only_a = sum(1 for k in shared if necessity_by_answerer[a][k] and not necessity_by_answerer[b_ans][k])
        only_b = sum(1 for k in shared if not necessity_by_answerer[a][k] and necessity_by_answerer[b_ans][k])
        neither = len(shared) - both - only_a - only_b
        po = (both + neither) / len(shared) if shared else None
        # Cohen's kappa on the binary measured-necessity label.
        kappa = None
        if shared:
            n = len(shared)
            pa = (both + only_a) / n
            pb = (both + only_b) / n
            pe = pa * pb + (1 - pa) * (1 - pb)
            kappa = round((po - pe) / (1 - pe), 4) if pe < 1 else None
        report["answerer_agreement"] = {
            "n_shared_items": len(shared),
            "necessary_under_both": both,
            f"necessary_only_{a}": only_a,
            f"necessary_only_{b_ans}": only_b,
            "necessary_under_neither": neither,
            "raw_agreement": round(po, 4) if po is not None else None,
            "cohen_kappa": kappa,
            "p_two_sided_exact_mcnemar": round(exact_mcnemar(only_a, only_b), 4),
            "role": "confound check on the single-answerer endpoint, not an endpoint"}

    out = RUN_DIR / "ABLATION_REPORT.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True,
                    choices=("preflight", "run", "analyse"))
    ap.add_argument("--usd-cap", type=float)
    args = ap.parse_args()

    items, frame = load_admitted(), load_frame()
    if args.phase == "preflight":
        print(json.dumps(preflight(items, frame), indent=1))
        return 0
    if args.phase == "run":
        if args.usd_cap is None:
            raise SystemExit("--usd-cap is required for --phase run")
        preflight(items, frame)
        print(json.dumps(run(items, frame, usd_cap=args.usd_cap), indent=1))
        return 0
    print(json.dumps(analyse(items), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
