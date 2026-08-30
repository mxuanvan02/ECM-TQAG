#!/usr/bin/env python3
"""Tests for the ECM-v2 division-of-labour gates.

Two kinds of test here, and the second kind matters more:

  * unit tests on the gate functions, including the cases that motivated each
    threshold (short correct answers, diacritic loss, stopword-only overlap);
  * a REGRESSION test that re-derives the retro-fit rates from the sealed
    frame-D and frame-E census records and asserts the counts the gate module
    produces. Those counts were first computed ad hoc while designing the gates;
    if the module and the ad-hoc pass disagree, one of them is wrong, and the
    test says which numbers the module stands behind.

Run: python -m pytest round2/test_ecm_v2_gates.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The gate module lives at round2/ecm_v2_gates.py in the private experiment tree
# and beside this file in the published copy. Both import paths are tried so the
# same test file runs unchanged in either location; a test that only runs in one
# of the two places is not a test of the published artefact.
try:
    from round2.ecm_v2_gates import (  # noqa: E402
        CHANCE_BASELINES,
        G7_MIN_ANSWER_FIGURE_WORDS,
        G8_MIN_DESCRIPTION_FIGURE_WORDS,
        content_words,
        evaluate,
        figure_word_pool,
        g6_answer_not_in_quote,
        g7_answer_meets_figure,
        g8_description_meets_figure,
        validate_generation_ecm_v2,
    )
except ModuleNotFoundError:  # published copy: module sits beside this file
    from ecm_v2_gates import (  # noqa: E402
        CHANCE_BASELINES,
        G7_MIN_ANSWER_FIGURE_WORDS,
        G8_MIN_DESCRIPTION_FIGURE_WORDS,
        content_words,
        evaluate,
        figure_word_pool,
        g6_answer_not_in_quote,
        g7_answer_meets_figure,
        g8_description_meets_figure,
        validate_generation_ecm_v2,
    )

FRAME_D_CENSUS = ROOT / "runs" / "round4_framed_census_20260829T200000Z"
FRAME_E_CENSUS = ROOT / "runs" / "round4_framee_census_20260830T100000Z"
FRAME_D_MANIFEST = (ROOT / "dataset_framed"
                    / "dataset_manifest_framed_20260829T195643Z.json")
FRAME_E_MANIFEST = (ROOT / "dataset_framee"
                    / "dataset_manifest_framee_20260830T093119Z.json")


# ---------------------------------------------------------------- helpers
def _item(answer: str, quote: str, description: str = "x") -> dict:
    return {
        "answer": answer,
        "text_evidence_quote": quote,
        "visual_evidence": {"description": description,
                            "image_sha256": "deadbeef",
                            "necessity_rationale": "y"},
    }


def _figure_text(words: list[str]) -> dict:
    return {"words": words}


# ---------------------------------------------------------------- content_words
def test_content_words_drops_stopwords_and_short_tokens():
    got = content_words("Của trong và các thặng dư người tiêu dùng")
    # "cua/trong/va/cac/nguoi" are stopwords; "du" is 2 chars
    assert got == {"thang", "tieu", "dung"}


def test_content_words_folds_accents_so_ocr_diacritic_loss_still_matches():
    assert content_words("Thặng") == content_words("Thang") == {"thang"}


def test_content_words_keeps_digits_and_codes():
    assert "1898" in content_words("Quyết định 1898/QD-UBND")


# ---------------------------------------------------------------- G6
def test_g6_rejects_answer_readable_off_the_quote():
    ok, ev = g6_answer_not_in_quote(
        "Thặng dư người tiêu dùng",
        "Điều này dẫn đến thặng dư người tiêu dùng và được chỉ ra bởi vùng gạch chéo")
    assert ok is False
    assert ev["answer_inside_quote"] is True


def test_g6_admits_answer_the_quote_does_not_contain():
    ok, ev = g6_answer_not_in_quote(
        "Hội đồng Thẩm định trực thuộc Ủy ban Điều phối",
        "Hội đồng Thẩm định là công cụ của Ủy ban Điều phối trong khâu xét duyệt")
    assert ok is True
    assert ev["answer_inside_quote"] is False


def test_g6_is_case_insensitive_so_capitalisation_cannot_evade_it():
    ok, _ = g6_answer_not_in_quote("tòa án độc lập", "Đó là TÒA ÁN ĐỘC LẬP xuất hiện")
    assert ok is False


def test_g6_does_not_fold_accents():
    # folding would make these match and over-reject a genuinely different answer
    ok, _ = g6_answer_not_in_quote("thang du", "thặng dư người tiêu dùng")
    assert ok is True


def test_g6_fails_closed_on_empty_fields():
    assert g6_answer_not_in_quote("", "abc")[0] is False
    assert g6_answer_not_in_quote("abc", "")[0] is False


# ---------------------------------------------------------------- G7 / G8
def test_g7_needs_two_content_words_not_one():
    pool = {"thang", "tieu", "dung"}
    assert g7_answer_meets_figure("Thặng dư", pool)[0] is False   # 1 hit
    assert g7_answer_meets_figure("Thặng dư tiêu dùng", pool)[0] is True  # 3 hits


def test_g7_stopword_overlap_cannot_satisfy_the_gate():
    # a figure pool full of function words must not admit a generic answer
    pool = content_words("của trong và các người việc pháp luật nhà nước")
    ok, ev = g7_answer_meets_figure("Của người trong pháp luật nhà nước", pool)
    assert ok is False
    assert ev["overlap"] == 0


def test_g8_threshold_is_stricter_than_g7():
    assert G8_MIN_DESCRIPTION_FIGURE_WORDS > G7_MIN_ANSWER_FIGURE_WORDS
    pool = {"quoc", "hoi", "chinh", "phu", "ngan", "hang"}
    assert g8_description_meets_figure("Sơ đồ Quốc hội Chính phủ", pool)[0] is True
    assert g8_description_meets_figure("Sơ đồ Quốc hội", pool)[0] is False


def test_g8_rejects_the_invented_description_that_v1_admitted():
    # v1 checked only non-emptiness, so this passed; it must not now
    pool = {"quoc", "hoi", "chinh", "phu"}
    ok, _ = g8_description_meets_figure(
        "Hình ảnh hiển thị phần NHẬN XÉT trong tài liệu giáo trình", pool)
    assert ok is False


# ---------------------------------------------------------------- figure pool
def test_figure_word_pool_reads_the_gated_ocr_channel():
    pool = figure_word_pool(_figure_text(["Quốc", "hội", "Chính", "phủ", "và"]))
    assert "quoc" in pool and "chinh" in pool
    assert "va" not in pool          # stopword


def test_figure_word_pool_is_empty_when_the_channel_is_absent_or_malformed():
    assert figure_word_pool(None) == set()
    assert figure_word_pool({}) == set()
    assert figure_word_pool({"words": "not a list"}) == set()


def test_empty_figure_pool_fails_g7_and_g8_closed():
    result = evaluate(_item("Tòa án độc lập", "một đoạn văn khác", "mô tả nào đó"),
                      None)
    assert result["passed"] is False
    assert "g7_answer_meets_figure" in result["failed_gates"]
    assert "g8_description_meets_figure" in result["failed_gates"]


# ---------------------------------------------------------------- composite
def test_evaluate_conjunction_and_reporting_shape():
    pool = ["Hội", "đồng", "Thẩm", "định", "Ủy", "ban", "Điều", "phối"]
    item = _item("Hội đồng Thẩm định trực thuộc Ủy ban Điều phối",
                 "Hội đồng Thẩm định là công cụ xét duyệt hồ sơ chuyên môn",
                 "Sơ đồ Ủy ban Điều phối và Hội đồng Thẩm định")
    result = evaluate(item, _figure_text(pool))
    assert result["passed"] is True
    assert result["failed_gates"] == []
    assert set(result["gates"]) == {"g6_answer_not_in_quote",
                                    "g7_answer_meets_figure",
                                    "g8_description_meets_figure"}
    assert result["thresholds"]["g7_min_answer_figure_words"] == 2


def test_validate_raises_naming_every_failing_gate():
    with pytest.raises(ValueError) as exc:
        validate_generation_ecm_v2(_item("x y z", "x y z abc", "mô tả"), None)
    message = str(exc.value)
    assert message.startswith("BLOCKED_ECM_V2:GATE:")
    assert "g6_answer_not_in_quote" in message


def test_validate_attaches_the_gate_record_on_success():
    pool = ["Hội", "đồng", "Thẩm", "định", "Ủy", "ban", "Điều", "phối"]
    out = validate_generation_ecm_v2(
        _item("Hội đồng Thẩm định trực thuộc Ủy ban Điều phối",
              "một đoạn văn nói về khâu xét duyệt hồ sơ",
              "Sơ đồ Hội đồng Thẩm định và Ủy ban Điều phối"),
        _figure_text(pool))
    assert out["ecm_v2_gates"]["passed"] is True
    assert out["answer"]                      # original fields preserved


def test_evaluate_fails_closed_on_missing_visual_evidence():
    with pytest.raises(ValueError):
        evaluate({"answer": "a", "text_evidence_quote": "b"}, None)


# ---------------------------------------------------------------- baselines
def test_chance_baselines_record_that_single_word_overlap_is_near_chance():
    """The rejected designs must stay documented in the module."""
    g7 = CHANCE_BASELINES["g7_answer_meets_figure"]
    one = g7["1_word"]
    two = g7["2_words"]
    lift_one = one["observed"] - one["chance_p95"]
    lift_two = two["observed"] - two["chance_p95"]
    assert lift_two > lift_one          # why the threshold is 2, not 1
    rejected = CHANCE_BASELINES["rejected_variant_answer_meets_surplus_only"]
    assert rejected["observed"] < rejected["chance_p95"]   # below chance


# ---------------------------------------------------------------- regression
def _admitted_items(census_dir: Path) -> list[tuple[str, dict]]:
    out = []
    for path in sorted((census_dir / "state" / "tasks").glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        tid = rec.get("task_id", "")
        if not tid.startswith("generation::"):
            continue
        if rec.get("status") != "COMPLETE" or not rec.get("gates_passed"):
            continue
        chunk = "::".join(tid.split("::")[2:5])
        out.append((chunk, rec["object"]))
    return out


def _figure_texts(manifest_path: Path) -> dict[str, dict]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {p["chunk_id"]: (p["evidence"].get("figure_text") or {})
            for p in data["packages"]}


@pytest.mark.parametrize(
    "census_dir,manifest,expect",
    [
        # AUTHORITATIVE counts, produced by this module against the sealed
        # censuses. They differ from figures obtained ad hoc while designing the
        # gates, and the module is the correct one in both places the two
        # disagreed:
        #
        #   g6: ad hoc frame-E said 25, module says 27. The ad-hoc probe compared
        #       answer and quote case-SENSITIVELY, so an answer that appears in
        #       the quote differing only in the capitalisation of its first letter
        #       ("Cộng, được xác định..." against "cộng, được xác định...") was
        #       scored as NOT contained and wrongly passed. All 10 disagreements
        #       were of that shape. Leading case is exactly the difference the
        #       v1 gate already normalises away, so G6 must too.
        #
        #   g7/g8: ad hoc said 93/112 and 106/123, module says 78/100 and 98/109.
        #       The ad-hoc probe counted overlap over RAW figure words; the module
        #       counts CONTENT words, dropping stopwords and tokens under three
        #       characters (305 raw words fall to 133 content words on the probe
        #       chunk). Without that filter "của / trong / pháp luật" satisfy the
        #       gate, which is the near-chance behaviour the permutation test
        #       rejected.
        (FRAME_D_CENSUS, FRAME_D_MANIFEST,
         {"items": 120, "g6": 50, "g7": 78, "g8": 100, "all": 32}),
        (FRAME_E_CENSUS, FRAME_E_MANIFEST,
         {"items": 128, "g6": 27, "g7": 98, "g8": 109, "all": 22}),
    ],
    ids=["frame_d", "frame_e"],
)
def test_retrofit_counts_reproduce_on_the_sealed_censuses(census_dir, manifest, expect):
    if not census_dir.is_dir() or not manifest.is_file():
        pytest.skip(f"sealed records not present: {census_dir.name}")
    items = _admitted_items(census_dir)
    pools = _figure_texts(manifest)
    assert len(items) == expect["items"]

    counts = {"g6": 0, "g7": 0, "g8": 0, "all": 0}
    for chunk_id, obj in items:
        result = evaluate(obj, pools.get(chunk_id))
        gates = result["gates"]
        counts["g6"] += gates["g6_answer_not_in_quote"]["passed"]
        counts["g7"] += gates["g7_answer_meets_figure"]["passed"]
        counts["g8"] += gates["g8_description_meets_figure"]["passed"]
        counts["all"] += result["passed"]

    assert counts["g6"] == expect["g6"]
    assert counts["g7"] == expect["g7"]
    assert counts["g8"] == expect["g8"]
    assert counts["all"] == expect["all"]


def test_g6_is_the_binding_gate_on_both_sealed_censuses():
    """The conjunction must be driven by G6, which is the design claim."""
    for census_dir, manifest in ((FRAME_D_CENSUS, FRAME_D_MANIFEST),
                                 (FRAME_E_CENSUS, FRAME_E_MANIFEST)):
        if not census_dir.is_dir() or not manifest.is_file():
            pytest.skip("sealed records not present")
        items = _admitted_items(census_dir)
        pools = _figure_texts(manifest)
        failures = {"g6_answer_not_in_quote": 0, "g7_answer_meets_figure": 0,
                    "g8_description_meets_figure": 0}
        for chunk_id, obj in items:
            for name in evaluate(obj, pools.get(chunk_id))["failed_gates"]:
                failures[name] += 1
        assert failures["g6_answer_not_in_quote"] > failures["g7_answer_meets_figure"]
        assert failures["g6_answer_not_in_quote"] > failures["g8_description_meets_figure"]
