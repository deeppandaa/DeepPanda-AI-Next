from __future__ import annotations

import argparse
import ast
import asyncio
import copy
import hashlib
import json
import math
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

CAPABILITY_CASES_PATH = Path(__file__).with_name("model_capability_cases.json")
BENCHMARK_CASES_PATH = Path(__file__).with_name("model_benchmark_cases.json")
AREA_DESCRIPTIONS = {
    "intent": "Türkçe/İngilizce istek türünü ayırma; hiçbir araç çalıştırılmaz.",
    "answer": "Kısa Türkçe anlama, olumsuzluk ve aritmetik; serbest sohbet kalitesi ölçülmez.",
    "planning": "Bağımlılık sıralama, güvenli geçiş planı ve döngü fark etme.",
    "source_grounded": "Verilen kaynaktan alıntı satırıyla bilgi çıkarma; web tarama testi değildir.",
    "learning": "Proje tercihi çıkarma ve kaydetmeme isteğine uyma; bellek yazılmaz.",
    "code_change": "Küçük Python düzeltmelerinin AST kontrolü ve kod akıl yürütme; kod çalıştırılmaz.",
}
AREA_NAMES = tuple(AREA_DESCRIPTIONS)
MINIMUM_AREA_SCORE = 0.5
SCORER_VERSION = 3
SYSTEM_PROMPT = "Answer the task with the requested JSON object only. Never run tools, commands, or code."
AREA_SYSTEM_PROMPTS = {
    "intent": (
        " Classify only the quoted user request. answer means direct information or conversation; "
        "plan means steps without execution; research means gathering/analyzing external sources; "
        "learn means explicitly proposing a reusable project fact/preference for reviewed memory, "
        "NOT an educational question; action_request means actually changing files, running commands, "
        "or performing actions. Precedence: action_request, research, learn, plan, answer. "
        "A request to plan then execute is action_request. The evaluation's do-not-perform instruction "
        "does not change the intent of the quoted request."
    ),
    "learning": (
        " Extract the quoted user's memory intent only. save_requested means the USER explicitly "
        "asked to remember a project fact; it does not mean anything was saved or approved. "
        "The evaluator's instruction not to save is not part of the quoted user request."
    ),
}


