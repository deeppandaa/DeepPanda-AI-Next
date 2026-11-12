from __future__ import annotations

import hashlib
import json
import unittest

from jsonschema import validate

from desktop.chat_agent import compact_result
from desktop.program_repair import (
    ACCEPTANCE_REVIEW_TOOL,
    acceptance_review_context,
    has_behavior_linked_test_assertion,
    has_executable_test_assertion,
    parse_criteria,
    repair_attempt,
    repair_context,
    validate_acceptance_review,
    validate_repair,
    validate_review_sources,
)


class ProgramRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = {
            "passed": False, "exit_code": 1,
            "tests": {
                "tests": 1, "failures": 1, "test_ids": ["test_app.test_add"],
                "test_ids_truncated": False, "skipped_test_ids": [], "skipped_test_ids_truncated": False,
                "executed_test_lines": [{
                    "test_id": "test_app.test_add", "path": "test_app.py",
                    "lines": [2], "truncated": False,
                }],
            },
            "stdout": "noise" * 6400, "stderr": "AssertionError: 5 != 15",
            "source_files": [
                {"path": "app.py", "content": "def add(a,b):\n    return a-b\n", "truncated": False},
                {
                    "path": "test_app.py",
                    "content": "def test_add():\n    assert add(10,5)==15\n",
                    "truncated": False,
                },
            ],
        }

    def test_exact_sources_and_failure_are_preserved_after_display_is_truncated(self) -> None:
        display = compact_result(self.evidence)
        self.assertNotIn("source_files", display)
        context = json.loads(repair_context("sample", self.evidence))
        self.assertEqual(context["source_files"], self.evidence["source_files"])
        self.assertEqual(context["stderr"], "AssertionError: 5 != 15")
        self.assertTrue(context["stdout_truncated"])
        self.assertLessEqual(len(json.dumps(context, ensure_ascii=False)), 48000)

    def test_real_implementation_edit_is_accepted(self) -> None:
        validate_repair({"files": [{"path": "app.py", "content": "def add(a,b):\n    return a+b\n"}]}, self.evidence)

    def test_equivalent_previously_failed_state_is_rejected_before_writing(self) -> None:
        corrected = {"files": [{"path": "app.py", "content": "def add(a,b):\n    return a+b\n"}]}
        attempt = repair_attempt(corrected, self.evidence)
        current = {**self.evidence, "source_files": [
            {"path": "app.py", "content": corrected["files"][0]["content"], "truncated": False},
            self.evidence["source_files"][1],
        ], "repair_history": [attempt]}
        with self.assertRaisesRegex(ValueError, "denenmiş"):
            validate_repair({"files": [{"path": "app.py", "content": "def add(a, b):\n    return a - b\n"}]}, current)
        validate_repair({"files": [{"path": "app.py", "content": "def add(a,b):\n    return abs(a)+abs(b)\n"}]}, current)

    def test_failure_kind_in_context_is_grounded_not_semantic_diagnosis(self) -> None:
        for extra, expected in (
            ({"source_integrity": {"unchanged": False}}, "source_integrity"),
            ({"cancelled": True}, "cancelled"),
            ({"timed_out": True}, "timeout"),
            ({"failure_details": {"items": [{"kind": "failure"}]}}, "assertion_failure"),
            ({"failure_details": {"items": [{"kind": "error"}]}}, "test_error"),
            ({}, "unclassified"),
        ):
            with self.subTest(extra=extra):
                context = json.loads(repair_context("sample", {**self.evidence, **extra}))
                self.assertEqual(context["failure_kind"], expected)

    def test_long_outputs_preserve_integrity_failure_in_test_and_package_summaries(self) -> None:
        integrity = {"unchanged": False, "changed_paths": ["app.py"], "omitted": 0}
        for status in (
            {"passed": False, "tests": {"tests": 1, "passed": True}},
            {"packaged": False},
        ):
            with self.subTest(status=status):
                compact = compact_result({
                    **status, "source_integrity": integrity, "integrity_error": "Source changed",
                    "stdout": "x" * 32000,
                })
                self.assertEqual(compact["source_integrity"], integrity)
                self.assertEqual(compact["integrity_error"], "Source changed")
                self.assertLessEqual(len(json.dumps(compact, ensure_ascii=False)), 5000)

    def test_review_quotes_must_exist_in_full_current_sources(self) -> None:
        report = {"source_evidence": [{"path": "APP.py", "quote": "return a-b"}]}
        validate_review_sources(report, self.evidence)
        for path, quote in (("app.py", "return a+b"), ("missing.py", "return a-b")):
            with self.subTest(path=path, quote=quote), self.assertRaises(ValueError):
                validate_review_sources({"source_evidence": [{"path": path, "quote": quote}]}, self.evidence)
        self.evidence["source_files"][0]["truncated"] = True
        with self.assertRaises(ValueError):
            validate_review_sources(report, self.evidence)

    def test_acceptance_review_requires_complete_criterion_ids_and_exact_test_citations(self) -> None:
        criteria = [{"id": "C1", "text": "Add values"}]
        evidence = {
            "tests": {
                "test_ids": ["test_app.test_add"], "test_ids_truncated": False,
                "skipped_test_ids": [], "skipped_test_ids_truncated": False,
                "executed_test_lines": [{
                    "test_id": "test_app.test_add", "path": "test_app.py",
                    "lines": [1, 2, 3], "truncated": False,
                }],
            },
            "source_files": [
                {"path": "app.py", "content": "def add(a,b):\n    return a+b\n", "truncated": False},
                {
                    "path": "test_app.py",
                    "content": "def test_add():\n    # assert add(3, 2) == 5\n    assert add(2, 3) == 5\n",
                    "truncated": False,
                },
                {"path": "hidden.py", "content": "secret = True\n", "truncated": True},
            ],
        }
        report = {
            "summary": "The criterion is linked to a test, not independently verified.",
            "request_coverage": {"status": "original_request_unavailable", "omissions": []},
            "criteria": [{
                "id": "C1", "assessment": "test_linked", "rationale": "A test asserts addition.",
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(2, 3) == 5",
                    "test_id": "test_app.test_add",
                }],
            }],
            "findings": [],
            "source_evidence": [{"path": "app.py", "quote": "return a+b"}],
        }
        validate_acceptance_review(report, evidence, criteria, "Create sample")
        validate(report, ACCEPTANCE_REVIEW_TOOL["parameters"])
        evidence["tests"]["executed_test_lines"] = []
        with self.assertRaisesRegex(ValueError, "çalıştırıldığı"):
            validate_acceptance_review(report, evidence, criteria, "Create sample")
        evidence["tests"]["executed_test_lines"] = [{
            "test_id": "test_app.test_add", "path": "test_app.py",
            "lines": [1], "truncated": False,
        }]
        with self.assertRaisesRegex(ValueError, "çalıştırılmamış"):
            validate_acceptance_review(report, evidence, criteria, "Create sample")
        for invalid in (
            {**report, "criteria": []},
            {**report, "request_coverage": {"status": "gaps_found", "omissions": []}},
            {**report, "criteria": [{**report["criteria"][0], "id": "C2"}]},
            {**report, "criteria": [{
                **report["criteria"][0],
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(4, 1) == 5",
                    "test_id": "test_app.test_add",
                }],
            }]},
            {**report, "criteria": [{
                **report["criteria"][0],
                "evidence": [{"path": "hidden.py", "quote": "secret = True"}],
            }]},
            {**report, "criteria": [{
                **report["criteria"][0],
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(2, 3) == 5",
                    "test_id": "test_app.test_missing",
                }],
            }]},
            {**report, "criteria": [{
                **report["criteria"][0],
                "evidence": [{"path": "test_app.py", "quote": "assert add(2, 3) == 5"}],
            }]},
            {**report, "criteria": [{
                **report["criteria"][0],
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(3, 2) == 5",
                    "test_id": "test_app.test_add",
                }],
            }]},
        ):
            with self.subTest(report=invalid), self.assertRaises(ValueError):
                validate_acceptance_review(invalid, evidence, criteria, "Create sample")
        skipped_evidence = {**evidence, "tests": {
            **evidence["tests"], "skipped_test_ids": ["test_app.test_add"],
        }}
        with self.assertRaises(ValueError):
            validate_acceptance_review(report, skipped_evidence, criteria, "Create sample")
        incomplete_skips = {**evidence, "tests": {
            **evidence["tests"], "skipped_test_ids_truncated": True,
        }}
        with self.assertRaises(ValueError):
            validate_acceptance_review(report, incomplete_skips, criteria, "Create sample")

    def test_test_linked_evidence_recognizes_runtime_assertion_forms_only(self) -> None:
        cases = (
            ("def test_add():\n    assert add(2, 3) == 5\n", "assert add(2, 3) == 5", True),
            ("def test_add(self):\n    self.assertEqual(add(2, 3), 5)\n",
             "self.assertEqual(add(2, 3), 5)", True),
            (("class TestMath(unittest.TestCase):\n    def test_add(self):\n"
              "        self.assertEqual(add(2, 3), 5)\n"),
             "self.assertEqual(add(2, 3), 5)", True),
            ("def test_invalid():\n    with pytest.raises(ValueError):\n        parse(None)\n",
             "pytest.raises(ValueError)", True),
            ("def test_add():\n    def unused_helper():\n        assert add(2, 3) == 5\n",
             "assert add(2, 3) == 5", False),
            ("def test_invalid():\n    pytest.raises(ValueError)\n",
             "pytest.raises(ValueError)", False),
            ("def test_add():\n    # assert add(2, 3) == 5\n    pass\n",
             "assert add(2, 3) == 5", False),
            ("assert add(2, 3) == 5\n", "assert add(2, 3) == 5", False),
        )
        for source, quote, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(has_executable_test_assertion(source, quote), expected)

    def test_conflict_assessment_requires_an_executable_test_citation(self) -> None:
        request = "Add values"
        evidence = {
            "tests": {
                "test_ids": ["test_app.test_add"], "test_ids_truncated": False,
                "skipped_test_ids": [], "skipped_test_ids_truncated": False,
                "executed_test_lines": [{
                    "test_id": "test_app.test_add", "path": "test_app.py",
                    "lines": [1, 2, 3], "truncated": False,
                }],
            },
            "source_files": self.evidence["source_files"],
        }
        criteria = [{"id": "C1", "text": "Add values"}]
        report = {
            "summary": "A test contradicts the criterion.",
            "request_coverage": {"status": "original_request_unavailable", "omissions": []},
            "criteria": [{
                "id": "C1", "assessment": "conflict", "rationale": "The test asserts a different result.",
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(10,5)==15",
                    "test_id": "test_app.test_add",
                }],
            }],
            "findings": [],
            "source_evidence": [{"path": "app.py", "quote": "return a-b"}],
        }
        validate_acceptance_review(report, evidence, criteria, request)
        for invalid_evidence in (
            [],
            [{"path": "app.py", "quote": "return a-b"}],
            [{"path": "test_app.py", "quote": "def test_add():", "test_id": "test_app.test_add"}],
        ):
            with self.subTest(invalid_evidence=invalid_evidence), self.assertRaises(ValueError):
                validate_acceptance_review(
                    {**report, "criteria": [{**report["criteria"][0], "evidence": invalid_evidence}]},
                    evidence, criteria, request,
                )

    def test_test_linked_rejects_vacuous_assertions_and_unconnected_calls(self) -> None:
        request = "Add values"
        criteria = [{"id": "C1", "text": "Add values"}]
        evidence = {
            "tests": {
                "test_ids": ["test_app.test_add"], "test_ids_truncated": False,
                "skipped_test_ids": [], "skipped_test_ids_truncated": False,
                "executed_test_lines": [{
                    "test_id": "test_app.test_add", "path": "test_app.py",
                    "lines": list(range(1, 16)), "truncated": False,
                }],
            },
            "source_files": [
                {"path": "app.py", "content": "def add(a, b):\n    return a + b\n", "truncated": False},
                {
                    "path": "test_app.py",
                    "content": (
                        "def test_add():\n"
                        "    add(2, 3)\n"
                        "    assert True\n"
                    ),
                    "truncated": False,
                },
            ],
        }
        report = {
            "summary": "A test is linked to the criterion.",
            "request_coverage": {"status": "original_request_unavailable", "omissions": []},
            "criteria": [{
                "id": "C1", "assessment": "test_linked", "rationale": "The test invokes addition.",
                "evidence": [{"path": "test_app.py", "quote": "assert True", "test_id": "test_app.test_add"}],
            }],
            "findings": [],
            "source_evidence": [{"path": "app.py", "quote": "return a + b"}],
        }
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    result = add(2, 3); result = 999; assert result == 999\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = (
            "result = add(2, 3); result = 999; assert result == 999"
        )
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    assert True or add(2, 3)\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = "assert True or add(2, 3)"
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    assert add(2, 3) == 6 or True\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = "assert add(2, 3) == 6 or True"
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    assert add(2, 3) == 6 or 3 > 2\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = "assert add(2, 3) == 6 or 3 > 2"
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    result = add(2, 3)\n"
            "    for result in (999,):\n"
            "        pass\n"
            "    assert result == 999\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = (
            "result = add(2, 3)\n"
            "    for result in (999,):\n"
            "        pass\n"
            "    assert result == 999"
        )
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    result = add(2, 3)\n"
            "    result = 999\n"
            "    assert result == 999\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = (
            "result = add(2, 3)\n    result = 999\n    assert result == 999"
        )
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

        evidence["source_files"][1]["content"] = (
            "def test_add():\n"
            "    result = add(2, 3)\n"
            "    assert result == 5\n"
        )
        report["criteria"][0]["evidence"][0]["quote"] = (
            "result = add(2, 3)\n    assert result == 5"
        )
        validate_acceptance_review(report, evidence, criteria, request)

        report["criteria"][0]["evidence"][0]["quote"] = "assert result == 5"
        with self.assertRaisesRegex(ValueError, "assertion"):
            validate_acceptance_review(report, evidence, criteria, request)

    def test_behavior_linked_exception_test_requires_real_with_context_invocation(self) -> None:
        implementation = ["def parse(value):\n    if value is None: raise ValueError()\n"]
        valid = (
            "def test_parse():\n"
            "    with pytest.raises(ValueError):\n"
            "        parse(None)\n"
        )
        self.assertTrue(has_behavior_linked_test_assertion(
            valid, "with pytest.raises(ValueError):\n        parse(None)", implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse():\n    pytest.raises(parse(None))\n",
            "pytest.raises(parse(None))", implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse():\n"
            "    with pytest.raises(ValueError):\n"
            "        True or parse(None)\n",
            "with pytest.raises(ValueError):\n        True or parse(None)",
            implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse():\n    assert parse(None) == 1 or True\n",
            "assert parse(None) == 1 or True",
            implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse(self):\n    self.assertTrue(parse(None) or True)\n",
            "self.assertTrue(parse(None) or True)",
            implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse():\n    assert parse(None) == 1 or 3 > 2\n",
            "assert parse(None) == 1 or 3 > 2",
            implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse(self):\n"
            "    self.assertEqual(parse(None) > 1 or True, True)\n",
            "self.assertEqual(parse(None) > 1 or True, True)",
            implementation,
        ))
        self.assertFalse(has_behavior_linked_test_assertion(
            "def test_parse():\n    with pytest.raises(ValueError):\n        pass\n",
            "with pytest.raises(ValueError):\n        pass",
            ["def raises(): pass\n"],
        ))

    def test_request_coverage_gaps_require_exact_quotes_from_hash_matched_original_request(self) -> None:
        request = "Create a report that adds numbers and rejects negative values."
        evidence = {
            "criteria_request_sha256": hashlib.sha256(request.encode()).hexdigest(),
            "tests": self.evidence["tests"],
            "source_files": self.evidence["source_files"],
        }
        report = {
            "summary": "The original request contains one requirement not represented in criteria.",
            "request_coverage": {
                "status": "gaps_found",
                "omissions": [{"quote": "rejects negative values", "rationale": "No criterion covers rejection."}],
            },
            "criteria": [{
                "id": "C1", "assessment": "test_linked", "rationale": "A test checks addition.",
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(10,5)==15",
                    "test_id": "test_app.test_add",
                }],
            }],
            "findings": [],
            "source_evidence": [{"path": "app.py", "quote": "return a-b"}],
        }
        criteria = [{"id": "C1", "text": "Add numbers"}]
        validate_acceptance_review(report, evidence, criteria, request)
        report["request_coverage"]["omissions"][0]["quote"] = "rejects negative values now"
        with self.assertRaisesRegex(ValueError, "özgün istekte"):
            validate_acceptance_review(report, evidence, criteria, request)

    def test_truncated_original_request_cannot_be_reported_as_fully_reviewed(self) -> None:
        request = "Create report. " + ("requirement text " * 900)
        evidence = {
            "criteria_request_sha256": hashlib.sha256(request.encode()).hexdigest(),
            "tests": self.evidence["tests"],
            "source_files": self.evidence["source_files"],
        }
        report = {
            "summary": "Only the excerpt was reviewed.",
            "request_coverage": {"status": "incomplete_original_request", "omissions": []},
            "criteria": [{
                "id": "C1", "assessment": "test_linked", "rationale": "A test checks the result.",
                "evidence": [{
                    "path": "test_app.py", "quote": "assert add(10,5)==15",
                    "test_id": "test_app.test_add",
                }],
            }],
            "findings": [],
            "source_evidence": [{"path": "app.py", "quote": "return a-b"}],
        }
        criteria = [{"id": "C1", "text": "Add numbers"}]
        context = json.loads(acceptance_review_context("sample", request, evidence))
        self.assertEqual(context["original_requirements_status"], "truncated")
        validate_acceptance_review(report, evidence, criteria, request)
        report["request_coverage"]["status"] = "no_obvious_gaps"
        with self.assertRaisesRegex(ValueError, "kesilmiş"):
            validate_acceptance_review(report, evidence, criteria, request)

    def test_acceptance_review_context_is_bounded_and_does_not_mutate_evidence(self) -> None:
        sources = [{"path": "app.py", "content": "\\" * 30000, "truncated": False}]
        request = "Create sample"
        evidence = {
            "source_files": sources, "criteria": "- Add values\n2. Reject invalid",
            "criteria_request_sha256": hashlib.sha256(request.encode()).hexdigest(),
        }
        context = acceptance_review_context("sample", request, evidence)
        self.assertLessEqual(len(context), 48000)
        self.assertFalse(sources[0]["truncated"])
        self.assertEqual(len(sources[0]["content"]), 30000)
        data = json.loads(context)
        self.assertEqual(data["original_requirements_status"], "available")
        self.assertEqual(data["original_requirements"], request)
        self.assertEqual(data["criteria"], [
            {"id": "C1", "text": "Add values"}, {"id": "C2", "text": "Reject invalid"},
        ])
        self.assertFalse(data["criteria_truncated"])
        followup = json.loads(acceptance_review_context("sample", "Test sample", evidence))
        self.assertEqual(followup["original_requirements_status"], "unavailable")
        self.assertEqual(followup["original_requirements"], "")
        criteria, truncated = parse_criteria("\n".join(f"- criterion {index}" for index in range(33)))
        self.assertEqual(len(criteria), 32)
        self.assertTrue(truncated)

    def test_acceptance_report_schema_keeps_worst_case_result_under_chat_context_limit(self) -> None:
        quote = "x" * 180
        path = "p" * 100
        criteria = [{
            "id": f"C{index}", "assessment": "test_linked", "rationale": "r" * 240,
            "evidence": [{"path": path, "quote": quote}],
        } for index in range(1, 33)]
        report = {
            "summary": "s" * 1200,
            "request_coverage": {
                "status": "gaps_found",
                "omissions": [{"quote": quote, "rationale": "o" * 240} for _ in range(8)],
            },
            "criteria": criteria,
            "findings": [{
                "severity": "medium", "summary": "f" * 240,
                "evidence": [{"path": path, "quote": quote}],
            } for _ in range(4)],
            "source_evidence": [{"path": path, "quote": quote} for _ in range(4)],
        }
        validate(report, ACCEPTANCE_REVIEW_TOOL["parameters"])
        self.assertLess(len(json.dumps(report)), 48000)

    def test_attempt_keeps_actual_before_failures_and_bounded_diff_in_context(self) -> None:
        self.evidence["failure_details"] = {"items": [{"test_id": "test.add", "traceback": "wrong"}], "omitted": 0}
        attempt = repair_attempt({
            "files": [{"path": "app.py", "content": "def add(a,b):\n    return a+b\n"}],
        }, self.evidence)
        self.assertEqual(attempt["before_failures"], self.evidence["failure_details"])
        self.assertIn("-    return a-b", attempt["changes"][0]["diff"])
        self.assertIn("+    return a+b", attempt["changes"][0]["diff"])
        data = json.loads(repair_context("sample", {**self.evidence, "repair_history": [attempt]}))
        self.assertEqual(data["repair_history"], [attempt])
        self.assertEqual(data["failure_details"], self.evidence["failure_details"])

    def test_conflict_requires_current_failed_id_and_actual_test_source(self) -> None:
        self.evidence["failure_details"] = {
            "items": [{"test_id": "test_app.Checks.test_add", "kind": "failure"}], "omitted": 0,
        }
        conflict = {"test_id": "test_app.Checks.test_add", "explanation": "Incorrect expected result"}
        valid = {
            "source_evidence": [{"path": "test_app.py", "quote": "assert add(10,5)==15"}],
            "test_conflicts": [conflict],
        }
        validate_review_sources(valid, self.evidence)
        for report in (
            {**valid, "test_conflicts": [{**conflict, "test_id": "test_app.Checks.test_invented"}]},
            {**valid, "test_conflicts": [conflict, conflict]},
            {**valid, "source_evidence": [{"path": "app.py", "quote": "return a-b"}]},
        ):
            with self.subTest(report=report), self.assertRaises(ValueError):
                validate_review_sources(report, self.evidence)
        self.evidence["source_files"][1]["path"] = r"tests\test_app.py"
        nested_id = "tests.test_app.Checks.test_add"
        self.evidence["failure_details"]["items"][0]["test_id"] = nested_id
        nested = {
            "source_evidence": [{"path": r"tests\test_app.py", "quote": "assert add(10,5)==15"}],
            "test_conflicts": [{**conflict, "test_id": nested_id}],
        }
        validate_review_sources(nested, self.evidence)
        nested["source_evidence"][0]["path"] = r"TESTS\TEST_APP.PY"
        validate_review_sources(nested, self.evidence)
        self.evidence["failure_details"]["items"][0]["test_id"] = "tests.test_other.Checks.test_add"
        nested["test_conflicts"][0]["test_id"] = "tests.test_other.Checks.test_add"
        with self.assertRaisesRegex(ValueError, "alıntı"):
            validate_review_sources(nested, self.evidence)

    def test_test_readme_missing_truncated_duplicate_and_format_only_updates_are_rejected(self) -> None:
        for path, content in (
            ("test_app.py", "pass"), ("tests/helpers.py", "pass"), ("module_test.py", "pass"),
            ("README.md", "fixed"), ("missing.py", "pass"), ("../app.py", "pass"),
            ("app.py", "# fixed\n\ndef add(a, b):\n    return a - b\n"),
            ("app.py", "def broken("),
        ):
            with self.subTest(path=path, content=content), self.assertRaises(ValueError):
                validate_repair({"files": [{"path": path, "content": content}]}, self.evidence)
        self.evidence["source_files"][0]["truncated"] = True
        with self.assertRaises(ValueError):
            validate_repair({"files": [{"path": "app.py", "content": "fixed=True"}]}, self.evidence)
        self.evidence["source_files"][0]["truncated"] = False
        with self.assertRaises(ValueError):
            validate_repair({"files": [{"path": "app.py", "content": "fixed=True"}] * 2}, self.evidence)

    def test_oversized_raw_evidence_is_explicit_error_not_silent_cutoff(self) -> None:
        self.evidence["source_files"][0]["content"] = "x" * 48000
        with self.assertRaisesRegex(ValueError, "48.000"):
            repair_context("sample", self.evidence)
