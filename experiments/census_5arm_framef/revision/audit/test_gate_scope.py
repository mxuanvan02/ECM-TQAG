#!/usr/bin/env python3
"""Rights-cleared tests for the historical ECM-v2 gate module."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

REVISION_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REVISION_ROOT / "reference" / "ecm_v2_gates.py"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "gate_cases.json"

spec = importlib.util.spec_from_file_location("ecm_v2_gates_historical", GATE_PATH)
assert spec and spec.loader
GATES = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GATES)


class HistoricalGateScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.cases = {case["name"]: case for case in cls.document["cases"]}

    def evaluate_case(self, name: str) -> dict:
        case = self.cases[name]
        result = GATES.evaluate(case["item"], case["figure_text"])
        expected = case["expected"]
        self.assertEqual(result["gates"]["g6_answer_not_in_quote"]["passed"], expected["g6"])
        self.assertEqual(result["gates"]["g7_answer_meets_figure"]["passed"], expected["g7"])
        self.assertEqual(result["gates"]["g8_description_meets_figure"]["passed"], expected["g8"])
        self.assertEqual(result["passed"], expected["passed"])
        return result

    def test_all_three_pass(self) -> None:
        self.evaluate_case("all_three_pass")

    def test_g6_rejects_literal_answer_in_declared_quote(self) -> None:
        result = self.evaluate_case("g6_rejects_literal_answer_in_quote")
        self.assertTrue(result["gates"]["g6_answer_not_in_quote"]["answer_inside_quote"])

    def test_question_side_answer_is_outside_g6_scope(self) -> None:
        case = self.cases["g6_does_not_inspect_question"]
        self.assertIn(case["item"]["answer"].casefold(), case["question"].casefold())
        result = self.evaluate_case("g6_does_not_inspect_question")
        self.assertTrue(result["passed"])

    def test_chunk_pool_can_pass_using_unselected_crop_words(self) -> None:
        case = self.cases["chunk_pool_can_pass_from_unselected_crop"]
        answer_words = GATES.content_words(case["item"]["answer"])
        selected_words = GATES.content_words(" ".join(case["selected_crop_words"]))
        other_words = GATES.content_words(" ".join(case["other_crop_words"]))
        self.assertLess(len(answer_words & selected_words), GATES.G7_MIN_ANSWER_FIGURE_WORDS)
        self.assertGreaterEqual(len(answer_words & other_words), GATES.G7_MIN_ANSWER_FIGURE_WORDS)
        result = self.evaluate_case("chunk_pool_can_pass_from_unselected_crop")
        self.assertTrue(result["passed"])

    def test_gate_module_hash_remains_protocol_bound(self) -> None:
        import hashlib
        digest = hashlib.sha256(GATE_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, "7f18b0c9ee4543e851985bb00748caf0b3b522098c4199b7a9bb901362db0828")


if __name__ == "__main__":
    unittest.main()
