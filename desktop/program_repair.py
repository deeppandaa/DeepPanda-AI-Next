from __future__ import annotations

import ast
import difflib
import hashlib
import json
import operator
import re
from pathlib import PureWindowsPath
from typing import Any

REVIEW_TOOL = {
    "name": "review.report",
    "description": "Read-only diagnosis of actual failed tests. No execution, writing or approval authority.",
    "parameters": {
        "type": "object",
        "properties": {
            "root_cause": {"type": "string", "minLength": 1, "maxLength": 1800},
            "recommended_change": {"type": "string", "minLength": 1, "maxLength": 1800},
            "checks": {"type": "array", "items": {"type": "string", "maxLength": 400}, "maxItems": 8},
            "test_conflicts": {
                "type": "array", "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "test_id": {"type": "string", "minLength": 1, "maxLength": 300},
                        "explanation": {"type": "string", "minLength": 1, "maxLength": 600},
                    },
                    "required": ["test_id", "explanation"], "additionalProperties": False,
                },
            },
            "source_evidence": {
                "type": "array", "minItems": 1, "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 200},
                        "quote": {"type": "string", "minLength": 10, "maxLength": 600},
                    },
                    "required": ["path", "quote"], "additionalProperties": False,
                },
            },
        },
        "required": ["root_cause", "recommended_change", "checks", "source_evidence", "test_conflicts"],
        "additionalProperties": False,
    },
}

ACCEPTANCE_REVIEW_TOOL = {
    "name": "acceptance.review",
    "description": "Read-only review of test coverage against project criteria and source evidence.",
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "minLength": 1, "maxLength": 1200},
            "request_coverage": {
                "type": "object",
                "properties": {
                    "status": {
                        "enum": [
                            "no_obvious_gaps", "gaps_found", "incomplete_original_request",
                            "original_request_unavailable",
                        ],
                    },
                    "omissions": {
                        "type": "array", "maxItems": 8,
                        "items": {
                            "type": "object",
                            "properties": {
                                "quote": {"type": "string", "minLength": 10, "maxLength": 180},
                                "rationale": {"type": "string", "minLength": 1, "maxLength": 240},
                            },
                            "required": ["quote", "rationale"], "additionalProperties": False,
                        },
                    },
                },
                "required": ["status", "omissions"], "additionalProperties": False,
            },
            "criteria": {
                "type": "array", "maxItems": 32,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "pattern": "^C[1-9][0-9]*$"},
                        "assessment": {"enum": ["test_linked", "gap", "conflict", "unverifiable"]},
                        "rationale": {"type": "string", "minLength": 1, "maxLength": 240},
                        "evidence": {
                            "type": "array", "maxItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "minLength": 1, "maxLength": 100},
                                    "quote": {"type": "string", "minLength": 10, "maxLength": 180},
                                    "test_id": {"type": "string", "minLength": 1, "maxLength": 300},
                                },
                                "required": ["path", "quote"], "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["id", "assessment", "rationale", "evidence"],
                    "additionalProperties": False,
                },
            },
            "findings": {
                "type": "array", "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"enum": ["high", "medium", "low"]},
                        "summary": {"type": "string", "minLength": 1, "maxLength": 240},
                        "evidence": {
                            "type": "array", "minItems": 1, "maxItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "minLength": 1, "maxLength": 100},
                                    "quote": {"type": "string", "minLength": 10, "maxLength": 180},
                                },
                                "required": ["path", "quote"], "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["severity", "summary", "evidence"],
                    "additionalProperties": False,
                },
            },
            "source_evidence": {
                "type": "array", "minItems": 1, "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 100},
                        "quote": {"type": "string", "minLength": 10, "maxLength": 180},
                    },
                    "required": ["path", "quote"], "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "request_coverage", "criteria", "findings", "source_evidence"],
        "additionalProperties": False,
    },
}


