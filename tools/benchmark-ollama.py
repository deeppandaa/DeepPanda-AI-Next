from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def request(base_url: str, route: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url + route, data=data, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure local Ollama inference, not Tensor Core unlock.")
    parser.add_argument("--label", required=True, choices=("cpu", "gpu"))
    parser.add_argument("--base-url", default="http://127.0.0.1:11435")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    args = parser.parse_args()
    if args.base_url != "http://127.0.0.1:11435":
        parser.error("Only this project's loopback Ollama endpoint is allowed.")
    installed = request(args.base_url, "/api/tags")["models"]
    catalog = next(item for item in installed if item["name"] == args.model)
    if args.model.casefold().endswith((":cloud", "-cloud")):
        parser.error("Only installed local models are allowed.")
    body = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": "Answer accurately and concisely."},
            {"role": "user", "content": "Write a Python function sum_even(values) that sums even integers, "
             "and show three assert tests. Output only Python code."},
        ],
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": 0, "seed": 42, "num_predict": 128, "num_ctx": 4096},
    }
    request(args.base_url, "/api/chat", body)
    results = []
    for _ in range(3):
        start = time.monotonic()
        response = request(args.base_url, "/api/chat", body)
        if response.get("done") is not True or not response.get("message", {}).get("content", "").strip():
            raise RuntimeError("Ollama did not complete a non-empty response.")
        duration = response["eval_duration"] / 1e9
        if duration <= 0 or response["eval_count"] <= 0:
            raise RuntimeError("Ollama returned invalid generation metrics.")
        loaded = request(args.base_url, "/api/ps")["models"]
        model = next(item for item in loaded if item["name"] == args.model)
        if args.label == "gpu" and model.get("size_vram", 0) <= 0:
            raise RuntimeError("GPU benchmark requested, but the model has no GPU allocation.")
        if args.label == "cpu" and model.get("size_vram", 0) != 0:
            raise RuntimeError("CPU baseline requested, but the model is using VRAM.")
        results.append({
            "wall_seconds": round(time.monotonic() - start, 3),
            "eval_count": response["eval_count"],
            "tokens_per_second": round(response["eval_count"] / duration, 3),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "size_vram": model.get("size_vram", 0),
            "response": response["message"]["content"],
        })
    report = {
        "label": args.label, "model": args.model, "digest": catalog["digest"],
        "options": body["options"], "prompt": body["messages"],
        "runs": results,
        "median_tokens_per_second": statistics.median(item["tokens_per_second"] for item in results),
        "scope": "Three warmed runs; CPU/GPU comparison, not unlock off/on.",
    }
    target = ROOT / "data" / "model-evaluations" / f"2026-11-10-ollama-{args.label}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "runs"}, indent=2))
    print(f"Report: {target}")


if __name__ == "__main__":
    main()
