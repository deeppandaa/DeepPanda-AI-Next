from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class ApiError(Exception):
    def __init__(self, status: int, detail: str, body: Any = None) -> None:
        super().__init__(f"{status}: {detail}" if status else detail)
        self.status = status
        self.detail = detail
        self.body = body

    @property
    def needs_approval(self) -> bool:
        return self.status == 403


class ApiClient:
    """Small synchronous client for the DeepPanda FastAPI backend; always called from worker threads."""

    def __init__(self, base_url: str, timeout: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, *, json_body: Any = None, timeout: float | None = None) -> Any:
        try:
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(timeout or self.timeout, connect=5.0)) as client:
                response = client.request(method, path, json=json_body)
        except httpx.HTTPError as exc:
            raise ApiError(0, f"API'ye ulaşılamıyor ({self.base_url}): {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = response.text
        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body
            if not isinstance(detail, str):
                detail = str(detail)
            raise ApiError(response.status_code, detail or response.reason_phrase, body)
        return body

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health", timeout=5)

    def plugins(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/plugins", timeout=15)

    def action(self, plugin: str, action: str, payload: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        return self._request(
            "POST",
            f"/api/plugins/{quote(plugin, safe='')}/actions/{quote(action, safe='')}",
            json_body={"payload": payload or {}},
            timeout=timeout,
        )

    def models(self) -> dict[str, Any]:
        return self._request("GET", "/api/plugins/ollama/models", timeout=20)

    def chat(self, message: str, model: str | None, workflow: str, session_id: str | None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/chat",
            json_body={"message": message, "model": model, "workflow": workflow, "session_id": session_id},
        )

    def sessions(self, limit: int = 50) -> dict[str, Any]:
        return self._request("GET", f"/api/chat/sessions?limit={limit}", timeout=15)

    def create_session(self, title: str) -> dict[str, Any]:
        return self._request("POST", "/api/chat/sessions", json_body={"title": title[:200] or "Yeni sohbet"})

    def session_messages(self, session_id: str, limit: int = 200) -> dict[str, Any]:
        return self._request("GET", f"/api/chat/sessions/{quote(session_id, safe='')}/messages?limit={limit}", timeout=15)

    def delete_session(self, session_id: str, approved: bool) -> dict[str, Any]:
        return self._request("DELETE", f"/api/chat/sessions/{quote(session_id, safe='')}", json_body={"approved": approved})

    def draft_task(self, request: str, model: str | None) -> dict[str, Any]:
        return self._request("POST", "/api/tasks/draft", json_body={"request": request, "model": model})

    def diagnostics_scan(self) -> dict[str, Any]:
        return self._request("POST", "/api/plugins/diagnostics/scan")

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"
