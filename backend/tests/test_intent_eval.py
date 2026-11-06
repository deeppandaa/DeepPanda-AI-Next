from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.intent_eval import load_cases, score_results
from app.plugins.intent_router import IntentRouterPlugin


class IntentEvaluationTests(unittest.TestCase):
    def test_benchmark_covers_every_supported_intent(self) -> None:
        cases = load_cases()

        self.assertEqual(len(cases), 27)
        self.assertEqual({case["expected"] for case in cases}, set(IntentRouterPlugin.intents))
        self.assertEqual(len({case["id"] for case in cases}), len(cases))

    def test_load_cases_rejects_unknown_intents_and_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cases_path = Path(temporary_directory) / "cases.json"
            cases_path.write_text(json.dumps({"cases": [
                {"id": "same", "expected": "execute", "text": "Change a file."},
            ]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected must be"):
                load_cases(cases_path)

            cases_path.write_text(json.dumps({"cases": [
                {"id": "same", "expected": "answer", "text": "First question."},
                {"id": "same", "expected": "answer", "text": "Second question."},
            ]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                load_cases(cases_path)

    def test_metrics_include_macro_f1_brier_ece_and_failures(self) -> None:
        results = [
            {"expected": "answer", "actual": "answer", "confidence": 0.9},
            {"expected": "plan", "actual": "answer", "confidence": 0.8},
            {"expected": "research", "actual": None, "confidence": None},
        ]

        metrics = score_results(results)

        self.assertEqual(metrics["case_count"], 3)
        self.assertEqual(metrics["successful_count"], 2)
        self.assertEqual(metrics["error_count"], 1)
        self.assertEqual(metrics["accuracy"], 0.3333)
        self.assertEqual(metrics["confusion_matrix"]["rows"]["research"]["error"], 1)
        self.assertEqual(metrics["brier_score"], 0.325)
        self.assertEqual(metrics["expected_calibration_error"], 0.35)


if __name__ == "__main__":
    unittest.main()