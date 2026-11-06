from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.worker_lifecycle import (
    drain_registered_workers,
    persist_cancellation,
    run_thread,
    start_worker,
)

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class EvaluationApprovalRequired(Exception):
    pass


class EvaluationPlugin:
    manifest = PluginManifest(
        plugin_id="evaluation",
        display_name="Evaluation Runner",
        description="Birim testlerini, niyet yönlendirici ve model kalite ölçümlerini onaylı arka plan işleri olarak çalıştırır.",
        actions=("suites", "run", "reports", "resume_job"),
    )

    suites: ClassVar[dict[str, str]] = {
        "unit_tests": "Backend birim testleri (unittest).",
        "intent": "Niyet yönlendirici doğruluk ölçümü (Ollama gerekir).",
        "models": "Kurulu yerel modellerin alan bazlı kalite karşılaştırması (Ollama gerekir).",
    }
    max_output_chars: ClassVar[int] = 20_000
    max_reports: ClassVar[int] = 50

    def __init__(self, gateway: PluginGateway, reports_dir: str | Path | None = None, backend_root: str | Path | None = None) -> None:
        self.gateway = gateway
        if reports_dir is None:
            reports_dir = Path(os.getenv("AI_DATA_DIR", "/data")).expanduser() / "evaluations"
        self.reports_dir = Path(reports_dir).expanduser().resolve()
        self.backend_root = Path(backend_root).resolve() if backend_root else self._find_backend_root()
        self.timeout_seconds = max(30, int(os.getenv("EVALUATION_TIMEOUT_SECONDS", "1800")))
        self.worker_id = f"evaluation-{uuid.uuid4().hex[:12]}"
        self._workers: set[asyncio.Task[None]] = set()

    async def drain_workers(self) -> None:
        await drain_registered_workers(self._workers)

    @staticmethod
    def _find_backend_root() -> Path:
        local = Path(__file__).resolve().parents[2]
        if (local / "tests").is_dir():
            return local
        return Path(os.getenv("DIAGNOSTICS_ROOT", "/workspace")).expanduser().resolve() / "backend"

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "suites":
            return {
                "suites": [{"id": key, "description": value} for key, value in self.suites.items()],
                "tests_available": (self.backend_root / "tests").is_dir(),
            }
        if action == "run":
            return await self._run(payload)
        if action == "resume_job":
            return await self._resume_job(payload)
        if action == "reports":
            return self._reports(payload)
        raise ValueError(f"Unsupported evaluation action: {action}")

    async def _run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise EvaluationApprovalRequired("Running an evaluation requires approved=true.")
        suite = payload.get("suite")
        if suite not in self.suites:
            raise ValueError(f"suite must be one of: {', '.join(self.suites)}.")
        limit = payload.get("limit")
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500):
            raise ValueError("limit must be an integer from 1 to 500.")
        model = payload.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 200):
            raise ValueError("model must be a non-empty string up to 200 characters.")
        if suite == "unit_tests" and not (self.backend_root / "tests").is_dir():
            raise ValueError("Backend tests directory was not found.")
        job = await self.gateway.invoke(
            "jobs", "create", {"approved": True, "kind": "evaluation", "input": {"suite": suite, "limit": limit, "model": model}},
        )
        started = await self._resume_job({"approved": True, "job_id": job["job_id"]})
        return {**started, "suite": suite}

    async def _resume_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise EvaluationApprovalRequired("Resuming an evaluation requires approved=true.")
        job = (await self.gateway.invoke("jobs", "get", {"job_id": payload.get("job_id")}))["job"]
        if job["kind"] != "evaluation" or job["status"] != "queued":
            raise ValueError("Only queued evaluation jobs can be resumed.")
        data = job["input"]
        suite, limit, model = data.get("suite"), data.get("limit"), data.get("model")
        if suite not in self.suites:
            raise ValueError("Stored evaluation suite is invalid.")
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500):
            raise ValueError("Stored evaluation limit is invalid.")
        if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 200):
            raise ValueError("Stored evaluation model is invalid.")
        await self.gateway.invoke("jobs", "claim", {"job_id": job["job_id"], "worker_id": self.worker_id})
        start_worker(
            partial(self._worker, job["job_id"], suite, limit, model, claimed=True),
            self._workers, self.gateway, {"job_id": job["job_id"], "worker_id": self.worker_id},
            logger, f"evaluation-{job['job_id']}",
        )
        return {"job_id": job["job_id"], "status": "running"}

    async def _worker(self, job_id: str, suite: str, limit: int | None, model: str | None, claimed: bool = False) -> None:
        worker = {"job_id": job_id, "worker_id": self.worker_id}
        try:
            if not claimed:
                await self.gateway.invoke("jobs", "claim", worker)
            update = await self.gateway.invoke("jobs", "progress", {**worker, "progress": 5, "message": f"{suite} çalışıyor."})
            if update["status"] == "cancelled":
                return
            if suite == "unit_tests":
                report = await run_thread(self._unit_tests, logger)
            elif suite == "intent":
                from app.intent_eval import evaluate, load_cases

                cases = load_cases()
                report = await asyncio.wait_for(evaluate(cases[:limit] if limit else cases, model), self.timeout_seconds)
            else:
                from app.model_eval import evaluate_models

                report = await asyncio.wait_for(evaluate_models([model] if model else None, limit), self.timeout_seconds)
            update = await self.gateway.invoke(
                "jobs", "progress", {**worker, "progress": 90, "message": "Değerlendirme raporu kaydediliyor."},
            )
            if update["status"] == "cancelled":
                return
            summary = self._save_report(suite, job_id, report)
            await self.gateway.invoke("jobs", "complete", {**worker, "result": summary})
        except asyncio.CancelledError:
            await persist_cancellation(self.gateway, worker, logger)
            raise
        except Exception as exc:
            try:
                await self.gateway.invoke("jobs", "fail", {**worker, "error": str(exc)[:2_000] or exc.__class__.__name__})
            except Exception:
                logger.exception("Could not persist evaluation job failure for %s.", job_id)

    def _unit_tests(self) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                cwd=self.backend_root, capture_output=True, text=True, timeout=self.timeout_seconds, check=False, shell=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except subprocess.TimeoutExpired:
            return {"passed": False, "returncode": None, "output": "Test suite timed out."}
        output = (completed.stdout + completed.stderr)[-self.max_output_chars:]
        summary_line = next((line for line in reversed(output.splitlines()) if line.startswith(("Ran ", "OK", "FAILED"))), "")
        return {"passed": completed.returncode == 0, "returncode": completed.returncode, "summary": summary_line, "output": output}

    def _save_report(self, suite: str, job_id: str, report: dict[str, Any]) -> dict[str, Any]:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        report_id = f"{created_at.replace(':', '').replace('-', '')[:15]}-{suite}-{job_id[:8]}"
        path = self.reports_dir / f"{report_id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"suite": suite, "job_id": job_id, "created_at": created_at, "report": report}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        for old in sorted(self.reports_dir.glob("*.json"))[:-self.max_reports]:
            old.unlink(missing_ok=True)
        return {"report_id": report_id, "suite": suite, "created_at": created_at, "highlights": self._highlights(suite, report)}

    @staticmethod
    def _highlights(suite: str, report: dict[str, Any]) -> dict[str, Any]:
        if suite == "unit_tests":
            return {"passed": report.get("passed"), "summary": report.get("summary", "")}
        if suite == "intent":
            metrics = report.get("metrics", {})
            return {"model": report.get("model"), "accuracy": metrics.get("accuracy"), "total": metrics.get("case_count")}
        return {"models_tested": report.get("models_tested", []), "overall_ranking": report.get("overall_ranking", [])}

    def _reports(self, payload: dict[str, Any]) -> dict[str, Any]:
        report_id = payload.get("report_id")
        if report_id is not None:
            if not isinstance(report_id, str) or not report_id or "/" in report_id or "\\" in report_id or ".." in report_id:
                raise ValueError("report_id is invalid.")
            path = self.reports_dir / f"{report_id}.json"
            if not path.is_file():
                raise ValueError("Evaluation report was not found.")
            return json.loads(path.read_text(encoding="utf-8"))
        items = []
        skipped_reports: list[str] = []
        if self.reports_dir.is_dir():
            for path in sorted(self.reports_dir.glob("*.json"), reverse=True)[:self.max_reports]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    logger.exception("Could not read evaluation report %s.", path.name)
                    skipped_reports.append(path.stem)
                    continue
                if (
                    not isinstance(data, dict)
                    or not isinstance(data.get("suite"), str)
                    or not isinstance(data.get("report", {}), dict)
                ):
                    logger.warning("Evaluation report %s has an invalid structure.", path.name)
                    skipped_reports.append(path.stem)
                    continue
                items.append({
                    "report_id": path.stem, "suite": data.get("suite"), "created_at": data.get("created_at"),
                    "highlights": self._highlights(str(data.get("suite")), data.get("report", {})),
                })
        return {"reports": items, "skipped_reports": skipped_reports}
