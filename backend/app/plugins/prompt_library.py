from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import tempfile
from functools import partial
from pathlib import Path
from typing import Any

import httpx

from app.plugins.contracts import PluginManifest
from app.plugins.worker_lifecycle import run_thread

CSV_URL = "https://raw.githubusercontent.com/f/prompts.chat/main/prompts.csv"
MCP_URL = "https://prompts.chat/api/mcp"
MAX_BYTES = 20_000_000
MAX_PROMPT = 20_000
logger = logging.getLogger(__name__)


class PromptApprovalRequired(Exception):
    pass


class PromptLibraryError(Exception):
    pass


class PromptLibraryPlugin:
    manifest = PluginManifest(
        "prompt_library", "Prompt library", "Yerel ve açık onaylı prompts.chat şablonları.",
        ("sync", "local_search", "online_search", "online_get"),
    )

    def __init__(self, data_dir: str | Path | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.path = Path(data_dir or os.getenv("AI_DATA_DIR", "/data")) / "prompt-library.json"
        self.transport = transport
        self.lock = asyncio.Lock()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "sync":
            self._approve(payload)
            async with self.lock:
                data = await self._download("GET", CSV_URL)
                return await run_thread(partial(self._save_catalog, data), logger)
        if action == "local_search":
            query = self._query(payload, allow_empty=True)
            async with self.lock:
                return await run_thread(partial(self._search_local, query), logger)
        if action == "online_search":
            query = self._query(payload)
            self._approve(payload)
            result = await self._mcp("search_prompts", {"query": query, "limit": 10, "type": "TEXT"})
            raw = result.get("prompts")
            if not isinstance(raw, list) or len(raw) > 10:
                raise PromptLibraryError("prompts.chat arama yanıtı geçersiz.")
            prompts = []
            for item in raw:
                if not isinstance(item, dict):
                    raise PromptLibraryError("prompts.chat arama kaydı geçersiz.")
                if item.get("type") != "TEXT":
                    raise PromptLibraryError("prompts.chat metin dışı bir sonuç döndürdü.")
                identifier, title, preview = item.get("id"), item.get("title"), item.get("contentPreview")
                if not all(isinstance(value, str) for value in (identifier, title, preview)):
                    raise PromptLibraryError("prompts.chat arama kaydı eksik.")
                if not identifier or len(identifier) > 200 or len(title) > 500 or len(preview) > MAX_PROMPT:
                    raise PromptLibraryError("prompts.chat arama kaydı sınırları aşıyor.")
                prompts.append({"id": identifier, "title": title, "content": preview, "preview": True})
            return {"prompts": prompts, "source": "online"}
        if action == "online_get":
            identifier = payload.get("id")
            if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
                raise ValueError("Şablon kimliği geçersiz.")
            self._approve(payload)
            result = await self._mcp("get_prompt", {"id": identifier})
            title, content = result.get("title"), result.get("content")
            if result.get("id") != identifier or result.get("type") != "TEXT":
                raise PromptLibraryError("prompts.chat farklı bir şablon veya metin dışı içerik döndürdü.")
            if not isinstance(title, str) or not isinstance(content, str) or not content:
                raise PromptLibraryError("prompts.chat şablon yanıtı geçersiz.")
            if len(title) > 500 or len(content) > MAX_PROMPT:
                raise PromptLibraryError("Şablon sohbetin 20.000 karakter sınırını aşıyor.")
            return {"prompt": {"id": identifier, "title": title, "content": content}, "source": "online"}
        raise ValueError("Bilinmeyen şablon işlemi.")

    @staticmethod
    def _approve(payload: dict[str, Any]) -> None:
        if payload.get("approved") is not True:
            raise PromptApprovalRequired("Harici istek için açık onay gerekir.")

    @staticmethod
    def _query(payload: dict[str, Any], allow_empty: bool = False) -> str:
        query = payload.get("query", "")
        if not isinstance(query, str) or len(query) > 200 or (not allow_empty and not query.strip()):
            raise ValueError("Arama metni en fazla 200 karakter olmalı ve çevrim içi aramada boş olmamalı.")
        return query.strip()

    async def _download(self, method: str, url: str, payload: dict[str, Any] | None = None) -> bytes:
        try:
            async with httpx.AsyncClient(
                timeout=30, follow_redirects=False, trust_env=False, transport=self.transport
            ) as client, client.stream(
                method, url, json=payload, headers={"Accept": "application/json, text/event-stream"}
            ) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(data) + len(chunk) > MAX_BYTES:
                        raise PromptLibraryError("Uzak yanıt 20 MB sınırını aşıyor.")
                    data.extend(chunk)
                return bytes(data)
        except httpx.HTTPError as exc:
            raise PromptLibraryError(f"prompts.chat bağlantısı başarısız: {type(exc).__name__}") from exc

    async def _mcp(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        data = await self._download("POST", MCP_URL, {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        })
        try:
            response = json.loads(data)
            result = response["result"]
            if not isinstance(response, dict) or not isinstance(result, dict):
                raise TypeError("Invalid MCP response")
            structured = result["structuredContent"]
            if response.get("id") != 1 or response.get("jsonrpc") != "2.0" or result.get("isError"):
                raise ValueError("MCP error")
            if not isinstance(structured, dict):
                raise TypeError("Invalid MCP result")
        except (ValueError, KeyError, TypeError) as exc:
            raise PromptLibraryError("prompts.chat geçersiz veya başarısız MCP yanıtı döndürdü.") from exc
        return structured

    def _save_catalog(self, data: bytes) -> dict[str, Any]:
        try:
            text = data.decode("utf-8-sig")
            # The public CSV contains fields larger than Python's default field limit.
            previous_limit = csv.field_size_limit()
            csv.field_size_limit(MAX_BYTES)
            try:
                reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
                if not reader.fieldnames or not {"act", "prompt", "type"}.issubset(reader.fieldnames):
                    raise ValueError("CSV headers")
                prompts = []
                skipped = 0
                for row in reader:
                    title, content, kind = row.get("act"), row.get("prompt"), row.get("type")
                    if not all(isinstance(value, str) for value in (title, content, kind)):
                        raise ValueError("CSV row")
                    if kind != "TEXT" or not title.strip() or not content.strip() or len(title) > 500 or len(content) > MAX_PROMPT:
                        skipped += 1
                        continue
                    prompts.append({"title": title, "content": content})
                    if len(prompts) > 10_000:
                        raise ValueError("Too many prompts")
            finally:
                csv.field_size_limit(previous_limit)
            if not prompts:
                raise ValueError("Empty catalog")
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            raise PromptLibraryError("Şablon kataloğu geçersiz; önceki katalog korunuyor.") from exc
        encoded = json.dumps({"source": CSV_URL, "prompts": prompts}, ensure_ascii=False).encode("utf-8")
        temporary: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".prompts-", delete=False) as file:
                temporary = file.name
                file.write(encoded)
            os.replace(temporary, self.path)
        except OSError as exc:
            raise PromptLibraryError("Yerel katalog kaydedilemedi; önceki katalog korunuyor.") from exc
        finally:
            if temporary is not None and Path(temporary).exists():
                Path(temporary).unlink()
        return {"count": len(prompts), "skipped": skipped, "source": CSV_URL}

    def _search_local(self, query: str) -> dict[str, Any]:
        if not self.path.exists():
            return {"prompts": [], "source": "local", "installed": False}
        try:
            if self.path.stat().st_size > MAX_BYTES * 3:
                raise ValueError("Catalog too large")
            catalog = json.loads(self.path.read_text(encoding="utf-8"))
            raw = catalog["prompts"]
            if not isinstance(raw, list) or len(raw) > 10_000:
                raise TypeError("Invalid catalog")
            matches = []
            for item in raw:
                if (
                    not isinstance(item, dict) or not isinstance(item.get("title"), str)
                    or not isinstance(item.get("content"), str) or len(item["title"]) > 500
                    or not item["content"] or len(item["content"]) > MAX_PROMPT
                ):
                    raise TypeError("Invalid prompt")
                if query.casefold() in item["title"].casefold():
                    matches.append(item)
                if len(matches) == 10:
                    break
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise PromptLibraryError("Yerel şablon kataloğu okunamadı.") from exc
        return {"prompts": matches, "source": "local", "installed": True}