def repair_context(project: str, evidence: dict[str, Any]) -> str:
    """Keep repair inputs separate from the deliberately shortened display result."""
    data = {
        "project": project,
        "passed": evidence.get("passed"),
        "tests": evidence.get("tests"),
        "exit_code": evidence.get("exit_code"),
        "failure_details": evidence.get("failure_details"),
        "failure_kind": failure_kind(evidence),
        "repair_history": evidence.get("repair_history", []),
        "source_files": [dict(item) for item in evidence.get("source_files", [])],
    }
    for key, limit in (("stderr", 12000), ("stdout", 4000)):
        text = str(evidence.get(key, ""))
        data[key] = text[:limit]
        data[key + "_truncated"] = bool(evidence.get(key + "_truncated")) or len(text) > limit
    result = json.dumps(data, ensure_ascii=False)
    if len(result) > 48000:
        raise ValueError("Düzeltme kanıtı 48.000 karakter sınırını aşıyor; otomatik düzeltme yapılmadı.")
    return result


def acceptance_review_context(project: str, request: str, evidence: dict[str, Any]) -> str:
    criteria, criteria_truncated = parse_criteria(evidence.get("criteria", ""))
    request_hash = evidence.get("criteria_request_sha256")
    request_hash_matches = (
        isinstance(request_hash, str) and re.fullmatch(r"[a-f0-9]{64}", request_hash) is not None
        and hashlib.sha256(request.encode("utf-8")).hexdigest() == request_hash
    )
    original_request = request[:12000] if request_hash_matches else ""
    data = {
        "project": project,
        "passed": evidence.get("passed"),
        "tests": evidence.get("tests"),
        "source_integrity": evidence.get("source_integrity"),
        "criteria": criteria,
        "criteria_truncated": criteria_truncated,
        "criteria_request_sha256": request_hash,
        "original_requirements_status": (
            "truncated" if request_hash_matches and len(request) > 12000
            else "available" if request_hash_matches else "unavailable"
        ),
        "original_requirements": original_request,
        "original_requirements_truncated": bool(request_hash_matches and len(request) > 12000),
        "source_files": [dict(item) for item in evidence.get("source_files", [])],
    }
    while True:
        result = json.dumps(data, ensure_ascii=False)
        if len(result) <= 48000:
            return result
        sources = data["source_files"]
        largest = max(
            (item for item in sources if item.get("content")),
            key=lambda item: len(item["content"]),
            default=None,
        )
        if largest is None:
            raise ValueError("Bağımsız kabul incelemesi için güvenli bağlam 48.000 karakter sınırını aşıyor.")
        largest["content"] = largest["content"][:len(largest["content"]) // 2]
        largest["truncated"] = True


def parse_criteria(value: Any) -> tuple[list[dict[str, str]], bool]:
    lines = []
    for line in str(value).splitlines():
        criterion = re.sub(r"^\d+[.)]\s*", "", line.strip()).lstrip("-*• ").strip()
        if criterion:
            lines.append(criterion)
    return (
        [{"id": f"C{index}", "text": text} for index, text in enumerate(lines[:32], 1)],
        len(lines) > 32,
    )


def failure_kind(evidence: dict[str, Any]) -> str:
    if evidence.get("source_integrity", {}).get("unchanged") is False:
        return "source_integrity"
    if evidence.get("cancelled"):
        return "cancelled"
    if evidence.get("timed_out"):
        return "timeout"
    kinds = {item.get("kind") for item in (evidence.get("failure_details") or {}).get("items", [])}
    if "error" in kinds:
        return "test_error"
    if "failure" in kinds:
        return "assertion_failure"
    return "unclassified"


def repair_state(evidence: dict[str, Any], files: list[dict[str, str]]) -> str:
    sources = {
        str(PureWindowsPath(item["path"])).casefold(): item["content"]
        for item in evidence.get("source_files", [])
    }
    sources.update({str(PureWindowsPath(item["path"])).casefold(): item["content"] for item in files})
    state = []
    for path, content in sorted(sources.items()):
        try:
            normalized = ast.dump(ast.parse(content), include_attributes=False)
        except SyntaxError:
            normalized = content
        state.append((path, normalized))
    return hashlib.sha256(json.dumps(state, ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_review_sources(report: dict[str, Any], evidence: dict[str, Any]) -> None:
    sources = {
        str(PureWindowsPath(item["path"])).casefold(): item["content"]
        for item in evidence.get("source_files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
        and isinstance(item.get("content"), str) and item.get("truncated") is False
    }
    for citation in report["source_evidence"]:
        content = sources.get(str(PureWindowsPath(citation["path"])).casefold())
        if content is None or citation["quote"] not in content:
            raise ValueError(
                f"İncelemecinin kaynak alıntısı gerçek tam dosyada yok: "
                f"{citation['path']!r}, {citation['quote'][:120]!r}; yazma yapılmadı."
            )
    conflicts = report.get("test_conflicts", [])
    details = evidence.get("failure_details") or {}
    failed_ids = {item["test_id"] for item in details.get("items", [])}
    seen = set()
    for conflict in conflicts:
        test_id = conflict["test_id"]
        if test_id not in failed_ids or test_id in seen:
            raise ValueError("Test çelişkisi güncel başarısız test kimliğiyle eşleşmiyor veya tekrarlı.")
        seen.add(test_id)
        cited_modules = {
            ".".join(PureWindowsPath(citation["path"]).with_suffix("").parts).casefold()
            for citation in report["source_evidence"]
            if PureWindowsPath(citation["path"]).suffix.casefold() == ".py"
            and PureWindowsPath(citation["path"]).stem.casefold().startswith("test")
        }
        if not any(test_id.casefold().startswith(module + ".") for module in cited_modules):
            raise ValueError("Test çelişkisi ilgili test dosyasından doğrulanmış alıntı gerektirir.")


def has_executable_test_assertion(source: str, quote: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    with_contexts = {
        id(item.context_expr)
        for parent in ast.walk(tree)
        if isinstance(parent, (ast.With, ast.AsyncWith))
        for item in parent.items
    }

    class AssertionVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.matches = False

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Assert(self, node: ast.Assert) -> None:
            self._check(node)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and (
                node.func.attr.startswith("assert") and len(node.func.attr) > len("assert")
                or node.func.attr in {"raises", "warns"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pytest"
                and id(node) in with_contexts
            ):
                self._check(node)
            self.generic_visit(node)

        def _check(self, node: ast.AST) -> None:
            assertion = ast.get_source_segment(source, node)
            if assertion and (assertion in quote or quote in assertion):
                self.matches = True

    def has_matching_test_body(statements: list[ast.stmt]) -> bool:
        visitor = AssertionVisitor()
        for statement in statements:
            visitor.visit(statement)
        return visitor.matches

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.casefold().startswith("test") and has_matching_test_body(node.body):
                return True
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if (
                    isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and member.name.casefold().startswith("test")
                    and has_matching_test_body(member.body)
                ):
                    return True
    return False


def has_behavior_linked_test_assertion(
    source: str, quote: str, implementation_sources: list[str], executed_lines: set[int] | None = None,
) -> bool:
    try:
        tree = ast.parse(source)
        implementations = [ast.parse(content) for content in implementation_sources]
    except SyntaxError:
        return False

    implementation_symbols = {
        node.name
        for implementation in implementations
        for node in ast.walk(implementation)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    if not implementation_symbols:
        return False
    with_contexts = {
        id(item.context_expr)
        for parent in ast.walk(tree)
        if isinstance(parent, (ast.With, ast.AsyncWith))
        for item in parent.items
    }

    def has_eager_matching_call(node: ast.AST) -> bool:
        if isinstance(node, ast.Call) and (
            isinstance(node.func, ast.Name) and node.func.id in implementation_symbols
            or isinstance(node.func, ast.Attribute) and node.func.attr in implementation_symbols
        ):
            return executed_lines is None or node.lineno in executed_lines
        if isinstance(node, ast.BoolOp):
            children = node.values[:1]
        elif isinstance(node, ast.IfExp):
            children = [node.test]
        elif isinstance(node, ast.Compare):
            children = [node.left, *node.comparators[:1]]
        elif isinstance(node, ast.Lambda):
            children = []
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            children = [node.generators[0].iter] if node.generators else []
        else:
            children = list(ast.iter_child_nodes(node))
        return any(has_eager_matching_call(child) for child in children)

    def statements_have_eager_matching_call(statements: list[ast.stmt]) -> bool:
        for statement in statements:
            expressions: list[ast.expr] = []
            if isinstance(statement, (ast.Expr, ast.Assign, ast.AnnAssign)) and statement.value is not None:
                expressions = [statement.value]
            elif isinstance(statement, (ast.Assert, ast.If, ast.While)):
                expressions = [statement.test]
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                expressions = [statement.iter]
            if any(has_eager_matching_call(expression) for expression in expressions):
                return True
        return False

    def constant_truth(node: ast.AST) -> bool | None:
        try:
            return bool(ast.literal_eval(node))
        except (MemoryError, RecursionError, SyntaxError, TypeError, ValueError):
            pass
        if isinstance(node, ast.BoolOp):
            checks = [constant_truth(value) for value in node.values]
            if isinstance(node.op, ast.Or):
                if True in checks:
                    return True
                return False if all(check is False for check in checks) else None
            if False in checks:
                return False
            return True if all(check is True for check in checks) else None
        if isinstance(node, ast.IfExp):
            test = constant_truth(node.test)
            if test is not None:
                return constant_truth(node.body if test else node.orelse)
            body, otherwise = constant_truth(node.body), constant_truth(node.orelse)
            return body if body is otherwise else None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = constant_truth(node.operand)
            return not operand if operand is not None else None
        if isinstance(node, ast.Compare):
            operations = {
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.Lt: operator.lt,
                ast.LtE: operator.le,
                ast.Gt: operator.gt,
                ast.GtE: operator.ge,
                ast.In: lambda left, right: left in right,
                ast.NotIn: lambda left, right: left not in right,
            }
            try:
                values = [ast.literal_eval(node.left), *(ast.literal_eval(item) for item in node.comparators)]
            except (MemoryError, RecursionError, SyntaxError, TypeError, ValueError):
                return None
            results: list[bool] = []
            try:
                for operation, left, right in zip(node.ops, values, values[1:]):
                    compare = operations.get(type(operation))
                    if compare is None:
                        return None
                    results.append(bool(compare(left, right)))
            except (TypeError, ValueError):
                return None
            return all(results)
        return None

    def is_always_truthy(node: ast.AST) -> bool:
        return constant_truth(node) is True

    def is_always_falsy(node: ast.AST) -> bool:
        return constant_truth(node) is False

    def is_boolean_expression(node: ast.AST) -> bool:
        if isinstance(node, ast.Constant):
            return isinstance(node.value, bool)
        if isinstance(node, ast.Compare):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return True
        if isinstance(node, ast.BoolOp):
            return all(is_boolean_expression(value) for value in node.values)
        return False

    def constant_boolean(node: ast.AST) -> bool | None:
        if not is_boolean_expression(node):
            return None
        if isinstance(node, ast.BoolOp):
            values = [constant_boolean(value) for value in node.values]
            if isinstance(node.op, ast.Or):
                if True in values:
                    return True
                return False if all(value is False for value in values) else None
            if False in values:
                return False
            return True if all(value is True for value in values) else None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = constant_boolean(node.operand)
            return not operand if operand is not None else None
        return constant_truth(node)

    def is_vacuous_assertion(node: ast.AST) -> bool:
        if isinstance(node, ast.Assert):
            return is_always_truthy(node.test)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args:
            if node.func.attr == "assertTrue":
                return is_always_truthy(node.args[0])
            if node.func.attr == "assertFalse":
                return is_always_falsy(node.args[0])
            if node.func.attr in {"assertEqual", "assertIs", "assertNotEqual", "assertIsNot"} \
                    and len(node.args) >= 2:
                left, right = constant_boolean(node.args[0]), constant_boolean(node.args[1])
                if left is not None and right is not None:
                    if node.func.attr in {"assertEqual", "assertIs"}:
                        return left is right
                    return left is not right
        return False

    def names(node: ast.AST, context: type[ast.expr_context]) -> set[str]:
        return {item.id for item in ast.walk(node) if isinstance(item, ast.Name) and isinstance(item.ctx, context)}

    class TestBodyVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.assertions: list[ast.Assert | ast.Call] = []
            self.assignments: list[ast.Assign | ast.AnnAssign | ast.AugAssign] = []
            self.writes: list[tuple[int, set[str]]] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Assert(self, node: ast.Assert) -> None:
            self.assertions.append(node)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and (
                node.func.attr.startswith("assert") and len(node.func.attr) > len("assert")
                or node.func.attr in {"raises", "warns"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pytest"
                and id(node) in with_contexts
            ):
                self.assertions.append(node)
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            self.assignments.append(node)
            self.writes.append((node.lineno, names(node, ast.Store)))
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            self.assignments.append(node)
            self.writes.append((node.lineno, names(node, ast.Store)))
            self.generic_visit(node)

        def visit_AugAssign(self, node: ast.AugAssign) -> None:
            self.assignments.append(node)
            self.writes.append((node.lineno, names(node, ast.Store)))
            self.generic_visit(node)

        def visit_For(self, node: ast.For) -> None:
            self.writes.append((node.lineno, names(node.target, ast.Store)))
            self.generic_visit(node)

        visit_AsyncFor = visit_For

        def visit_With(self, node: ast.With) -> None:
            for item in node.items:
                if item.optional_vars is not None:
                    self.writes.append((node.lineno, names(item.optional_vars, ast.Store)))
            self.generic_visit(node)

        visit_AsyncWith = visit_With

        def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
            self.writes.append((node.lineno, names(node.target, ast.Store)))
            self.generic_visit(node)

    def source_quote_contains(node: ast.AST) -> bool:
        segment = ast.get_source_segment(source, node)
        return bool(segment and segment in quote)

    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) or not function.name.casefold().startswith("test"):
            continue
        visitor = TestBodyVisitor()
        for statement in function.body:
            visitor.visit(statement)
        for assertion in visitor.assertions:
            if not source_quote_contains(assertion):
                continue
            if executed_lines is not None and assertion.lineno not in executed_lines:
                continue
            if is_vacuous_assertion(assertion):
                continue
            is_pytest_context = (
                isinstance(assertion, ast.Call) and isinstance(assertion.func, ast.Attribute)
                and assertion.func.attr in {"raises", "warns"}
                and id(assertion) in with_contexts
            )
            if not is_pytest_context and has_eager_matching_call(assertion):
                return True
            assertion_names = names(assertion, ast.Load)
            for assignment in visitor.assignments:
                if assignment.lineno >= assertion.lineno:
                    continue
                target_names = names(assignment, ast.Store)
                value = getattr(assignment, "value", None)
                if (
                    assertion_names & target_names
                    and isinstance(value, ast.AST)
                    and has_eager_matching_call(value)
                    and source_quote_contains(assignment)
                    and (executed_lines is None or assignment.lineno in executed_lines)
                ):
                    linked_names = assertion_names & target_names
                    if any(
                        assignment.lineno < write_line < assertion.lineno
                        and bool(linked_names & written_names)
                        for write_line, written_names in visitor.writes
                    ):
                        continue
                    return True
            if isinstance(assertion, ast.Call) and isinstance(assertion.func, ast.Attribute) \
                    and assertion.func.attr in {"raises", "warns"}:
                with_statement = next(
                    (
                        parent for parent in ast.walk(tree)
                        if isinstance(parent, (ast.With, ast.AsyncWith))
                        and any(item.context_expr is assertion for item in parent.items)
                    ),
                    None,
                )
                if (
                    with_statement is not None and source_quote_contains(with_statement)
                    and statements_have_eager_matching_call(with_statement.body)
                ):
                    return True
    return False


def test_id_matches_source(test_id: str, path: PureWindowsPath, source: str) -> bool:
    parts = test_id.split(".")
    module_parts = tuple(part.casefold() for part in path.with_suffix("").parts)
    if not any(
        tuple(part.casefold() for part in parts[start:start + len(module_parts)]) == module_parts
        for start in (len(parts) - len(module_parts) - 1, len(parts) - len(module_parts) - 2)
        if start >= 0
    ):
        return False
    test_name = parts[-1]
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == test_name
        and node.name.casefold().startswith("test")
        for node in ast.walk(tree)
    )


def validate_acceptance_review(
    report: dict[str, Any], evidence: dict[str, Any], criteria: list[dict[str, str]], request: str,
) -> None:
    sources = {
        str(PureWindowsPath(item["path"])).casefold(): item["content"]
        for item in evidence.get("source_files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
        and isinstance(item.get("content"), str) and item.get("truncated") is False
    }
    implementation_sources = [
        content for path, content in sources.items()
        if not (
            PureWindowsPath(path).name.casefold().startswith("test")
            or PureWindowsPath(path).stem.casefold().endswith("_test")
            or any(part.casefold() in {"test", "tests"} for part in PureWindowsPath(path).parts[:-1])
        )
    ]

    def verify_quotes(citations: list[dict[str, str]], *, require_test: bool = False) -> None:
        for citation in citations:
            path = PureWindowsPath(citation["path"])
            content = sources.get(str(path).casefold())
            if content is None or citation["quote"] not in content:
                raise ValueError(
                    f"Bağımsız kabul alıntısı tam güncel kaynakta yok: "
                    f"{citation['path']!r}, {citation['quote'][:120]!r}."
                )
            if require_test and not (
                path.name.casefold().startswith("test")
                or path.stem.casefold().endswith("_test")
                or any(part.casefold() in {"test", "tests"} for part in path.parts[:-1])
            ):
                raise ValueError("Testle ilişkilendirilen ölçüt için gerçek test dosyası alıntısı gerekir.")
            if require_test:
                test_result = evidence.get("tests")
                test_ids = test_result.get("test_ids") if isinstance(test_result, dict) else None
                skipped_ids = test_result.get("skipped_test_ids", []) if isinstance(test_result, dict) else []
                skipped_ids_truncated = (
                    test_result.get("skipped_test_ids_truncated")
                    if isinstance(test_result, dict) else None
                )
                test_id = citation.get("test_id")
                if (
                    not isinstance(test_ids, list) or not isinstance(skipped_ids, list)
                    or skipped_ids_truncated is not False
                    or not isinstance(test_id, str) or test_id not in test_ids or test_id in skipped_ids
                    or not test_id_matches_source(test_id, path, content)
                ):
                    raise ValueError("Test alıntısı başarılı son koşumun atlanmamış test kimliğiyle eşleşmelidir.")
                line_records = test_result.get("executed_test_lines")
                source_path = path.as_posix().casefold()
                line_record = next((
                    item for item in line_records
                    if isinstance(item, dict) and item.get("test_id") == test_id
                    and isinstance(item.get("path"), str)
                    and PureWindowsPath(item["path"]).as_posix().casefold() == source_path
                ), None) if isinstance(line_records, list) else None
                lines = line_record.get("lines") if isinstance(line_record, dict) else None
                if (
                    not isinstance(lines, list) or line_record.get("truncated") is not False
                    or any(isinstance(line, bool) or not isinstance(line, int) or line <= 0 for line in lines)
                ):
                    raise ValueError("Test assertion satırlarının başarılı koşumda çalıştırıldığı doğrulanamadı.")
                if not has_behavior_linked_test_assertion(
                    content, citation["quote"], implementation_sources, set(lines),
                ):
                    raise ValueError("Alıntılanan assertion/uygulama çağrısı başarılı test koşumunda çalıştırılmamış.")

    verify_quotes(report["source_evidence"])
    coverage = report["request_coverage"]
    request_hash = evidence.get("criteria_request_sha256")
    request_matches = (
        isinstance(request_hash, str) and re.fullmatch(r"[a-f0-9]{64}", request_hash) is not None
        and hashlib.sha256(request.encode("utf-8")).hexdigest() == request_hash
    )
    if not request_matches:
        if coverage["status"] != "original_request_unavailable" or coverage["omissions"]:
            raise ValueError("Özgün istek hash'iyle eşleşmedi; kapsama iddiası/atlanan gereksinim raporu reddedildi.")
    elif len(request) > 12000:
        if coverage["status"] != "incomplete_original_request":
            raise ValueError("Özgün istek kesilmiş; tam kapsam raporu reddedildi.")
    else:
        if coverage["status"] not in {"no_obvious_gaps", "gaps_found"}:
            raise ValueError("Eksiksiz özgün istek için kapsam durumu geçersiz.")
        if (coverage["status"] == "gaps_found") != bool(coverage["omissions"]):
            raise ValueError("Kapsama boşluğu durumu atlanan gereksinim alıntılarıyla tutarsız.")
    for omission in coverage["omissions"]:
        if omission["quote"] not in request[:12000]:
            raise ValueError("Atlanan gereksinim alıntısı hash'le eşleşen özgün istekte birebir bulunamadı.")
    expected_ids = [item["id"] for item in criteria]
    reviewed_ids = [item["id"] for item in report["criteria"]]
    if reviewed_ids != expected_ids:
        raise ValueError("Bağımsız inceleme ölçüt kimliklerini eksik, tekrarlı veya farklı sırada döndürdü.")
    for item in report["criteria"]:
        test_evidence_required = item["assessment"] in {"test_linked", "conflict"}
        verify_quotes(item["evidence"], require_test=test_evidence_required)
        if test_evidence_required and not item["evidence"]:
            raise ValueError("Testle ilişkilendirilen ölçüt sınıfı için çalıştırılabilir test kaynak alıntısı eksik.")
    for finding in report["findings"]:
        verify_quotes(finding["evidence"])


def repair_attempt(arguments: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    sources = {str(PureWindowsPath(item["path"])).casefold(): item["content"]
               for item in evidence["source_files"]}
    changes = []
    for item in arguments["files"]:
        old = sources[str(PureWindowsPath(item["path"])).casefold()]
        diff = "".join(difflib.unified_diff(
            old.splitlines(keepends=True), item["content"].splitlines(keepends=True),
            fromfile=item["path"], tofile=item["path"],
        ))
        changes.append({"path": item["path"], "diff": diff[:2000], "truncated": len(diff) > 2000})
    return {
        "before_state": repair_state(evidence, []),
        "after_state": repair_state(evidence, arguments["files"]),
        "before_tests": evidence.get("tests"),
        "before_failures": evidence.get("failure_details"),
        "changes": changes[:4], "omitted_changes": max(0, len(changes) - 4),
    }


def validate_repair(arguments: dict[str, Any], evidence: dict[str, Any]) -> None:
    sources = {
        str(PureWindowsPath(item["path"])).casefold(): item
        for item in evidence.get("source_files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
        and isinstance(item.get("content"), str)
    }
    files = arguments.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Otomatik düzeltme mevcut Python uygulama dosyası değişikliği gerektirir.")
    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("content"), str):
            raise TypeError("Otomatik düzeltme dosyası geçersiz.")
        path = PureWindowsPath(item["path"])
        key = str(path).casefold()
        if (
            path.is_absolute() or path.drive or ".." in path.parts or path.suffix.casefold() != ".py"
            or path.name.casefold().startswith("test") or path.stem.casefold().endswith("_test")
            or any(part.casefold() in {"test", "tests"} for part in path.parts[:-1])
        ):
            raise ValueError("Otomatik düzeltme testleri/README'yi değiştiremez; yalnız mevcut uygulama Python dosyaları.")
        original = sources.get(key)
        if original is None or original.get("truncated") is not False or key in seen:
            raise ValueError("Düzeltilecek dosyanın tam ve tekil kaynak kanıtı yok; otomatik yazma yapılmadı.")
        seen.add(key)
        try:
            old = ast.parse(original["content"])
            new = ast.parse(item["content"])
        except SyntaxError as exc:
            raise ValueError("Düzeltme Python sözdizimi geçersiz; dosya yazılmadı.") from exc
        if ast.dump(old) == ast.dump(new):
            raise ValueError("Düzeltme yalnız biçim/yorum değiştiriyor; kod değişmediği için yazılmadı.")
    candidate = repair_state(evidence, files)
    if any(candidate in {attempt.get("before_state"), attempt.get("after_state")}
           for attempt in evidence.get("repair_history", [])):
        raise ValueError("Düzeltme daha önce denenmiş eşdeğer kaynak durumunu tekrarlıyor; yazma yapılmadı.")
