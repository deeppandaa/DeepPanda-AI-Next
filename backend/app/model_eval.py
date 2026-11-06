from __future__ import annotations

import argparse
import ast
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

from app.intent_eval import DEFAULT_CASES_PATH, load_cases, score_results
from app.main import create_app
from app.plugins.gateway import PluginGateway
from app.plugins.intent_router import IntentRouterPlugin
from app.plugins.ollama import OllamaPlugin
from app.plugins.task_assistant import TaskAssistantPlugin

CAPABILITY_CASES_PATH = Path(__file__).with_name("model_capability_cases.json")
AREA_NAMES = ("intent", "answer", "planning", "source_grounded", "learning", "code_change")


def load_capability_cases(path: Path = CAPABILITY_CASES_PATH) -> dict[str, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Capability evaluation file must be a JSON object.")
    cases: dict[str, list[dict[str, Any]]] = {}
    for area in ("answer", "planning", "source_grounded", "learning", "code_change"):
        values = data.get(area)
        if not isinstance(values, list) or not values:
            raise ValueError(f"Capability evaluation area '{area}' must have at least one case.")
        ids: set[str] = set()
        for index, case in enumerate(values):
            if not isinstance(case, dict):
                raise ValueError(f"{area}[{index}] must be an object.")
            case_id = case.get("id")
            if not isinstance(case_id, str) or not case_id.strip() or case_id in ids:
                raise ValueError(f"{area}[{index}].id must be unique non-empty text.")
            ids.add(case_id)
        cases[area] = values
    return cases


def _concept_coverage(text: str, groups: list[list[str]]) -> tuple[float, list[bool]]:
    normalized_text = text.casefold()
    matched = [any(term.casefold() in normalized_text for term in group) for group in groups]
    return (sum(matched) / len(matched) if matched else 1.0), matched


def _mean_score(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return round(sum(result["score"] for result in results) / len(results), 4)


def _mean_latency(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return round(statistics.mean(result["latency_seconds"] for result in results), 3)


class _CodeEvaluationGateway:
    def __init__(self, ollama: OllamaPlugin, case: dict[str, Any]) -> None:
        self.ollama = ollama
        self.case = case

    async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> Any:
        if plugin_id == "ollama":
            return await self.ollama.invoke(action, payload)
        if (plugin_id, action) == ("tasks", "get"):
            return {"task": {
                "task_id": "0" * 32,
                "request": self.case["request"],
                "approved": True,
                "steps": [{"step_index": 0, "title": "Apply bounded patch", "status": "in_progress"}],
            }}
        if (plugin_id, action) == ("workspace", "read"):
            if payload.get("path") != self.case["path"]:
                raise ValueError("Evaluation requested an unselected source path.")
            return {"path": self.case["path"], "content": self.case["source"]}
        raise AssertionError(f"Unexpected evaluation action: {plugin_id}/{action}")


async def _json_chat(
    ollama: OllamaPlugin,
    model: str,
    message: str,
    schema: dict[str, Any],
    system_prompt: str,
    max_output_tokens: int = 256,
) -> dict[str, Any]:
    response = await ollama.invoke("chat", {
        "message": message,
        "model": model,
        "format": "json",
        "response_schema": schema,
        "max_output_tokens": max_output_tokens,
        "max_context_tokens": 8_192,
        "think": False,
        "system_prompt": system_prompt,
        "messages": [],
    })
    if isinstance(response, dict) and response.get("done_reason") == "length":
        raise ValueError("Model JSON output was truncated.")
    message_data = response.get("message") if isinstance(response, dict) else None
    content = message_data.get("content") if isinstance(message_data, dict) else None
    if not isinstance(content, str):
        raise ValueError("Model returned no JSON content.")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON output must be an object.")
    return parsed


async def _evaluate_answer_area(
    ollama: OllamaPlugin, model: str, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    system_prompt = "Answer the user's question accurately and minimally. Return the requested JSON only."
    for case in cases:
        started = time.perf_counter()
        try:
            answer_type = "integer" if isinstance(case["expected"], int) else "string"
            output = await _json_chat(
                ollama,
                model,
                json.dumps({"question": case["prompt"]}, ensure_ascii=False),
                {
                    "type": "object",
                    "properties": {"answer": {"type": answer_type}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
                system_prompt,
                max_output_tokens=128,
            )
            actual = output.get("answer")
            passed = type(actual) is type(case["expected"]) and actual == case["expected"]
            results.append({
                "id": case["id"],
                "score": float(passed),
                "passed": passed,
                "actual": actual,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            })
        except Exception as exc:
            results.append({
                "id": case["id"],
                "score": 0.0,
                "passed": False,
                "actual": None,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


async def _evaluate_planning_area(
    ollama: OllamaPlugin, model: str, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    gateway = PluginGateway()
    gateway.register(ollama)
    app = create_app(gateway)
    results = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://model-eval"
    ) as client:
        for case in cases:
            started = time.perf_counter()
            try:
                response = await client.post("/api/tasks/draft", json={
                    "request": case["request"],
                    "model": model,
                })
                data = response.json()
                steps = data.get("steps") if isinstance(data, dict) else None
                valid_steps = (
                    response.status_code == 200
                    and isinstance(steps, list)
                    and case["min_steps"] <= len(steps) <= case["max_steps"]
                    and all(isinstance(step, str) and step.strip() for step in steps)
                )
                step_text = "\n".join(steps) if valid_steps else ""
                coverage, matched = _concept_coverage(step_text, case["required_concepts"])
                score = (0.4 + 0.6 * coverage) if valid_steps else 0.0
                results.append({
                    "id": case["id"],
                    "score": round(score, 4),
                    "passed": valid_steps and coverage == 1.0,
                    "valid_steps": valid_steps,
                    "concept_coverage": round(coverage, 4),
                    "matched_concepts": matched,
                    "step_count": len(steps) if isinstance(steps, list) else 0,
                    "steps": steps if isinstance(steps, list) else [],
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "error": data.get("detail") if response.status_code != 200 else None,
                })
            except Exception as exc:
                results.append({
                    "id": case["id"],
                    "score": 0.0,
                    "passed": False,
                    "valid_steps": False,
                    "concept_coverage": 0.0,
                    "matched_concepts": [],
                    "step_count": 0,
                    "steps": [],
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "error": f"{type(exc).__name__}: {exc}",
                })
    return results


async def _evaluate_source_area(
    ollama: OllamaPlugin, model: str, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    system_prompt = (
        "Answer only from the supplied source lines. Do not use prior knowledge. "
        "Return one short answer and the 1-based line number that directly supports it."
    )
    schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "minLength": 1, "maxLength": 300},
            "evidence_line": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["answer", "evidence_line"],
        "additionalProperties": False,
    }
    for case in cases:
        started = time.perf_counter()
        try:
            source = "\n".join(
                f"{index}: {line}" for index, line in enumerate(case["source_lines"], start=1)
            )
            output = await _json_chat(
                ollama,
                model,
                json.dumps({"question": case["question"], "source_lines": source}, ensure_ascii=False),
                schema,
                system_prompt,
                max_output_tokens=256,
            )
            expected_answers = case.get("expected_answers", [case.get("expected_answer", "")])
            answer = output.get("answer", "").casefold()
            answer_ok = any(expected.casefold() in answer for expected in expected_answers)
            evidence_ok = output.get("evidence_line") == case["expected_line"]
            results.append({
                "id": case["id"],
                "score": round((int(answer_ok) + int(evidence_ok)) / 2, 4),
                "passed": answer_ok and evidence_ok,
                "answer_ok": answer_ok,
                "evidence_ok": evidence_ok,
                "actual": output,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            })
        except Exception as exc:
            results.append({
                "id": case["id"],
                "score": 0.0,
                "passed": False,
                "answer_ok": False,
                "evidence_ok": False,
                "actual": None,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


async def _evaluate_learning_area(
    router: IntentRouterPlugin, model: str, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            routed = await router.invoke("route", {"message": case["message"], "model": model})
            proposal = routed.get("learning_proposal")
            proposal_text = " ".join(proposal.values()).casefold() if isinstance(proposal, dict) else ""
            coverage, matched = _concept_coverage(proposal_text, case["required_terms"])
            is_learn = routed["intent"] == "learn"
            score = coverage if is_learn and proposal else 0.0
            results.append({
                "id": case["id"],
                "score": round(score, 4),
                "passed": is_learn and proposal is not None and coverage == 1.0,
                "intent": routed["intent"],
                "proposal_present": proposal is not None,
                "concept_coverage": round(coverage, 4),
                "matched_concepts": matched,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            })
        except Exception as exc:
            results.append({
                "id": case["id"],
                "score": 0.0,
                "passed": False,
                "intent": None,
                "proposal_present": False,
                "concept_coverage": 0.0,
                "matched_concepts": [],
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


class _CodeEvaluationGateway:
    def __init__(self, ollama: OllamaPlugin, case: dict[str, Any]) -> None:
        self.ollama = ollama
        self.case = case

    async def invoke(self, plugin_id: str, action: str, payload: dict[str, Any]) -> Any:
        if plugin_id == "ollama":
            return await self.ollama.invoke(action, payload)
        if (plugin_id, action) == ("tasks", "get"):
            return {"task": {
                "task_id": "0" * 32,
                "request": self.case["request"],
                "approved": True,
                "steps": [{"step_index": 0, "title": "Propose bounded patch", "status": "in_progress"}],
            }}
        if (plugin_id, action) == ("workspace", "read"):
            if payload.get("path") != self.case["path"]:
                raise ValueError("The evaluator requested an unselected source file.")
            return {"path": self.case["path"], "content": self.case["source"]}
        raise AssertionError(f"Unexpected evaluator action: {plugin_id}/{action}")


async def _evaluate_code_area(
    ollama: OllamaPlugin, model: str, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            gateway = _CodeEvaluationGateway(ollama, case)
            assistant = TaskAssistantPlugin(gateway)  # type: ignore[arg-type]
            proposal = await assistant.invoke("propose_change", {
                "approved": True,
                "task_id": "0" * 32,
                "step_index": 0,
                "path": case["path"],
                "model": model,
                "instruction": case["request"],
            })
            ast.parse(proposal["content"], filename=case["path"])
            coverage, matched = _concept_coverage(proposal["content"], case["required_concepts"])
            results.append({
                "id": case["id"],
                "score": round(0.35 + 0.65 * coverage, 4),
                "passed": coverage == 1.0,
                "source_range_valid": True,
                "python_syntax_valid": True,
                "concept_coverage": round(coverage, 4),
                "matched_concepts": matched,
                "summary": proposal["summary"],
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            })
        except Exception as exc:
            results.append({
                "id": case["id"],
                "score": 0.0,
                "passed": False,
                "source_range_valid": False,
                "python_syntax_valid": False,
                "concept_coverage": 0.0,
                "matched_concepts": [],
                "summary": "",
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


async def _evaluate_one_model(
    model: str,
    intent_cases: list[dict[str, str]],
    capability_cases: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    ollama = OllamaPlugin()
    gateway = PluginGateway()
    gateway.register(ollama)
    router = IntentRouterPlugin(gateway)
    intent_results = []
    for case in intent_cases:
        started = time.perf_counter()
        try:
            routed = await router.invoke("route", {"message": case["text"], "model": model})
            intent_results.append({
                "id": case["id"],
                "expected": case["expected"],
                "actual": routed["intent"],
                "confidence": routed["confidence"],
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": None,
            })
        except Exception as exc:
            intent_results.append({
                "id": case["id"],
                "expected": case["expected"],
                "actual": None,
                "confidence": None,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            })
    intent_metrics = score_results(intent_results)
    intent_score = intent_metrics["macro_f1"]
    areas: dict[str, dict[str, Any]] = {
        "intent": {
            "score": intent_score,
            "case_count": len(intent_results),
            "mean_latency_seconds": _mean_latency(intent_results),
            "metrics": intent_metrics,
            "results": intent_results,
        }
    }

    evaluators = {
        "answer": _evaluate_answer_area,
        "planning": _evaluate_planning_area,
        "source_grounded": _evaluate_source_area,
        "learning": _evaluate_learning_area,
        "code_change": _evaluate_code_area,
    }
    for area, evaluator in evaluators.items():
        if area == "learning":
            area_results = await evaluator(router, model, capability_cases[area])
        else:
            area_results = await evaluator(ollama, model, capability_cases[area])
        areas[area] = {
            "score": _mean_score(area_results),
            "case_count": len(area_results),
            "mean_latency_seconds": _mean_latency(area_results),
            "results": area_results,
        }
    overall_score = round(statistics.mean(area["score"] for area in areas.values()), 4)
    return {"model": model, "overall_score": overall_score, "areas": areas}


async def evaluate_models(
    models: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    ollama = OllamaPlugin()
    if models is None:
        catalog = await ollama.invoke("models", {})
        models = [
            item["name"]
            for item in catalog.get("models", [])
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and "embed" not in item["name"].casefold()
            and not item["name"].casefold().endswith(("-cloud", ":cloud"))
        ]
    models = list(dict.fromkeys(models))
    if not models:
        raise ValueError("No local chat models are available for evaluation.")

    intent_cases = load_cases(DEFAULT_CASES_PATH)
    capability_cases = load_capability_cases()
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        intent_cases = intent_cases[:limit]
        capability_cases = {
            area: cases[:limit] for area, cases in capability_cases.items()
        }

    model_results = []
    for model in models:
        model_results.append(await _evaluate_one_model(model, intent_cases, capability_cases))

    areas = ("intent", "answer", "planning", "source_grounded", "learning", "code_change")
    priorities = {
        area: [
            row["model"]
            for row in sorted(
                model_results,
                key=lambda row: (
                    -row["areas"][area]["score"],
                    row["areas"][area]["mean_latency_seconds"],
                ),
            )
        ]
        for area in areas
    }
    overall_rank = sorted(model_results, key=lambda row: -row["overall_score"])
    return {
        "models_tested": models,
        "case_counts": {
            "intent": len(intent_cases),
            **{area: len(cases) for area, cases in capability_cases.items()},
        },
        "areas": list(areas),
        "overall_ranking": [
            {"rank": index + 1, "model": row["model"], "score": row["overall_score"]}
            for index, row in enumerate(overall_rank)
        ],
        "priority_by_area": priorities,
        "model_results": model_results,
        "note": "Scores use small deterministic checks; they rank these fixtures, not general intelligence or safety.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark all installed local chat models across fixed capability checks."
    )
    parser.add_argument("--model", action="append", help="Test one model; may be supplied more than once. Defaults to all installed local chat models.")
    parser.add_argument("--limit", type=int, help="Run only the first N cases per area for a quick smoke test.")
    parser.add_argument("--output", type=Path, help="Optional path for the full JSON benchmark report.")
    parser.add_argument("--routing-output", type=Path, help="Optional path for the ranked model-routing preference JSON.")
    args = parser.parse_args()
    try:
        report = asyncio.run(evaluate_models(args.model, args.limit))
    except (OSError, ValueError, json.JSONDecodeError, httpx.HTTPError) as exc:
        parser.error(str(exc))

    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.routing_output:
        preferences = {
            "version": 1,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "models_tested": report["models_tested"],
            "area_priorities": report["priority_by_area"],
            "scores": {
                row["model"]: {area: row["areas"][area]["score"] for area in report["areas"]}
                for row in report["model_results"]
            },
            "source": "model_eval deterministic local benchmark",
        }
        args.routing_output.parent.mkdir(parents=True, exist_ok=True)
        args.routing_output.write_text(
            json.dumps(preferences, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())