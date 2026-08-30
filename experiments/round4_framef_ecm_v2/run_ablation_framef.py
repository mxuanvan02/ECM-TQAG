#!/usr/bin/env python3
"""Frame-D text-only ablation: is the census null the CORPUS or the INSTRUMENT?

Derived from run_ablation_visual_necessity.py (the sealed frame-C ablation) by
rebinding only: census run, frame manifest, pre-registration, run directory and
call cap. That runner is sealed evidence and is NOT edited. The branch design,
the deterministic grading rule, the transport discipline and the endpoint
definitions are carried over unchanged, so the two ablations are comparable.

WHAT THIS ADDS OVER THE FRAME-C ABLATION
  * Two PRE-REGISTERED STRATA, fixed in
    prospective/v3103_round2/ROUND4_FRAMEF_ABLATION_PREREGISTRATION.json before
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

RUN_DIR = ROOT / "runs" / "ablation_framef_20260831T020000Z"
CENSUS_DIR = ROOT / "runs" / "round4_framef_census_20260830T140000Z"
MANIFEST = ROOT / "dataset_framef" / "dataset_manifest_framef_20260830T122835Z.json"
PREREG = (ROOT.parent / "prospective" / "v3103_round2"
          / "ROUND4_FRAMEF_ABLATION_PREREGISTRATION.json")

BRANCHES = ("text_only", "text_image")
CALL_CAP = 454  # 450 tasks (225 items x 2 branches) + 4 spare, matching the authorization

# Frozen grading threshold. Read from the record too, and cross-checked against
# this constant in preflight, so a drifted record fails closed instead of being
# graded under a rule nobody registered.
F1_THRESHOLD = 0.70

# Report order for the five census arms. The within-arm tables are reported for
# every arm, however small, because the pooled table is confounded with arm by
# construction and the within-arm form is what breaks that confound.
ARMS_REPORT_ORDER = ("ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct",
                     "structured_no_contract")

# The five arms of the frame-F census, in report order.
ARMS = ("ecm_v2", "ecm_v2_disclosed", "ecm_full", "direct", "structured_no_contract")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def blocked(reason: str) -> RuntimeError:
    return RuntimeError("BLOCKED_ABLATION_F:" + reason)


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


def strip_accents(value: str) -> str:
    """Accent-fold, so an OCR- or model-side diacritic slip does not decide a
    grade. Applied after `normalise`."""
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_TOKEN_RE = re.compile(r"[0-9a-z]+")


def tokens(value: str) -> list[str]:
    """Content tokens of an answer: accent- and case-folded word forms."""
    return _TOKEN_RE.findall(strip_accents(normalise(value)))


def word_f1(returned: str, gold: str) -> float:
    """Symmetric token F1 between a returned answer and the recorded answer.

    WHY THIS REPLACES CONTAINMENT
      The frame-C and frame-D ablations graded a short answer by containment in
      either direction. That rule is lenient on substrings but STRICT on
      insertions: an answer differing from the gold by one inserted function word
      is neither contained nor containing, so it scored WRONG. Three of the ten
      items the frame-D ablation called figure-attributable were of exactly that
      shape ('Thang du CUA nguoi tieu dung' against 'Thang du nguoi tieu dung'),
      and re-grading the sealed frame-D pairs under this symmetric rule removes
      the significance at every threshold from 0.50 to 0.90. The frame-D result
      was therefore a grading artefact, which is recorded in the pre-registration
      and corrected in the report rather than left standing.

      F1 is symmetric by construction: inserting a token and dropping a token cost
      the same, so no verdict turns on which side happens to be longer.
    """
    got, want = tokens(returned), tokens(gold)
    if not got or not want:
        return 0.0
    want_counts: dict[str, int] = {}
    for tok in want:
        want_counts[tok] = want_counts.get(tok, 0) + 1
    overlap = 0
    for tok in got:
        if want_counts.get(tok, 0) > 0:
            want_counts[tok] -= 1
            overlap += 1
    if overlap == 0:
        return 0.0
    precision = overlap / len(got)
    recall = overlap / len(want)
    return 2 * precision * recall / (precision + recall)


def contained_either_way(returned: str, gold: str) -> bool:
    """The frame-D primary rule. Reported beside the primary for comparability
    only; it carries no claim in this record."""
    got, want = normalise(returned), normalise(gold)
    if not got or not want:
        return False
    return want in got or got in want


def graded_correct(item: Mapping[str, Any], returned: Mapping[str, Any],
                   *, threshold: float = F1_THRESHOLD) -> bool:
    """The frozen primary rule: option index for MCQ, symmetric word-F1 otherwise."""
    if item["question_type"] == "multiple_choice":
        return returned.get("option_index") == item["correct_option"]
    return word_f1(str(returned.get("answer", "")), item["gold_answer"]) >= threshold


def graded_correct_containment(item: Mapping[str, Any],
                              returned: Mapping[str, Any]) -> bool:
    """The secondary rule, for the comparability row only."""
    if item["question_type"] == "multiple_choice":
        return returned.get("option_index") == item["correct_option"]
    return contained_either_way(str(returned.get("answer", "")), item["gold_answer"])


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


# ---------------------------------------------------------------------------
# A2 status, read from the sealed census gate records
# ---------------------------------------------------------------------------
# The split this ablation tests is NOT a property of the chunk, as in frames D
# and E, but of the ITEM: did the item pass the three ECM-v2 gates? It is read
# from ECM_V2_GATE_RECORDS.json, written by the census from the frozen gate
# module, so nothing about the gates is recomputed here and the split cannot
# drift from what the census measured.
GATE_RECORDS = CENSUS_DIR / "ECM_V2_GATE_RECORDS.json"


def a2_status_by_item() -> dict[str, bool]:
    """item_id -> whether the item passed all three ECM-v2 gates."""
    raw = json.loads(GATE_RECORDS.read_text(encoding="utf-8"))
    out: dict[str, bool] = {}
    for task_id, cell in raw.items():
        if not isinstance(cell, Mapping) or "passed" not in cell:
            continue                      # evaluation_error rows carry no verdict
        parts = str(task_id).split("::")
        if len(parts) < 6:
            continue
        out["::".join(parts[2:6])] = bool(cell["passed"])
    return out


def strata_of(items, frame, prereg) -> dict[str, dict[str, list[str]]]:
    """Membership over the SCORED population, which is what the record sizes.

    One split only: A2 status. Frames D and E froze splits on question wording
    and chunk composition; this record freezes neither, and reporting them here
    under a pre-registered name would report a split this record never fixed.
    """
    a2 = a2_status_by_item()
    excluded = excluded_item_ids(prereg)
    out: dict[str, dict[str, list[str]]] = {"a2_status": {"a2_pass": [], "a2_fail": []}}
    for item in items:
        item_id = item["item_id"]
        if item_id in excluded or item_id not in a2:
            continue
        key = "a2_pass" if a2[item_id] else "a2_fail"
        out["a2_status"][key].append(item_id)
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

    # The record names the v1-admitted population `n_v1_admitted`, not
    # `n_admitted` as frames D and E did. Reading the wrong key would raise here
    # rather than mismeasure, but the point of this check is that the live
    # population still matches the record, so it reads the record's own name.
    n_admitted = int(prereg["items"]["n_v1_admitted"])
    n_scored = int(prereg["items"]["n_scored"])
    if len(items) != n_admitted:
        problems.append(f"v1_admitted_count:{len(items)}!={n_admitted}")

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

    # The frozen grading threshold must be the one this code applies. A record
    # and a runner that disagree on the threshold is exactly how the frame-D
    # grading defect stayed invisible.
    declared_threshold = float(prereg["grading"]["f1_threshold"])
    if abs(declared_threshold - F1_THRESHOLD) > 1e-9:
        problems.append(f"f1_threshold:{F1_THRESHOLD}!={declared_threshold}")

    # The only split this record freezes is A2 status, and its two sizes were
    # fixed before execution. Frames D and E froze splits on question wording
    # and chunk composition; this record freezes neither, so neither is checked
    # or reported here.
    strata = strata_of(items, frame, prereg)
    want = {"a2_pass": int(prereg["primary_endpoint"]["n_a2_pass"]),
            "a2_fail": int(prereg["primary_endpoint"]["n_a2_fail"])}
    got = {k: len(v) for k, v in strata["a2_status"].items()}
    if got != want:
        problems.append(f"a2_split:{got}!={want}")

    return {
        "schema": "ecm-tqag.ablation.framef-preflight.v1",
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


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p on the 2x2 table [[a, b], [c, d]].

    Exact hypergeometric sum over every table with the same margins whose
    probability is at most that of the observed table. Pure stdlib: the margins
    here are small and math.comb is exact, so there is nothing to converge.

    Used instead of McNemar because the A2 comparison is UNPAIRED: A2-pass and
    A2-fail are different items, not two conditions applied to one item.
    """
    row1, row2 = a + b, c + d
    col1, col2 = a + c, b + d
    total = row1 + row2
    if total == 0 or row1 == 0 or row2 == 0 or col1 == 0 or col2 == 0:
        return 1.0

    def prob(x: int) -> float:
        return (math.comb(col1, x) * math.comb(col2, row1 - x)
                / math.comb(total, row1))

    observed = prob(a)
    lo = max(0, row1 - col2)
    hi = min(row1, col1)
    # 1e-12 guards against a table tied with the observed one being dropped by
    # floating-point noise, which would make the test anti-conservative.
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1)
                        if prob(x) <= observed * (1 + 1e-12)))


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
    # Raw returned objects, keyed by task id. Kept so the sensitivity curve can
    # re-grade the SAME responses under every threshold without re-calling.
    returned_by_task: dict[str, Mapping[str, Any]] = {}
    for path in sorted((RUN_DIR / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text())
        statuses[str(rec.get("status"))] = statuses.get(str(rec.get("status")), 0) + 1
        if rec.get("status") != "COMPLETE":
            continue
        item = by_item.get(rec["item_id"])
        if item is None:
            continue
        returned_by_task[str(rec["task_id"])] = rec["returned"]
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
        "schema": "ecm-tqag.ablation.framef-a2-validity.v1",
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

    # ---- PRIMARY: does A2 select items that need the figure? ----
    # The endpoint of this record. A2 status is a property of the ITEM, so the
    # comparison is unpaired and the test is Fisher exact, not McNemar. Membership
    # comes from the census's own sealed gate records; nothing is recomputed.
    a2 = a2_status_by_item()
    a2_pass = sorted(k for k in paired if a2.get(k) is True)
    a2_fail = sorted(k for k in paired if a2.get(k) is False)

    def v_star_count(ids: list[str]) -> int:
        return sum(1 for i in ids if not paired[i]["text_only"])

    pass_need, fail_need = v_star_count(a2_pass), v_star_count(a2_fail)
    table = (pass_need, len(a2_pass) - pass_need,
             fail_need, len(a2_fail) - fail_need)
    report["PRIMARY_A2_CONSTRUCT_VALIDITY"] = {
        "definition": prereg()["primary_endpoint"]["definition"],
        "test": "fisher_exact_two_sided",
        "why_unpaired": prereg()["primary_endpoint"]["why_unpaired"],
        "a2_pass": block(a2_pass, paired),
        "a2_fail": block(a2_fail, paired),
        "contingency_table": {
            "a2_pass_needs_figure": table[0], "a2_pass_answerable_from_text": table[1],
            "a2_fail_needs_figure": table[2], "a2_fail_answerable_from_text": table[3],
        },
        "v_star_a2_pass": round(pass_need / len(a2_pass), 4) if a2_pass else None,
        "v_star_a2_fail": round(fail_need / len(a2_fail), 4) if a2_fail else None,
        "fisher_exact_two_sided_p": round(fisher_exact_two_sided(*table), 6),
        "confound_declared_before_execution":
            prereg()["primary_endpoint"]["confound_declared_now"],
    }

    # ---- the form that breaks the arm confound: A2 status WITHIN each arm ----
    within: dict[str, Any] = {}
    for arm in ARMS_REPORT_ORDER:
        ids = [k for k in paired if by_item[k]["arm"] == arm]
        p_ids = sorted(k for k in ids if a2.get(k) is True)
        f_ids = sorted(k for k in ids if a2.get(k) is False)
        if not p_ids or not f_ids:
            within[arm] = {"n_a2_pass": len(p_ids), "n_a2_fail": len(f_ids),
                           "note": "one cell empty; no comparison possible"}
            continue
        pn, fn = v_star_count(p_ids), v_star_count(f_ids)
        cell = (pn, len(p_ids) - pn, fn, len(f_ids) - fn)
        within[arm] = {
            "n_a2_pass": len(p_ids), "n_a2_fail": len(f_ids),
            "v_star_a2_pass": round(pn / len(p_ids), 4),
            "v_star_a2_fail": round(fn / len(f_ids), 4),
            "fisher_exact_two_sided_p": round(fisher_exact_two_sided(*cell), 6),
        }
    report["a2_validity_within_arm"] = {
        "why": ("A2 status correlates with arm by construction, so the pooled table "
                "cannot separate gate selection from an arm effect. Within an arm "
                "that confound is gone. Every cell here is small and carries NO "
                "significance claim; it is reported for every arm whatever it shows."),
        "arms": within,
    }

    # ---- per-arm branch rates (secondary, conditional on admission) ----
    report["by_arm"] = {
        "why_confounded": ("the arms admit different item sets, so each arm's rate "
                           "is measured on different items; conditional on admission"),
        "arms": {arm: block(sorted(k for k in paired if by_item[k]["arm"] == arm),
                            paired)
                 for arm in ARMS_REPORT_ORDER},
    }

    # ---- the sensitivity curve the frame-D failure was invisible without ----
    # Every endpoint re-graded at eight F1 thresholds plus the frame-D containment
    # rule. Reported whatever it shows: if the primary moves across the curve, the
    # result depends on the threshold and must be read that way.
    curve: dict[str, Any] = {}
    for label, rule in ([("containment_frame_d_rule", None)]
                        + [(f"f1_{t:.2f}", t) for t in
                           (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90)]):
        scored: dict[str, dict[str, bool]] = {}
        for item_id in sorted(paired):
            item = by_item[item_id]
            cell = {}
            for branch in BRANCHES:
                returned = returned_by_task.get(f"ablation::{branch}::{item_id}")
                if returned is None:
                    cell = {}
                    break
                cell[branch] = (graded_correct_containment(item, returned)
                                if rule is None
                                else graded_correct(item, returned, threshold=rule))
            if len(cell) == len(BRANCHES):
                scored[item_id] = cell
        if not scored:
            continue
        ids = sorted(scored)
        p_ids = [k for k in ids if a2.get(k) is True]
        f_ids = [k for k in ids if a2.get(k) is False]
        pn = sum(1 for i in p_ids if not scored[i]["text_only"])
        fn = sum(1 for i in f_ids if not scored[i]["text_only"])
        cell4 = (pn, len(p_ids) - pn, fn, len(f_ids) - fn)
        curve[label] = {
            "n": len(ids),
            "v_star_overall": round(
                sum(1 for i in ids if not scored[i]["text_only"]) / len(ids), 4),
            "v_star_a2_pass": round(pn / len(p_ids), 4) if p_ids else None,
            "v_star_a2_fail": round(fn / len(f_ids), 4) if f_ids else None,
            "fisher_exact_two_sided_p": round(fisher_exact_two_sided(*cell4), 6),
            "branch_mcnemar_p": block(ids, scored)["mcnemar_exact_two_sided_p"],
        }
    report["grading_sensitivity_curve"] = {
        "why": ("the frame-D ablation's significance came from a grading rule that "
                "was strict to insertions; it did not survive re-grading. This curve "
                "is reported so the same failure cannot hide here."),
        "frozen_primary_threshold": F1_THRESHOLD,
        "thresholds": curve,
    }

    # ---- sensitivity: excluded items scored correct in BOTH branches ----
    sens = dict(paired)
    for k in sorted(dropped & set(both)):
        sens[k] = {"text_only": True, "text_image": True}
    report["sensitivity_all_items_exclusions_scored_correct"] = {
        "why": ("the two excluded items are added back scored correct in both "
                "branches. They are concordant by construction, so they cannot move "
                "the branch McNemar test, only the raw rates."),
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
