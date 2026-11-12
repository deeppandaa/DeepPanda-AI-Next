from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
from app.model_eval import (
    AREA_NAMES,
    AREA_SYSTEM_PROMPTS,
    _concept_coverage,
    _schema,
    _summarize_area,
    build_preferences,
    evaluate_models,
    load_benchmark_cases,
    load_capability_cases,
    merge_reports,
    rescore_report,
    score_case,
    validate_embeddings,
)


class ModelEvaluationTests(unittest.TestCase):
    def test_capability_cases_cover_every_ranked_area(self) -> None:
        cases = load_capability_cases()

        self.assertEqual(
            set(cases),
            {"answer", "planning", "source_grounded", "learning", "code_change"},
        )
        self.assertTrue(all(cases.values()))
        self.assertEqual(
            len({case["id"] for area in cases.values() for case in area}), 15
        )
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
        expected_answers = case.get(
            "expected_answers", [case.get("expected_answer", "")]
        )

        self.assertIn("4", expected_answers)
        self.assertIn("four", expected_answers)

    def test_benchmark_covers_every_area_with_multiple_cases(self) -> None:
        cases = load_benchmark_cases()
        self.assertEqual(len(cases), 20)
        for area in AREA_NAMES:
            self.assertGreaterEqual(sum(case["area"] == area for case in cases), 3)
        self.assertTrue(any("Türkçe" in case["prompt"] for case in cases))
        self.assertIn("NOT an educational question", AREA_SYSTEM_PROMPTS["intent"])
        self.assertIn(
            "does not mean anything was saved", AREA_SYSTEM_PROMPTS["learning"]
        )

    def test_exact_scoring_rejects_missing_keys_wrong_types_and_extra_fields(
        self,
    ) -> None:
        case = {"expected": {"answer": 1}}
        for actual in (
            {"answer": True},
            {"answer": "1"},
            {"answer": 1, "other": 2},
            {},
        ):
            with self.subTest(actual=actual):
                self.assertEqual(score_case(case, actual)[0], 0)
        self.assertEqual(score_case(case, {"answer": 1})[0], 1)
        self.assertEqual(
            score_case({"expected": {"answer": [1]}}, {"answer": [True]})[0], 0
        )

    def test_code_scoring_checks_ast_not_keyword_presence(self) -> None:
        case = next(
            case
            for case in load_benchmark_cases()
            if case["id"] == "code-clamp-boundary"
        )
        correct = case["code_templates"][0]
        self.assertEqual(score_case(case, {"code": correct})[0], 1)
        self.assertEqual(
            score_case(
                case,
                {"code": correct.replace("ValueError()", "ValueError('bad bounds')")},
            )[0],
            1,
        )
        self.assertEqual(
            score_case(case, {"code": correct.replace("low > high", "low >= high")})[0],
            0,
        )
        self.assertEqual(
            score_case(case, {"code": correct.replace("low > high", "high < low")})[0],
            1,
        )
        self.assertEqual(
            score_case(
                case,
                {
                    "code": correct.replace(
                        "    return min", "    else:\n        return min"
                    )
                },
            )[0],
            1,
        )
        self.assertEqual(
            score_case(
                case, {"code": correct + "\nraise RuntimeError('must never execute')\n"}
            )[0],
            0,
        )
        self.assertEqual(
            score_case(
                case,
                {"code": "# low > high; ValueError; min(max(value, low), high)\npass"},
            )[0],
            0,
        )

    def test_null_expected_does_not_constrain_model_to_correct_answer(self) -> None:
        self.assertEqual(_schema(None), {"type": ["string", "null"]})

    def test_embedding_checks_validate_actual_vectors(self) -> None:
        result = validate_embeddings([[1, 0], [1, 0], [0, 1]], 3)
        self.assertEqual(result["dimensions"], 2)
        self.assertEqual(result["duplicate_cosine"], 1)
        self.assertEqual(result["unrelated_cosine"], 0)
        for vectors in (
            [[0, 0]] * 3,
            [[1, float("nan")]] * 3,
            [[True, 1]] * 3,
            [[1, 0], [1], [1, 0]],
            [[1, 0]],
        ):
            with self.subTest(vectors=vectors), self.assertRaises(ValueError):
                validate_embeddings(vectors, 3)

    def test_skipped_cases_are_not_fabricated_zero_scores(self) -> None:
        result = _summarize_area(
            [
                {
                    "status": "skipped",
                    "score": None,
                    "passed": False,
                    "latency_seconds": 0,
                }
            ],
            "answer",
        )
        self.assertIsNone(result["score"])
        self.assertEqual(result["attempted_count"], 0)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], "untested")

    def test_single_case_cannot_produce_a_usable_ranking(self) -> None:
        result = _summarize_area(
            [{"status": "ok", "score": 1, "passed": True, "latency_seconds": 1}],
            "answer",
        )
        self.assertFalse(result["eligible"])

    def test_real_request_contract_circuit_breaker_embeddings_and_serial_unloads(
        self,
    ) -> None:
        cases = load_benchmark_cases()
        requests = []
        loaded = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content) if request.content else {}
            path = request.url.path
            requests.append((path, body))
            if path == "/api/tags":
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": name, "digest": name}
                            for name in ("broken", "chat", "vectors")
                        ]
                    },
                )
            if path == "/api/ps":
                return httpx.Response(
                    200, json={"models": [{"name": name} for name in loaded]}
                )
            if path == "/api/show":
                return httpx.Response(
                    200,
                    json={
                        "capabilities": ["embedding"]
                        if body["model"] == "vectors"
                        else ["completion"]
                    },
                )
            if path == "/api/generate":
                self.assertEqual(body["keep_alive"], 0)
                loaded.clear()
                return httpx.Response(200, json={"done": True})
            if path == "/api/chat":
                model = body["model"]
                self.assertTrue(not loaded or loaded == [model])
                loaded[:] = [model]
                self.assertEqual(body["options"]["seed"], 42)
                self.assertEqual(body["options"]["temperature"], 0)
                self.assertFalse(body["think"])
                if model == "broken":
                    raise httpx.ReadTimeout("bounded", request=request)
                case = next(
                    case
                    for case in cases
                    if case["prompt"] == body["messages"][-1]["content"]
                )
                actual = (
                    {"code": case["code_templates"][0]}
                    if "code_templates" in case
                    else case["expected"]
                )
                return httpx.Response(
                    200,
                    json={
                        "message": {"content": json.dumps(actual)},
                        "done_reason": "stop",
                    },
                )
            if path == "/api/embed":
                self.assertFalse(loaded)
                loaded[:] = [body["model"]]
                return httpx.Response(
                    200, json={"embeddings": [[1, 0], [1, 0], [0, 1], [1, 1]]}
                )
            self.fail(f"Unexpected request {path}")

        async def exercise() -> dict:
            client = httpx.AsyncClient(
                base_url="http://127.0.0.1:11435",
                transport=httpx.MockTransport(handler),
            )
            with patch("app.model_eval.httpx.AsyncClient", return_value=client):
                return await evaluate_models()

        report = asyncio.run(exercise())
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["models_tested"], ["broken", "chat", "vectors"])
        broken, chat, embedding = report["model_results"]
        self.assertEqual(broken["status"], "unavailable")
        self.assertIsNone(broken["areas"]["answer"]["score"])
        self.assertEqual(chat["overall_score"], 1)
        self.assertEqual(embedding["status"], "healthy")
        self.assertEqual(embedding["areas"], {})
        self.assertEqual(
            len(
                [
                    body
                    for path, body in requests
                    if path == "/api/chat" and body["model"] == "broken"
                ]
            ),
            1,
        )
        self.assertEqual(
            [body["model"] for path, body in requests if path == "/api/generate"],
            ["broken", "chat", "vectors"],
        )
        preferences = build_preferences(report)
        self.assertTrue(
            all(
                models == ["chat"] for models in preferences["area_priorities"].values()
            )
        )
        self.assertNotIn("vectors", preferences["scores"])
        self.assertEqual(preferences["model_profiles"]["vectors"]["kind"], "embedding")
        corrected = rescore_report(report)
        self.assertEqual(corrected["scorer_version"], 3)
        self.assertEqual(corrected["priority_by_area"], report["priority_by_area"])
        self.assertEqual(
            corrected["scoring_history"][0]["previous_scores"]["chat"]["code_change"], 1
        )

    def test_rejects_external_endpoint_before_network_access(self) -> None:
        with self.assertRaisesRegex(ValueError, "local Ollama"):
            asyncio.run(evaluate_models(base_url="https://example.com"))

    def test_merge_preserves_baseline_areas_and_checks_model_identity(self) -> None:
        area = _summarize_area(
            [
                {
                    "id": "test",
                    "status": "ok",
                    "actual": {"answer": 1},
                    "score": 1,
                    "passed": True,
                    "latency_seconds": 1,
                    "error": None,
                }
            ],
            "answer",
        )
        report = {
            "status": "completed",
            "models_tested": ["chat"],
            "settings": {},
            "started_at": "start",
            "completed_at": "end",
            "note": "",
            "cases": [{"id": "test", "area": "answer", "expected": {"answer": 1}}],
            "model_results": [
                {
                    "model": "chat",
                    "kind": "chat",
                    "digest": "same",
                    "duration_seconds": 1,
                    "status": "healthy",
                    "areas": {"answer": area},
                }
            ],
        }
        merged = merge_reports(report, report)
        self.assertEqual(len(merged["measurement_rounds"]), 2)
        self.assertEqual(merged["model_results"][0]["duration_seconds"], 2)
        self.assertEqual(report["model_results"][0]["duration_seconds"], 1)
        with self.assertRaisesRegex(ValueError, "same installed"):
            merge_reports(report, {**report, "models_tested": ["different"]})
        with self.assertRaisesRegex(ValueError, "complete"):
            merge_reports(report, {**report, "status": "running"})


if __name__ == "__main__":
    unittest.main()