def load_capability_cases(
    path: Path = CAPABILITY_CASES_PATH,
) -> dict[str, list[dict[str, Any]]]:
    """Read the older fixtures for consumers that still use their prompt examples."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Capability evaluation file must be a JSON object.")
    cases = {}
    for area in AREA_NAMES[1:]:
        values = data.get(area)
        if not isinstance(values, list) or not values:
            raise ValueError(
                f"Capability evaluation area '{area}' must have at least one case."
            )
        ids = [case.get("id") for case in values if isinstance(case, dict)]
        if (
            len(ids) != len(values)
            or any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError(f"{area} case IDs must be unique non-empty text.")
        cases[area] = values
    return cases


def _concept_coverage(text: str, groups: list[list[str]]) -> tuple[float, list[bool]]:
    matched = [
        any(term.casefold() in text.casefold() for term in group) for group in groups
    ]
    return (sum(matched) / len(matched) if matched else 1.0), matched


def load_benchmark_cases(path: Path = BENCHMARK_CASES_PATH) -> list[dict[str, Any]]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark requires a non-empty cases list.")
    seen = set()
    for case in cases:
        if not isinstance(case, dict) or case.get("area") not in AREA_NAMES:
            raise ValueError("Invalid benchmark area.")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("Benchmark IDs must be unique non-empty text.")
        if not isinstance(case.get("prompt"), str) or not isinstance(
            case.get("expected"), dict
        ):
            raise TypeError(
                "Benchmark cases require a prompt and expected JSON object."
            )
        seen.add(case_id)
    if any(sum(case["area"] == area for case in cases) < 2 for area in AREA_NAMES):
        raise ValueError("Every area requires at least two deterministic cases.")
    return cases


def _schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {key: _schema(item) for key, item in value.items()},
            "required": list(value),
            "additionalProperties": False,
        }
    if isinstance(value, list):
        return {"type": "array", "items": _schema(value[0]) if value else {}}
    if value is None:
        # Do not leak the correct answer through a null-only constrained schema.
        return {"type": ["string", "null"]}
    return {
        "type": "boolean"
        if isinstance(value, bool)
        else "integer"
        if isinstance(value, int)
        else "string"
    }


def _normalized_ast(code: str) -> str:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], ast.Lt)
            and isinstance(node.left, ast.Name)
            and isinstance(node.comparators[0], ast.Name)
        ):
            node.left, node.comparators[0] = node.comparators[0], node.left
            node.ops = [ast.Gt()]
        body = getattr(node, "body", None)
        if isinstance(body, list):
            normalized = []
            for statement in body:
                normalized.append(statement)
                if (
                    isinstance(statement, ast.If)
                    and statement.body
                    and isinstance(statement.body[-1], (ast.Return, ast.Raise))
                    and statement.orelse
                ):
                    # A guard that exits makes its else equivalent to following statements.
                    normalized.extend(statement.orelse)
                    statement.orelse = []
            node.body = normalized
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == "ValueError"
            and not node.exc.keywords
            and all(
                isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                for arg in node.exc.args
            )
        ):
            # A literal exception message does not change the required guard behavior.
            node.exc.args = []
    return ast.dump(tree, include_attributes=False)


def score_case(case: dict[str, Any], actual: Any) -> tuple[float, dict[str, bool]]:
    if not isinstance(actual, dict):
        return 0.0, {"json_object": False}
    if case.get("code_templates"):
        code = actual.get("code")
        try:
            syntax_ok = isinstance(code, str) and len(code) < 20_000
            canonical = _normalized_ast(code) if syntax_ok else ""
            matches = syntax_ok and canonical in {
                _normalized_ast(template) for template in case["code_templates"]
            }
        except (SyntaxError, ValueError, RecursionError):
            syntax_ok, matches = False, False
        checks = {
            "python_syntax_valid": syntax_ok,
            "allowed_ast_matches": matches,
            "exact_keys": set(actual) == {"code"},
        }
    else:
        expected = case["expected"]
        checks = {
            key: type(actual.get(key)) is type(value)
            and json.dumps(actual.get(key), sort_keys=True)
            == json.dumps(value, sort_keys=True)
            for key, value in expected.items()
        }
        checks["exact_keys"] = set(actual) == set(expected)
    return float(all(checks.values())), checks


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        pending = path.with_suffix(path.suffix + ".pending")
        pending.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        pending.replace(path)


async def _request(
    client: httpx.AsyncClient, method: str, path: str, timeout: float, **kwargs: Any
) -> dict[str, Any]:
    async with asyncio.timeout(timeout):
        response = await client.request(
            method,
            path,
            timeout=httpx.Timeout(timeout, connect=min(5, timeout)),
            **kwargs,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Ollama response must be an object.")
        if data.get("error"):
            raise ValueError(str(data["error"])[:500])
        return data


async def _unload(client: httpx.AsyncClient, model: str, timeout: float) -> None:
    await _request(
        client, "POST", "/api/generate", timeout, json={"model": model, "keep_alive": 0}
    )
    deadline = time.monotonic() + timeout
    while True:
        loaded = await _request(
            client, "GET", "/api/ps", min(5, max(0.1, deadline - time.monotonic()))
        )
        if not any(
            item.get("name") == model or item.get("model") == model
            for item in loaded.get("models", [])
        ):
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Model {model} did not unload; refusing overlapping inference."
            )
        await asyncio.sleep(0.25)


def _summarize_area(results: list[dict[str, Any]], area: str) -> dict[str, Any]:
    attempted = [result for result in results if result["status"] != "skipped"]
    scores = [result["score"] for result in attempted]
    errors = [result for result in attempted if result["status"] != "ok"]
    score = round(statistics.mean(scores), 4) if scores else None
    complete = len(attempted) == len(results)
    eligible = (
        complete
        and len(attempted) >= 2
        and not errors
        and score is not None
        and score >= MINIMUM_AREA_SCORE
    )
    return {
        "score": score,
        "case_count": len(results),
        "attempted_count": len(attempted),
        "passed": sum(result["passed"] for result in attempted),
        "error_count": len(errors),
        "mean_latency_seconds": round(
            statistics.mean(result["latency_seconds"] for result in attempted), 3
        )
        if attempted
        else None,
        "status": "healthy"
        if eligible
        else "untested"
        if not attempted
        else "unavailable"
        if len(errors) == len(attempted)
        else "degraded",
        "eligible": eligible,
        "description": AREA_DESCRIPTIONS[area],
        "results": results,
    }


async def _evaluate_chat(
    client: httpx.AsyncClient,
    model: str,
    cases: list[dict[str, Any]],
    request_timeout: float,
    cold_timeout: float,
    model_timeout: float,
) -> dict[str, Any]:
    started = time.monotonic()
    results = []
    circuit_reason = None
    for index, case in enumerate(cases):
        remaining = model_timeout - (time.monotonic() - started)
        if remaining <= 0:
            circuit_reason = "per-model deadline exceeded"
        if circuit_reason:
            results.append(
                {
                    "id": case["id"],
                    "area": case["area"],
                    "status": "skipped",
                    "score": None,
                    "passed": False,
                    "latency_seconds": 0,
                    "error": circuit_reason,
                }
            )
            continue
        case_started = time.monotonic()
        result: dict[str, Any] = {
            "id": case["id"],
            "area": case["area"],
            "status": "ok",
            "error": None,
        }
        try:
            body = {
                "model": model,
                "stream": False,
                "think": False,
                "keep_alive": "5m",
                "options": {
                    "temperature": 0,
                    "seed": 42,
                    "num_ctx": 2048,
                    "num_predict": 192,
                },
                "format": _schema(case["expected"]),
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                        + AREA_SYSTEM_PROMPTS.get(case["area"], ""),
                    },
                    {"role": "user", "content": case["prompt"]},
                ],
            }
            response = await _request(
                client,
                "POST",
                "/api/chat",
                min(cold_timeout if index == 0 else request_timeout, remaining),
                json=body,
            )
            content = response.get("message", {}).get("content", "")
            result["raw_response"] = content
            if response.get("done_reason") == "length":
                raise ValueError("Model output was truncated by the token limit.")
            actual = json.loads(content)
            score, checks = score_case(case, actual)
            result.update(actual=actual, score=score, checks=checks, passed=score == 1)
            result["timing"] = {
                key: response.get(key)
                for key in (
                    "total_duration",
                    "load_duration",
                    "prompt_eval_count",
                    "prompt_eval_duration",
                    "eval_count",
                    "eval_duration",
                )
            }
        except (
            TimeoutError,
            httpx.HTTPError,
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            result.update(
                status="timeout"
                if isinstance(exc, (TimeoutError, httpx.TimeoutException))
                else "error",
                score=0.0,
                passed=False,
                error=f"{type(exc).__name__}: {exc}"[:700],
            )
            if isinstance(exc, (TimeoutError, httpx.HTTPError)):
                circuit_reason = result["error"] or result["status"]
        result["latency_seconds"] = round(time.monotonic() - case_started, 3)
        results.append(result)
    areas = {
        area: _summarize_area(
            [result for result in results if result["area"] == area], area
        )
        for area in AREA_NAMES
    }
    successful = sum(result["status"] == "ok" for result in results)
    return {
        "model": model,
        "kind": "chat",
        "status": "healthy"
        if successful == len(cases)
        else "degraded"
        if successful
        else "unavailable",
        "failure_reason": circuit_reason,
        "duration_seconds": round(time.monotonic() - started, 3),
        "overall_score": round(
            statistics.mean(area["score"] for area in areas.values()), 4
        )
        if all(area["score"] is not None for area in areas.values())
        else None,
        "areas": areas,
    }


def validate_embeddings(vectors: Any, count: int) -> dict[str, Any]:
    if not isinstance(vectors, list) or len(vectors) != count:
        raise ValueError("Embedding batch count mismatch.")
    dimensions = len(vectors[0]) if isinstance(vectors[0], list) else 0
    if not dimensions or any(
        not isinstance(vector, list) or len(vector) != dimensions for vector in vectors
    ):
        raise ValueError("Embedding dimensions are empty or inconsistent.")
    if any(
        type(value) not in (int, float) or not math.isfinite(value)
        for vector in vectors
        for value in vector
    ):
        raise ValueError("Embedding vectors contain non-finite/non-numeric values.")
    norms = [math.sqrt(sum(value * value for value in vector)) for vector in vectors]
    if any(norm == 0 for norm in norms):
        raise ValueError("Embedding vectors must have nonzero norm.")
    cosine = lambda left, right: (
        sum(a * b for a, b in zip(vectors[left], vectors[right]))
        / (norms[left] * norms[right])
    )
    return {
        "dimensions": dimensions,
        "vector_count": count,
        "finite": True,
        "nonzero": True,
        "duplicate_cosine": round(cosine(0, 1), 6),
        "unrelated_cosine": round(cosine(0, 2), 6),
    }


async def _evaluate_embedding(
    client: httpx.AsyncClient, model: str, timeout: float
) -> dict[str, Any]:
    inputs = [
        "search_document: Python unit tests verify code behavior.",
        "search_document: Python unit tests verify code behavior.",
        "search_document: Orchids need water and indirect sunlight.",
        "search_document: Türkçe belgeler için anlamsal arama.",
    ]
    started = time.monotonic()
    try:
        response = await _request(
            client,
            "POST",
            "/api/embed",
            timeout,
            json={"model": model, "input": inputs, "keep_alive": "5m"},
        )
        checks = validate_embeddings(response.get("embeddings"), len(inputs))
        checks["duplicate_consistent"] = checks["duplicate_cosine"] > 0.999
        checks["distinct_input_differs"] = (
            checks["unrelated_cosine"] < checks["duplicate_cosine"] - 0.01
        )
        passed = checks["duplicate_consistent"] and checks["distinct_input_differs"]
        return {
            "model": model,
            "kind": "embedding",
            "status": "healthy" if passed else "degraded",
            "inputs": inputs,
            "checks": checks,
            "areas": {},
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": None,
        }
    except (TimeoutError, httpx.HTTPError, ValueError, TypeError) as exc:
        return {
            "model": model,
            "kind": "embedding",
            "status": "unavailable",
            "inputs": inputs,
            "areas": {},
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(exc).__name__}: {exc}"[:700],
        }


def build_preferences(report: dict[str, Any]) -> dict[str, Any]:
    profiles = {}
    for row in report["model_results"]:
        areas = {
            area: {key: value for key, value in details.items() if key != "results"}
            for area, details in row["areas"].items()
        }
        eligible = [area for area, details in areas.items() if details["eligible"]]
        load_durations = [
            result.get("timing", {}).get("load_duration")
            for details in row["areas"].values()
            for result in details["results"]
        ]
        load_seconds = max(
            (
                value / 1_000_000_000
                for value in load_durations
                if isinstance(value, (int, float))
            ),
            default=None,
        )
        if row["kind"] == "embedding":
            description = f"Embedding doğrulaması: {row['status']}; {row.get('checks', {}).get('dimensions', '?')} boyut. Sohbet model sıralamasına dahil değildir."
        else:
            description = f"Yerel ölçüm: {row['status']}. Eşik üstü alanlar: {', '.join(eligible) or 'yok'}."
        profiles[row["model"]] = {
            "kind": row["kind"],
            "status": row["status"],
            "description": description,
            "failure_reason": row.get("failure_reason") or row.get("error"),
            "areas": areas,
            "digest": row.get("digest"),
            "checks": row.get("checks"),
            "max_observed_load_seconds": round(load_seconds, 3)
            if load_seconds is not None
            else None,
        }
    priorities = {
        area: sorted(
            [
                name
                for name, profile in profiles.items()
                if profile["kind"] == "chat"
                and profile["status"] in {"healthy", "degraded"}
                and profile["areas"].get(area, {}).get("eligible")
            ],
            key=lambda name: (
                -profiles[name]["areas"][area]["score"],
                profiles[name]["areas"][area]["mean_latency_seconds"],
                name,
            ),
        )
        for area in AREA_NAMES
    }
    return {
        "version": 3,
        "generated_at": report.get("completed_at") or report["started_at"],
        "models_tested": report["models_tested"],
        "area_priorities": priorities,
        "area_descriptions": AREA_DESCRIPTIONS,
        "model_profiles": profiles,
        "scores": {
            name: {area: details["score"] for area, details in profile["areas"].items()}
            for name, profile in profiles.items()
            if profile["kind"] == "chat"
        },
        "source": "model_eval bounded local deterministic benchmark",
        "benchmark_report": report.get("report_path"),
        "note": report["note"],
        "ranking_policy": "Complete area, >=2 cases, zero request/parse errors, score >=0.5; score descending then mean latency ascending. Unattempted cases have null scores.",
    }


def rescore_report(report: dict[str, Any]) -> dict[str, Any]:
    """Recheck saved responses without inference, preserving telemetry and old scores."""
    if report.get("status") != "completed":
        raise ValueError("Only completed benchmark reports can be rescored.")
    cases = {case["id"]: case for case in report["cases"]}
    previous_scores = {
        row["model"]: {area: details["score"] for area, details in row["areas"].items()}
        for row in report["model_results"]
    }
    previous_version = report.get("scorer_version", 1)
    for row in report["model_results"]:
        if row["kind"] != "chat":
            continue
        for area, details in row["areas"].items():
            for result in details["results"]:
                if result["status"] == "ok":
                    score, checks = score_case(cases[result["id"]], result["actual"])
                    result.update(score=score, checks=checks, passed=score == 1)
            row["areas"][area] = _summarize_area(details["results"], area)
        scores = [area["score"] for area in row["areas"].values()]
        row["overall_score"] = (
            round(statistics.mean(scores), 4)
            if all(score is not None for score in scores)
            else None
        )
    report["scorer_version"] = SCORER_VERSION
    report.setdefault("scoring_history", []).append(
        {
            "rescored_at": _timestamp(),
            "previous_scorer_version": previous_version,
            "previous_scores": previous_scores,
            "reason": "AST comparison accepts equivalent exiting-guard else branches and reversed pure-name less-than comparisons; no generated code is executed.",
        }
    )
    report["priority_by_area"] = build_preferences(report)["area_priorities"]
    return report


def merge_reports(baseline: dict[str, Any], followup: dict[str, Any]) -> dict[str, Any]:
    """Replace retested areas, retaining untouched measurements and source-round paths."""
    if any(report.get("status") != "completed" for report in (baseline, followup)):
        raise ValueError("Both benchmark rounds must be complete.")
    if baseline["models_tested"] != followup["models_tested"]:
        raise ValueError(
            "Benchmark rounds must cover the same installed model inventory."
        )
    merged = copy.deepcopy(baseline)
    selected_areas = {case["area"] for case in followup["cases"]}
    merged["cases"] = [
        case for case in merged["cases"] if case["area"] not in selected_areas
    ] + copy.deepcopy(followup["cases"])
    followup_rows = {row["model"]: row for row in followup["model_results"]}
    for row in merged["model_results"]:
        replacement = followup_rows[row["model"]]
        if (
            row.get("digest") != replacement.get("digest")
            or row["kind"] != replacement["kind"]
        ):
            raise ValueError(
                "Model content/capability changed between rounds; a full retest is required."
            )
        total_duration = round(
            row["duration_seconds"] + replacement["duration_seconds"], 3
        )
        if row["kind"] != "chat":
            row.update(copy.deepcopy(replacement))
            row["duration_seconds"] = total_duration
            continue
        for area in selected_areas:
            row["areas"][area] = copy.deepcopy(replacement["areas"][area])
        results = [
            result for area in row["areas"].values() for result in area["results"]
        ]
        successful = sum(result["status"] == "ok" for result in results)
        row["status"] = (
            "healthy"
            if successful == len(results)
            else "degraded"
            if successful
            else "unavailable"
        )
        row["duration_seconds"] = total_duration
        row["failure_reason"] = next(
            (result["error"] for result in results if result["error"]), None
        )
    merged["completed_at"] = followup["completed_at"]
    merged["prompt_version"] = followup.get("prompt_version")
    merged["system_prompts"] = followup.get("system_prompts")
    merged["measurement_rounds"] = [
        {
            "report_path": report.get("report_path"),
            "started_at": report["started_at"],
            "completed_at": report["completed_at"],
            "settings": report["settings"],
            "areas": sorted({case["area"] for case in report["cases"]}),
        }
        for report in (baseline, followup)
    ]
    merged["note"] = (
        followup["note"]
        + " Intent/memory prompts were clarified to match the production taxonomy; "
        "only those areas were retested for every model. Original rounds remain available."
    )
    return rescore_report(merged)


async def evaluate_models(
    models: list[str] | None = None,
    limit: int | None = None,
    *,
    base_url: str | None = None,
    request_timeout: float = 30,
    cold_timeout: float = 75,
    model_timeout: float = 360,
    report_path: Path | None = None,
    areas: list[str] | None = None,
) -> dict[str, Any]:
    if min(request_timeout, cold_timeout, model_timeout) <= 0:
        raise ValueError("Timeouts must be positive.")
    cases = load_benchmark_cases()
    if areas is not None:
        if not areas or any(area not in AREA_NAMES for area in areas):
            raise ValueError("Selected areas must be known benchmark areas.")
        cases = [case for case in cases if case["area"] in areas]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        cases = [
            case
            for area in AREA_NAMES
            for case in [item for item in cases if item["area"] == area][:limit]
        ]
    url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435")).rstrip(
        "/"
    )
    if httpx.URL(url).host not in {
        "127.0.0.1",
        "localhost",
        "::1",
        "ollama",
        "host.docker.internal",
    }:
        raise ValueError("Benchmark only allows a local Ollama endpoint.")
    async with httpx.AsyncClient(base_url=url, trust_env=False) as client:
        catalog = await _request(client, "GET", "/api/tags", 10)
        installed = {
            item["name"]: item
            for item in catalog.get("models", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        selected = list(dict.fromkeys(models if models is not None else installed))
        if not selected or any(name not in installed for name in selected):
            raise ValueError(
                "Only installed model names can be evaluated; no downloads are performed."
            )
        if any(name.casefold().endswith((":cloud", "-cloud")) for name in selected):
            raise ValueError("Cloud models cannot be benchmarked.")
        report: dict[str, Any] = {
            "version": 3,
            "scorer_version": SCORER_VERSION,
            "prompt_version": 2,
            "system_prompts": {
                area: SYSTEM_PROMPT + AREA_SYSTEM_PROMPTS.get(area, "")
                for area in AREA_NAMES
            },
            "started_at": _timestamp(),
            "status": "running",
            "base_url": url,
            "report_path": str(report_path) if report_path else None,
            "models_tested": selected,
            "settings": {
                "request_timeout_seconds": request_timeout,
                "cold_timeout_seconds": cold_timeout,
                "model_timeout_seconds": model_timeout,
                "temperature": 0,
                "seed": 42,
                "num_ctx": 2048,
                "num_predict": 192,
                "think": False,
                "serial_inference": True,
            },
            "cases_sha256": hashlib.sha256(
                BENCHMARK_CASES_PATH.read_bytes()
            ).hexdigest(),
            "cases": cases,
            "areas": list(AREA_NAMES),
            "inventory": list(installed.values()),
            "model_results": [],
            "note": "Small fixed JSON/AST fixtures, one run per case; scores are not general intelligence, open conversation, production tool-use, or safety guarantees. The first case includes a cold model load; later cases are warm. No generated code is executed. Null scores mean untested; timeouts are hardware/budget specific.",
        }
        _write_report(report_path, report)
        loaded = await _request(client, "GET", "/api/ps", 10)
        for item in loaded.get("models", []):
            await _unload(client, item["name"], 20)
        for model in selected:
            print(f"Evaluating {model}", flush=True)
            started = time.monotonic()
            try:
                details = await _request(
                    client, "POST", "/api/show", 10, json={"model": model}
                )
                capabilities = details.get("capabilities", [])
                if details.get("remote_host") or details.get("remote_model"):
                    raise ValueError("Remote-backed models cannot be benchmarked.")
                if "embedding" in capabilities and "completion" not in capabilities:
                    row = await _evaluate_embedding(client, model, cold_timeout)
                elif "completion" in capabilities:
                    row = await _evaluate_chat(
                        client,
                        model,
                        cases,
                        request_timeout,
                        cold_timeout,
                        model_timeout,
                    )
                else:
                    raise ValueError(f"Unsupported capabilities: {capabilities}")
                row["capabilities"] = capabilities
            except (TimeoutError, httpx.HTTPError, ValueError, TypeError) as exc:
                row = {
                    "model": model,
                    "kind": "unknown",
                    "status": "unavailable",
                    "areas": {},
                    "error": f"{type(exc).__name__}: {exc}"[:700],
                    "duration_seconds": round(time.monotonic() - started, 3),
                }
            row["digest"] = installed[model].get("digest")
            report["model_results"].append(row)
            _write_report(report_path, report)
            try:
                await _unload(client, model, 20)
                row["unload_status"] = "ok"
            except (TimeoutError, httpx.HTTPError, ValueError, TypeError) as exc:
                row["unload_status"] = f"{type(exc).__name__}: {exc}"
                report["status"] = "aborted_unload_failed"
                _write_report(report_path, report)
                raise RuntimeError(
                    f"Cannot confirm {model} was unloaded; stopped to avoid concurrent heavy inference."
                ) from exc
            print(
                f"Finished {model}: {row['status']}, {row['duration_seconds']}s",
                flush=True,
            )
            _write_report(report_path, report)
        report.update(status="completed", completed_at=_timestamp())
        report["priority_by_area"] = build_preferences(report)["area_priorities"]
        _write_report(report_path, report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequential, bounded evaluation of every installed local chat/embedding model."
    )
    parser.add_argument("--model", action="append")
    parser.add_argument(
        "--area",
        action="append",
        choices=AREA_NAMES,
        help="Evaluate only selected areas; partial runs do not replace routing preferences.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="First N cases per area; N=1 never produces eligible rankings.",
    )
    parser.add_argument("--base-url")
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument("--cold-timeout", type=float, default=75)
    parser.add_argument("--model-timeout", type=float, default=360)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "model-evaluations" / "latest.json",
    )
    parser.add_argument("--routing-output", type=Path)
    parser.add_argument(
        "--rescore-report",
        type=Path,
        help="Recheck a completed saved report with the current scorer, without model calls.",
    )
    parser.add_argument(
        "--merge-baseline",
        type=Path,
        help="Merge the selected-area --rescore-report into this complete saved baseline; no inference.",
    )
    args = parser.parse_args()
    try:
        if args.rescore_report:
            saved = json.loads(args.rescore_report.read_text(encoding="utf-8"))
            report = (
                merge_reports(
                    json.loads(args.merge_baseline.read_text(encoding="utf-8")), saved
                )
                if args.merge_baseline
                else rescore_report(saved)
            )
            report["report_path"] = str(args.output)
            _write_report(args.output, report)
        else:
            if args.merge_baseline:
                raise ValueError("--merge-baseline requires --rescore-report.")
            report = asyncio.run(
                evaluate_models(
                    args.model,
                    args.limit,
                    base_url=args.base_url,
                    request_timeout=args.request_timeout,
                    cold_timeout=args.cold_timeout,
                    model_timeout=args.model_timeout,
                    report_path=args.output,
                    areas=args.area,
                )
            )
        if args.routing_output:
            preferences = build_preferences(report)
            if not all(preferences["area_priorities"].values()):
                raise ValueError(
                    "Not every area has a usable measured candidate; existing routing file was preserved."
                )
            _write_report(args.routing_output, preferences)
    except (OSError, ValueError, TypeError, RuntimeError, httpx.HTTPError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "report": str(args.output),
                "status": report["status"],
                "priorities": report["priority_by_area"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
