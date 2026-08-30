#!/usr/bin/env python3
"""Tests for the ECM-v2 arm prompts.

The tests that matter here are the ones that would catch a silently broken
identification argument:

  * the two arms must render DIFFERENT system prompts. An earlier revision of
    `build_generation_request_ecm_v2` accepted an `arm` argument and then failed
    to forward it to `render_messages`, so the disclosure control would have been
    served the treatment prompt and the control would have been a copy of the
    treatment. That defect is exactly what `test_builder_forwards_the_arm` pins.
  * the two arms must be LENGTH MATCHED, because prompt length is a confound and
    the reported census licenses its ordering claim on a matched pair.
  * both arms must state all three gates, and only the treatment may carry the
    ordering clauses.

Run: python -m pytest round2/test_ecm_v2_prompt.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from round2.ecm_v2_prompt import (  # noqa: E402
        ARM_NAME,
        CONTROL_ARM_NAME,
        ECM_V2_ARMS,
        ROLE_GUIDANCE,
        SEALED_HELPERS_AVAILABLE,
        build_generation_request_ecm_v2,
        prompt_lengths,
        render_messages,
    )
except ModuleNotFoundError:  # published copy: module sits beside this test
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ecm_v2_prompt import (  # type: ignore  # noqa: E402
        ARM_NAME,
        CONTROL_ARM_NAME,
        ECM_V2_ARMS,
        ROLE_GUIDANCE,
        SEALED_HELPERS_AVAILABLE,
        build_generation_request_ecm_v2,
        prompt_lengths,
        render_messages,
    )

# The request builder calls the sealed evidence verifier, which ships only in the
# private experiment tree. The prompt TEXT and its rendering are self-contained
# and are tested everywhere; the builder tests skip where the sealed helpers are
# absent rather than failing for an environment reason.
needs_sealed = pytest.mark.skipif(
    not SEALED_HELPERS_AVAILABLE,
    reason="sealed ecm_tqag.v310_runner helpers not present in this tree",
)

# Clauses that fix the ORDER of work. Only the treatment may carry these.
ORDERING_CLAUSES = ("ĐỌC HÌNH trước", "NIÊM PHONG", "Bốn bước")
# The clause that explicitly frees the order. Only the control may carry it.
FREE_ORDER_CLAUSE = "Bạn tự quyết định trình tự"


def _render(arm: str, role: str = "table", qtype: str = "short_answer"):
    return render_messages(
        arm=arm,
        question_type=qtype,
        source_text="một đoạn văn nguồn nào đó",
        document_structure={"section_label": "x"},
        image_hashes=["aa" * 32],
        figure_role=role,
    )


# ---------------------------------------------------------------- arms differ
def test_the_two_arms_render_different_system_prompts():
    treat = _render(ARM_NAME)[0]["content"]
    ctrl = _render(CONTROL_ARM_NAME)[0]["content"]
    assert treat != ctrl


def test_only_the_treatment_fixes_the_order_of_work():
    treat = _render(ARM_NAME)[0]["content"]
    ctrl = _render(CONTROL_ARM_NAME)[0]["content"]
    for clause in ORDERING_CLAUSES:
        assert clause in treat, clause
        assert clause not in ctrl, clause
    assert FREE_ORDER_CLAUSE in ctrl
    assert FREE_ORDER_CLAUSE not in treat


def test_both_arms_disclose_all_three_gates():
    for arm in ECM_V2_ARMS:
        system = _render(arm)[0]["content"]
        for gate in ("G6", "G7", "G8"):
            assert gate in system, (arm, gate)


def test_both_arms_receive_identical_role_guidance():
    for role, guidance in ROLE_GUIDANCE.items():
        for arm in ECM_V2_ARMS:
            user = _render(arm, role=role)[1]["content"]
            assert guidance in user, (arm, role)


# ---------------------------------------------------------------- length match
def test_arms_are_length_matched_within_five_percent():
    lengths = prompt_lengths()
    treat = lengths[ARM_NAME]["total"]
    ctrl = lengths[CONTROL_ARM_NAME]["total"]
    # The reported census matched 1604 against 1623 characters. A 5% band is
    # looser than that and still rules out length as an explanation.
    assert abs(treat - ctrl) / treat < 0.05, (treat, ctrl)


def test_length_match_holds_on_the_rendered_prompt_not_only_the_template():
    rendered = {}
    for arm in ECM_V2_ARMS:
        messages = _render(arm)
        rendered[arm] = sum(len(m["content"]) for m in messages)
    treat, ctrl = rendered[ARM_NAME], rendered[CONTROL_ARM_NAME]
    assert abs(treat - ctrl) / treat < 0.05, rendered


# ---------------------------------------------------------------- fail closed
@pytest.mark.parametrize("role", ["chart", "", None, "TABLE"])
def test_unknown_figure_role_fails_closed(role):
    with pytest.raises(ValueError) as exc:
        _render(ARM_NAME, role=role)
    assert "FIGURE_ROLE" in str(exc.value)


def test_unknown_arm_fails_closed():
    with pytest.raises(ValueError) as exc:
        _render("nope")
    assert str(exc.value).startswith("BLOCKED_ECM_V2_PROMPT:ARM:")


def test_unknown_question_type_fails_closed():
    with pytest.raises(ValueError):
        _render(ARM_NAME, qtype="essay")


# ---------------------------------------------------------------- builder
def _package(tmp_path: Path) -> dict:
    """A minimal TLV package with one real image on disk."""
    import hashlib

    # 1x1 PNG, written so `_verified_evidence` can hash real bytes
    raw = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6300010000050001od0a2db40000000049454e44ae"
        "426082".replace("od", "0d")
    )
    path = tmp_path / "region.png"
    path.write_bytes(raw)
    return {
        "chunk_id": "frameF::T::s0001",
        "condition": "TLV",
        "question_type": "short_answer",
        "evidence": {
            "text": "một đoạn văn nguồn dài hơn hai mươi ký tự để qua kiểm tra",
            "document_structure": {"section_label": "dec:1", "figure_role": "table"},
            "images": [{
                "path": str(path),
                "declared_order": 1,
                "width": 1, "height": 1,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }],
        },
    }


@needs_sealed
def test_builder_forwards_the_arm(tmp_path):
    """The defect this pins: a builder that accepts `arm` and ignores it would
    serve the treatment prompt to the control, making the control a copy of the
    treatment and voiding the identification argument."""
    package = _package(tmp_path)
    treat = build_generation_request_ecm_v2(
        package, question_type="short_answer", arm=ARM_NAME)
    ctrl = build_generation_request_ecm_v2(
        package, question_type="short_answer", arm=CONTROL_ARM_NAME)
    assert treat["method_prompt_sha256"] != ctrl["method_prompt_sha256"]
    assert treat["arm"] == ARM_NAME and ctrl["arm"] == CONTROL_ARM_NAME


@needs_sealed
def test_builder_carries_evidence_digest_and_role(tmp_path):
    built = build_generation_request_ecm_v2(
        _package(tmp_path), question_type="short_answer")
    assert built["figure_role"] == "table"
    assert len(built["evidence_sha256"]) == 64
    assert built["payload"]["temperature"] == 0
    # the image must reach the model as an image part, not as text
    parts = built["payload"]["messages"][1]["content"]
    assert any(p.get("type") == "image_url" for p in parts)


@needs_sealed
def test_builder_rejects_a_package_without_a_figure_role(tmp_path):
    package = _package(tmp_path)
    del package["evidence"]["document_structure"]["figure_role"]
    with pytest.raises(ValueError) as exc:
        build_generation_request_ecm_v2(package, question_type="short_answer")
    assert "FIGURE_ROLE_MISSING_IN_PACKAGE" in str(exc.value)


@needs_sealed
def test_builder_rejects_a_question_type_mismatch(tmp_path):
    with pytest.raises(ValueError):
        build_generation_request_ecm_v2(
            _package(tmp_path), question_type="multiple_choice")
