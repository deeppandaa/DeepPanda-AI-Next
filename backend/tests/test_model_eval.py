from __future__ import annotations

import unittest

from app.model_eval import _concept_coverage, load_capability_cases


class ModelEvaluationTests(unittest.TestCase):
    def test_capability_cases_cover_every_ranked_area(self) -> None:
        cases = load_capability_cases()

        self.assertEqual(
            set(cases),
            {"answer", "planning", "source_grounded", "learning", "code_change"},
        )
        self.assertTrue(all(cases.values()))
        self.assertEqual(len({case["id"] for area in cases.values() for case in area}), 15)
        self.assertTrue(all(case["max_steps"] == 20 for case in cases["planning"]))

    def test_concept_coverage_scores_alternative_terms_per_requirement(self) -> None:
        score, matched = _concept_coverage(
            "Add a pytest regression test and update the README documentation.",
            [["unit test", "pytest"], ["readme", "docs"]],
        )

        self.assertEqual(score, 1.0)
        self.assertEqual(matched, [True, True])

        partial_score, partial_matched = _concept_coverage(
            "Add a regression test.", [["test"], ["readme", "docs"]]
        )
        self.assertEqual(partial_score, 0.5)
        self.assertEqual(partial_matched, [True, False])

    def test_source_answer_aliases_accept_numeric_and_word_forms(self) -> None:
        case = load_capability_cases()["source_grounded"][1]
        expected_answers = case.get("expected_answers", [case.get("expected_answer", "")])

        self.assertIn("4", expected_answers)
        self.assertIn("four", expected_answers)


if __name__ == "__main__":
    unittest.main()