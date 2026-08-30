#!/usr/bin/env python3
"""Frame-D text-only ablation: is the census null the CORPUS or the INSTRUMENT?

Derived from run_ablation_visual_necessity.py (the sealed frame-C ablation) by
rebinding only: census run, frame manifest, pre-registration, run directory and
call cap. That runner is sealed evidence and is NOT edited. The branch design,
the deterministic grading rule, the transport discipline and the endpoint
definitions are carried over unchanged, so the two ablations are comparable.

WHAT THIS ADDS OVER THE FRAME-C ABLATION
  * Two PRE-REGISTERED STRATA, fixed in
    prospective/v3103_round2/ROUND4_FRAMED_ABLATION_PREREGISTRATION.json before
    any call:
      - question_reference: does the question text point at a figure, or is it
        anchored in prose? This is the split that separates H1 (the document
        class restates figures in prose) from H2 (the verbatim-quote gate pushes
        the generator toward prose-anchored questions).
      - chunk_composition: embedded raster vs rendered-vector-only. This reads
        directly on the owner's hypothesis that necessity fails because the
        figures are mostly tables.
  * An exact two-sided McNemar test on the branch-discordant items, which the
    frame-C ablation reported only as counts.
  * A DECLARED EXCLUSION of 5 short-answer items whose gold answer normalises to
    <= 2 characters. The containment grading rule would auto-pass those in both
    branches, turning a generation defect into evidence that the figure was
    unnecessary. The exclusion is listed item-by-item in the pre-registration,
    its arm asymmetry is declared there, and both endpoints are additionally
    reported over all 120 items as a sensitivity check.

PHASES
  --phase preflight : 0 calls, offline. Verifies items, frame, image integrity,
                      authorization binding, prereg hash, strata sizes.
  --phase run       : up to 240 calls (120 items x 2 branches). Resumable.
  --phase analyse   : 0 calls. Grades recorded responses and writes the report.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import math
import mimetypes
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ecm_tqag.official_credentials import runtime_key_file
from ecm_tqag.run.ledger import RunLedger
from ecm_tqag.run.transport import OpenAITransport, TransportConfig, load_response_sidecar
from ecm_tqag.stats.intervals import clopper_pearson
from ecm_tqag.stats.paired import exact_mcnemar

GENERATOR = "qwen/qwen3-vl-8b-instruct"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

RUN_DIR = ROOT / "runs" / "ablation_framed_20260830T060000Z"
CENSUS_DIR = ROOT / "runs" / "round4_framed_census_20260829T200000Z"
MANIFEST = ROOT / "dataset_framed" / "dataset_manifest_framed_20260829T195643Z.json"
PREREG = (ROOT.parent / "prospective" / "v3103_round2"
          / "ROUND4_FRAMED_ABLATION_PREREGISTRATION.json")

BRANCHES = ("text_only", "text_image")
CALL_CAP = 244  # 240 tasks + 4 spare attempts, matching the authorization


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blocked(reason: str) -> RuntimeError:
    return RuntimeError("BLOCKED_ABLATION_D:" + reason)


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def load_admitted() -> list[dict[str, Any]]:
    """Every generation that passed the deterministic gate G in the frame-D census."""
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


# --------------------------------------------------------------------------
# the pre-registration, and every population decision it fixes
# --------------------------------------------------------------------------
# Populations, strata and exclusions are READ from the frozen record rather than
# restated here. A hardcoded copy could drift from what was pre-registered; a
# read cannot, and the reader binds the record by sha256 either way.
def load_prereg() -> dict[str, Any]:
    return json.loads(PREREG.read_text(encoding="utf-8"))


def fold(text: str) -> str:
    """casefold o whitespace-collapse o NFC, the grading normaliser."""
    return " ".join(unicodedata.normalize("NFC", text or "").split()).casefold()


def excluded_item_ids(prereg: Mapping[str, Any]) -> set[str]:
    return set(prereg["declared_exclusion_before_execution"]["item_ids"])


def figure_pattern(prereg: Mapping[str, Any]):
    raw = prereg["pre_registered_strata"]["question_reference"]["regex"]
    return re.compile(raw, re.IGNORECASE)


def question_stratum(item: Mapping[str, Any], pattern) -> str:
    """H1-vs-H2 split: does the question point at a figure, or at the prose?"""
    return ("question_refers_to_figure" if pattern.search(fold(item["question"]))
            else "question_does_not_refer_to_figure")


def composition_stratum(package: Mapping[str, Any]) -> str:
    """The owner's hypothesis: does the chunk carry a real image, or only tables
    rendered out of the vector layer?"""
    sources = {img.get("source") for img in package["evidence"]["images"]}
    return ("has_embedded_raster" if "embedded_raster" in sources
            else "rendered_vector_only")


def strata_of(items, frame, prereg) -> dict[str, dict[str, list[str]]]:
    """Membership over the SCORED population, which is what the record sizes."""
    pattern = figure_pattern(prereg)
    excluded = excluded_item_ids(prereg)
    out: dict[str, dict[str, list[str]]] = {
        "question_reference": {}, "chunk_composition": {}}
    for item in items:
        if item["item_id"] in excluded:
            continue
        out["question_reference"].setdefault(
            question_stratum(item, pattern), []).append(item["item_id"])
        out["chunk_composition"].setdefault(
            composition_stratum(frame[item["chunk_id"]]), []).append(item["item_id"])
    return out


def preflight(items, frame) -> dict[str, Any]:
    """Zero-call offline readiness check.

    Fails closed if the live population no longer matches the frozen record:
    counts, the declared exclusion, and BOTH pre-registered strata are checked
    against the pre-registration, not merely recomputed and reported. The
    inherited frame-C assertion `len(items) == 50` is replaced by a check
    against the record, because a hardcoded n from another frame is exactly the
    class of defect that silently mismeasures a new one.
    """
    prereg = load_prereg()
    problems: list[str] = []

    n_admitted = int(prereg["items"]["n_admitted"])
    n_scored = int(prereg["items"]["n_scored"])
    if len(items) != n_admitted:
        problems.append(f"admitted_count:{len(items)}!={n_admitted}")

    excluded = excluded_item_ids(prereg)
    live_ids = {i["item_id"] for i in items}
    if not excluded <= live_ids:
        problems.append("declared_exclusion_names_absent_item")
    if len(items) - len(excluded) != n_scored:
        problems.append(f"scored_count:{len(items) - len(excluded)}!={n_scored}")

    # The exclusion rule must still describe the items it names, so a later
    # regeneration cannot quietly change what is being excluded.
    for item in items:
        trivial = (item["question_type"] != "multiple_choice"
                   and len(fold(item["gold_answer"])) <= 2)
        if trivial and item["item_id"] not in excluded:
            problems.append("trivial_gold_not_excluded:" + item["item_id"])
        if item["item_id"] in excluded and not trivial:
            problems.append("excluded_item_is_not_trivial:" + item["item_id"])

    missing = [i["chunk_id"] for i in items if i["chunk_id"] not in frame]
    if missing:
        problems.append(f"chunk_not_in_frame:{len(missing)}")

    for item in items:
        package = frame.get(item["chunk_id"])
        if package is None:
            continue
        image_parts(package)                      # integrity re-verified offline
        build_payload(item, package, "text_only")
        build_payload(item, package, "text_image")
        if item["question_type"] == "multiple_choice":
            if not isinstance(item["correct_option"], int) or len(item["options"]) != 4:
                problems.append("mcq_shape:" + item["item_id"])

    strata = strata_of(items, frame, prereg)
    declared = prereg["pre_registered_strata"]
    for name, key in (("question_reference", "question_reference"),
                      ("chunk_composition", "chunk_composition")):
        want = {k: int(v) for k, v in declared[key]["sizes"].items()}
        got = {k: len(v) for k, v in strata[name].items()}
        if got != want:
            problems.append(f"stratum_sizes_{name}:{got}!={want}")

    return {
        "schema": "ecm-tqag.ablation.framed-preflight.v1",
        "preregistration": PREREG.name,
        "preregistration_sha256": sha256_bytes(PREREG.read_bytes()),
        "census_run": CENSUS_DIR.name,
        "frame_manifest_sha256": sha256_bytes(MANIFEST.read_bytes()),
        "items_admitted": len(items),
        "items_excluded": len(excluded),
        "items_scored": len(items) - len(excluded),
        "tasks": len(items) * len(BRANCHES),
        "call_cap": CALL_CAP,
        "mcq": sum(i["question_type"] == "multiple_choice" for i in items),
        "short_answer": sum(i["question_type"] != "multiple_choice" for i in items),
        "stratum_sizes": {n: {k: len(v) for k, v in s.items()}
                          for n, s in strata.items()},
        "calls_made_by_preflight": 0,
        "problems": problems,
        "verdict": "READY" if not problems else "BLOCKED",
    }


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
            config = TransportConfig(provider="openrouter", model=GENERATOR,
                                     base_url=OPENROUTER_URL, api_key_file=key_file,
                                     allow_fallbacks=False, max_retries=0,
                                     timeout_sec=300)
            transport = OpenAITransport(ledger)
            for item in items:
                package = frame[item["chunk_id"]]
                for branch in BRANCHES:
                    task_id = f"ablation::{branch}::{item['item_id']}"
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
                            "item_id": item["item_id"], "arm": item["arm"],
                            "question_type": item["question_type"]}
                    terminal = transport.call(config, payload, metadata=meta)
                    record: dict[str, Any] = {"task_id": task_id, "branch": branch,
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
def prereg() -> dict[str, Any]:
    """The frozen pre-registration. Read at runtime so the exclusion list, the
    stratum regex and the stratum sizes come from the record rather than from a
    copy in this file that could drift away from it."""
    return json.loads(PREREG.read_text(encoding="utf-8"))


def excluded_ids() -> set[str]:
    doc = prereg()["declared_exclusion_before_execution"]
    return set(doc["item_ids"])


def figure_ref_re():
    pattern = prereg()["pre_registered_strata"]["question_reference"]["regex"]
    return re.compile(pattern, re.I)


def exact_mcnemar_p(b: int, c: int) -> float:
    """Exact two-sided McNemar: conditional binomial on the discordant count.

    p = min(1, 2 * P(X <= min(b,c) | b+c, 1/2)); d == 0 yields 1.0 by definition.
    Same form as the census instrument's test, kept local so this runner does not
    depend on a module bound to another frame's expected n.
    """
    d = b + c
    if d == 0:
        return 1.0
    lo = min(b, c)
    tail = sum(math.comb(d, i) for i in range(lo + 1)) / (2 ** d)
    return min(1.0, 2.0 * tail)


def analyse(items) -> dict[str, Any]:
    by_item = {i["item_id"]: i for i in items}
    graded: dict[str, dict[str, Any]] = {}
    statuses: dict[str, int] = {}
    for path in sorted((RUN_DIR / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text())
        statuses[str(rec.get("status"))] = statuses.get(str(rec.get("status")), 0) + 1
        if rec.get("status") != "COMPLETE":
            continue
        item = by_item.get(rec["item_id"])
        if item is None:
            continue
        graded.setdefault(rec["item_id"], {})[rec["branch"]] = graded_correct(
            item, rec["returned"])

    both = {k: v for k, v in graded.items() if set(v) == set(BRANCHES)}
    dropped = excluded_ids()
    # PRIMARY population: the declared exclusion applied.
    paired = {k: v for k, v in both.items() if k not in dropped}

    def ci(successes: int, n: int) -> list[float]:
        if n <= 0:
            return [0.0, 0.0]
        out = clopper_pearson(successes, n)
        return [round(out["lower"], 4), round(out["upper"], 4)]

    def block(ids: list[str], scored: dict[str, dict[str, bool]]) -> dict[str, Any]:
        """Every endpoint over one set of item ids: branch rates, measured
        necessity, the paired gain table and its exact McNemar p."""
        n = len(ids)
        if not n:
            return {"n": 0}
        t_only = sum(1 for i in ids if scored[i]["text_only"])
        t_img = sum(1 for i in ids if scored[i]["text_image"])
        nec = [i for i in ids
               if scored[i]["text_image"] and not scored[i]["text_only"]]
        # paired gain table: b = image helped, c = image hurt
        b = len(nec)
        c = sum(1 for i in ids
                if scored[i]["text_only"] and not scored[i]["text_image"])
        v_star = sum(1 for i in ids if not scored[i]["text_only"])
        return {
            "n": n,
            "text_only": {"correct": t_only, "rate": round(t_only / n, 4),
                          "ci95": ci(t_only, n)},
            "text_image": {"correct": t_img, "rate": round(t_img / n, 4),
                           "ci95": ci(t_img, n)},
            "measured_visual_necessity_V_star": {
                "definition": "V*(i) = 1 - R_TEXT(i): item not answerable from text alone",
                "count": v_star, "rate": round(v_star / n, 4), "ci95": ci(v_star, n)},
            "figure_attributable_G": {
                "definition": "image made the item answerable: TEXT wrong and TEXT+IMG right",
                "count": b, "rate": round(b / n, 4), "ci95": ci(b, n),
                "item_ids": sorted(nec)},
            "paired_table": {"image_helped_b": b, "image_hurt_c": c,
                             "discordant": b + c,
                             "concordant": n - b - c},
            "mcnemar_exact_two_sided_p": round(exact_mcnemar_p(b, c), 6),
        }

    report: dict[str, Any] = {
        "schema": "ecm-tqag.ablation.framed-visual-necessity.v1",
        "question_this_answers": prereg()["question_this_answers"],
        "preregistration": PREREG.name,
        "preregistration_sha256": sha256_bytes(PREREG.read_bytes()),
        "census_run": CENSUS_DIR.name,
        "task_status_counts": statuses,
        "items_with_both_branches": len(both),
        "declared_exclusion_applied": {
            "n": len(both) - len(paired),
            "rule": prereg()["declared_exclusion_before_execution"]["rule"],
            "item_ids": sorted(dropped & set(both)),
        },
        "PRIMARY_ALL": block(sorted(paired), paired),
    }

    mcq = sorted(k for k in paired if by_item[k]["question_type"] == "multiple_choice")
    report["PRIMARY_MCQ"] = {
        **block(mcq, paired),
        "chance_level": 0.25,
        "why_reported_separately": ("graded by option index alone, with no string "
                                    "containment heuristic"),
    }

    # ---- pre-registered strata (descriptive; membership frozen before the run) ----
    fig_re = figure_ref_re()
    qref = {"question_refers_to_figure": [], "question_does_not_refer_to_figure": []}
    for k in sorted(paired):
        key = ("question_refers_to_figure" if fig_re.search(by_item[k]["question"])
               else "question_does_not_refer_to_figure")
        qref[key].append(k)

    frame = load_frame()
    comp = {"has_embedded_raster": [], "rendered_vector_only": []}
    for k in sorted(paired):
        images = frame[by_item[k]["chunk_id"]]["evidence"]["images"]
        key = ("has_embedded_raster"
               if any(im.get("source") == "embedded_raster" for im in images)
               else "rendered_vector_only")
        comp[key].append(k)

    strata_doc = prereg()["pre_registered_strata"]
    report["pre_registered_strata"] = {
        "why_descriptive": strata_doc["stratum_tests_are_descriptive"],
        "question_reference": {
            "reads_on": strata_doc["question_reference"]["reads_on"],
            "regex": strata_doc["question_reference"]["regex"],
            "strata": {name: block(ids, paired) for name, ids in qref.items()},
        },
        "chunk_composition": {
            "reads_on": strata_doc["chunk_composition"]["reads_on"],
            "definition": strata_doc["chunk_composition"]["definition"],
            "strata": {name: block(ids, paired) for name, ids in comp.items()},
        },
    }

    # ---- per-arm (secondary, confounded by admission; declared in the prereg) ----
    report["by_arm"] = {
        "why_confounded": ("the arms admit different item sets, so each arm's rate "
                           "is measured on different items; conditional on admission"),
        "arms": {arm: block(sorted(k for k in paired if by_item[k]["arm"] == arm),
                            paired)
                 for arm in ("ecm_full", "direct", "structured_no_contract")},
    }

    # ---- sensitivity: excluded items scored correct in BOTH branches ----
    sens = dict(paired)
    for k in sorted(dropped & set(both)):
        sens[k] = {"text_only": True, "text_image": True}
    report["sensitivity_all_items_exclusions_scored_correct"] = {
        "why": prereg()["declared_exclusion_before_execution"]["sensitivity_required"],
        "endpoint": block(sorted(sens), sens),
    }

    out = RUN_DIR / "ABLATION_REPORT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
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
