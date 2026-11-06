from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.plugins.gateway import PluginGateway
from app.plugins.intent_router import IntentRouterPlugin
from app.plugins.ollama import OllamaPlugin

DEFAULT_CASES_PATH = Path(__file__).with_name("intent_eval_cases.json")
CONFIDENCE_BINS = 5


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else None
    labels = set(IntentRouterPlugin.intents)
    if not isinstance(cases, list) or not cases:
        raise ValueError("Evaluation file must contain a non-empty cases list.")
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] must be an object.")
        case_id = case.get("id")
        expected = case.get("expected")
        text = case.get("text")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError(f"cases[{index}].id must be unique non-empty text.")
        if expected not in labels:
            raise ValueError(f"cases[{index}].expected must be one of {sorted(labels)}.")
        if not isinstance(text, str) or not text.strip() or len(text) > IntentRouterPlugin.max_message_length:
            raise ValueError(f"cases[{index}].text must be non-empty text within the router limit.")
        seen_ids.add(case_id)
        normalized.append({"id": case_id, "expected": expected, "text": text})
    return normalized


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def score_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        raise ValueError("At least one evaluation result is required.")

    labels = list(IntentRouterPlugin.intents)
    columns = [*labels, "error"]
    confusion = {label: {column: 0 for column in columns} for label in labels}
    correct_count = 0
    confidences: list[tuple[float, bool]] = []
    per_intent: dict[str, dict[str, float | int]] = {}

    for result in results:
        expected = result["expected"]
        actual = result.get("actual")
        column = actual if actual in labels else "error"
        confusion[expected][column] += 1
        correct = actual == expected
        correct_count += int(correct)
        confidence = result.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            confidences.append((float(confidence), correct))

    class_f1: list[float] = []
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[other][label] for other in labels if other != label)
        false_negative = sum(confusion[label][other] for other in columns if other != label)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = _f1(precision, recall)
        class_f1.append(f1)
        per_intent[label] = {
            "support": sum(confusion[label].values()),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    bin_summaries = []
    ece = 0.0
    for bin_index in range(CONFIDENCE_BINS):
        lower = bin_index / CONFIDENCE_BINS
        upper = (bin_index + 1) / CONFIDENCE_BINS
        members = [
            item for item in confidences
            if lower <= item[0] and (item[0] < upper or bin_index == CONFIDENCE_BINS - 1 and item[0] <= upper)
        ]
        mean_confidence = sum(item[0] for item in members) / len(members) if members else 0.0
        accuracy = sum(item[1] for item in members) / len(members) if members else 0.0
        ece += len(members) / len(confidences) * abs(mean_confidence - accuracy) if confidences else 0.0
        bin_summaries.append({
            "range": [round(lower, 2), round(upper, 2)],
            "count": len(members),
            "mean_confidence": round(mean_confidence, 4),
            "accuracy": round(accuracy, 4),
        })

    brier_score = (
        sum((confidence - float(correct)) ** 2 for confidence, correct in confidences) / len(confidences)
        if confidences else None
    )
    return {
        "case_count": len(results),
        "successful_count": len(confidences),
        "error_count": sum(1 for result in results if result.get("actual") not in labels),
        "accuracy": round(correct_count / len(results), 4),
        "macro_f1": round(sum(class_f1) / len(class_f1), 4),
        "mean_confidence": round(sum(item[0] for item in confidences) / len(confidences), 4) if confidences else None,
        "brier_score": round(brier_score, 4) if brier_score is not None else None,
        "expected_calibration_error": round(ece, 4) if confidences else None,
        "per_intent": per_intent,
        "confusion_matrix": {"columns": columns, "rows": confusion},
        "confidence_bins": bin_summaries,
    }


async def evaluate(
    cases: list[dict[str, str]], model: str | None = None
) -> dict[str, Any]:
    gateway = PluginGateway()
    ollama = OllamaPlugin()
    gateway.register(ollama)
    router = IntentRouterPlugin(gateway)
    results: list[dict[str, Any]] = []
    for case in cases:
        try:
            routed = await router.invoke("route", {"message": case["text"], "model": model})
            results.append({
                "id": case["id"],
                "expected": case["expected"],
                "actual": routed["intent"],
                "confidence": routed["confidence"],
                "rationale": routed["rationale"],
                "correct": routed["intent"] == case["expected"],
                "learning_proposal_present": routed["learning_proposal"] is not None,
                "error": None,
            })
        except Exception as exc:
            results.append({
                "id": case["id"],
                "expected": case["expected"],
                "actual": None,
                "confidence": None,
                "rationale": "",
                "correct": False,
                "learning_proposal_present": False,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return {
        "model": model or ollama.default_model,
        "metrics": score_results(results),
        "results": results,
        "note": "Small fixed benchmark; confidence metrics are diagnostic, not a statistical guarantee.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the local intent router without saving or executing actions.")
    parser.add_argument("--model", help="Installed local Ollama chat model; defaults to the configured model.")
    parser.add_argument("--limit", type=int, help="Run only the first N cases for a quick smoke test.")
    parser.add_argument("--output", type=Path, help="Optional path for a JSON report; stdout is used by default.")
    parser.add_argument("--min-accuracy", type=float, help="Exit with code 1 if accuracy is below this value.")
    args = parser.parse_args()
    try:
        cases = load_cases()
        if args.limit is not None:
            if args.limit < 1:
                raise ValueError("--limit must be at least 1.")
            cases = cases[:args.limit]
        if args.min_accuracy is not None and not 0 <= args.min_accuracy <= 1:
            raise ValueError("--min-accuracy must be between 0 and 1.")
        report = asyncio.run(evaluate(cases, args.model))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if args.min_accuracy is not None and report["metrics"]["accuracy"] < args.min_accuracy:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())