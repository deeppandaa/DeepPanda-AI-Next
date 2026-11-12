from __future__ import annotations

import json
from collections.abc import Callable
from threading import Event
from typing import Any
from urllib.parse import quote

import httpx

# Model catalog + five sequential 600s stages, or a 7200s model pull, with response headroom.
ACTION_TIMEOUTS = {("multi_agent", "run"): 3660.0, ("ollama", "pull"): 7260.0}


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
        request_timeout = self.timeout if timeout is None else timeout
        try:
            with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(request_timeout, connect=5.0)) as client:
                response = client.request(method, path, json=json_body)
        except httpx.ConnectTimeout as exc:
            raise ApiError(
                0, f"API bağlantısı 5 saniyede kurulamadı ({self.base_url}). Servis durumunu ve bağlantı izinlerini kontrol edin."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ApiError(
                0,
                f"API isteği zaman aşımına uğradı ({request_timeout:g} sn). "
                "Sunucudaki işlem devam ediyor olabilir; yeniden göndermeden önce durumunu kontrol edin.",
            ) from exc
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
        if timeout is None:
            timeout = max(self.timeout, ACTION_TIMEOUTS.get((plugin, action), 0))
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

    def analyze_attachments(self, files: list[dict[str, str]], approved: bool = False) -> dict[str, Any]:
        return self._request(
            "POST", "/api/chat/attachments/analyze",
            json_body={"files": files, "approved": approved},
        )

    def plan_tool(
        self, message: str, tools: list[dict[str, Any]], context: str, model: str | None,
    ) -> dict[str, Any]:
        return self._request(
            "POST", "/api/chat/tool-plan",
            json_body={"message": message, "tools": tools, "context": context, "model": model},
        )

    def stream_chat(
        self, payload: dict[str, Any], cancelled: Event, on_event: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        from desktop.chat_context import check_cancelled

        check_cancelled(cancelled)
        try:
            with httpx.Client(
                base_url=self.base_url, timeout=httpx.Timeout(self.timeout, connect=5.0),
            ) as client, client.stream("POST", "/api/chat/stream", json=payload) as response:
                if response.status_code >= 400:
                    response.read()
                    try:
                        body = response.json()
                    except ValueError:
                        body = {"detail": response.text}
                    detail = body.get("detail", response.reason_phrase) if isinstance(body, dict) else body
                    raise ApiError(response.status_code, str(detail), body)
                for line in response.iter_lines():
                    check_cancelled(cancelled)
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError as exc:
                        raise ApiError(502, "Sohbet akışı geçerli JSON döndürmedi.") from exc
                    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                        raise ApiError(502, "Sohbet akışı geçersiz bir olay döndürdü.")
                    if event["type"] not in {"progress", "token", "result", "error", "heartbeat"}:
                        raise ApiError(502, "Sohbet akışı bilinmeyen bir olay döndürdü.")
                    if event["type"] == "token" and not isinstance(event.get("content"), str):
                        raise ApiError(502, "Sohbet akışındaki metin parçası geçersiz.")
                    if event["type"] == "error":
                        status = event.get("status", 502)
                        if isinstance(status, bool) or not isinstance(status, int):
                            raise ApiError(502, "Sohbet akışındaki hata durumu geçersiz.")
                        raise ApiError(status, str(event.get("detail", "Sohbet hatası")), event.get("body"))
                    if event["type"] == "result":
                        result = event.get("result")
                        if not isinstance(result, dict):
                            raise ApiError(502, "Sohbet akışında sonuç eksik.")
                        return result
                    on_event(event)
        except httpx.TimeoutException as exc:
            raise ApiError(0, "Sohbet akışı zaman aşımına uğradı; otomatik tekrar yapılmadı.") from exc
        except httpx.HTTPError as exc:
            raise ApiError(0, f"Sohbet akışı kesildi: {exc}") from exc
        check_cancelled(cancelled)
        raise ApiError(502, "Sohbet akışı sonuç vermeden kapandı.")

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
