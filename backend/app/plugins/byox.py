from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import partial
from pathlib import Path
from typing import Any

import httpx

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.integration_errors import IntegrationNotFoundError, IntegrationUnavailableError
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)

SOURCE_URL = "https://raw.githubusercontent.com/codecrafters-io/build-your-own-x/master/README.md"
_CATEGORY = re.compile(r"^####\s+Build your own\s+`(?P<name>[^`]+)`\s*$")
_ITEM = re.compile(
    r"^\s*[*-]\s*\[\*\*(?P<languages>[^*]+?)\*\*\s*:\s*_(?P<title>.+)_\]\((?P<url>https?://[^)\s]+)\)(?P<extra>.*)$"
)


def parse_catalog(markdown: str) -> list[dict[str, Any]]:
    categories: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in markdown.splitlines():
        heading = _CATEGORY.match(line)
        if heading:
            current = {"name": heading.group("name").strip(), "items": []}
            categories.append(current)
            continue
        if line.startswith("## ") and current is not None:
            current = None
            continue
        item = _ITEM.match(line)
        if item and current is not None:
            current["items"].append({
                "languages": [part.strip() for part in item.group("languages").split("/") if part.strip()],
                "title": item.group("title").strip(),
                "url": item.group("url"),
                "video": "[video]" in item.group("extra"),
            })
    return [category for category in categories if category["items"]]


class BuildYourOwnXPlugin:
    """Searchable catalog of codecrafters-io/build-your-own-x tutorials, with local learning plans."""

    manifest = PluginManifest(
        plugin_id="byox",
        display_name="Build Your Own X",
        description="build-your-own-x eğitim kataloğunu indirir, kategori/dil ile arar ve yerel Qwen ile öğrenme planı çıkarır.",
        actions=("categories", "search", "refresh", "plan"),
    )

    def __init__(self, gateway: PluginGateway | None = None, data_dir: str | Path | None = None,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.gateway = gateway
        root = Path(data_dir or os.getenv("AI_DATA_DIR", "/data")).expanduser()
        self.cache_path = root / "byox" / "catalog.json"
        self.source_url = os.getenv("BYOX_SOURCE_URL", SOURCE_URL)
        self.transport = transport

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "refresh":
            catalog = await self.refresh()
            return {"categories": len(catalog["categories"]), "items": catalog["item_count"],
                    "fetched_at": catalog["fetched_at"]}
        catalog = await self.catalog()
        if action == "categories":
            return {
                "fetched_at": catalog["fetched_at"],
                "categories": [
                    {"name": category["name"], "count": len(category["items"]),
                     "languages": sorted({lang for item in category["items"] for lang in item["languages"]})}
                    for category in catalog["categories"]
                ],
            }
        if action == "search":
            return self.search(catalog, payload)
        if action == "plan":
            return await self.plan(catalog, payload)
        raise ValueError(f"Unsupported byox action: {action}")

    async def catalog(self) -> dict[str, Any]:
        cached = await run_thread(self._read_cache, logger)
        return cached if cached is not None else await self.refresh()

    async def refresh(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0), transport=self.transport,
                                         follow_redirects=True) as client:
                response = await client.get(self.source_url)
                response.raise_for_status()
                markdown = response.text
        except httpx.HTTPError as exc:
            raise IntegrationUnavailableError(f"build-your-own-x kataloğu indirilemedi: {exc}") from exc
        categories = parse_catalog(markdown)
        if not categories:
            raise IntegrationUnavailableError("build-your-own-x README biçimi tanınamadı.")
        catalog = {
            "source": self.source_url,
            "fetched_at": int(time.time()),
            "item_count": sum(len(category["items"]) for category in categories),
            "categories": categories,
        }
        await run_thread(partial(self._write_cache, catalog), logger)
        return catalog

    def search(self, catalog: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        query = str(payload.get("query", "")).casefold().strip()
        language = str(payload.get("language", "")).casefold().strip()
        category_filter = str(payload.get("category", "")).casefold().strip()
        limit = payload.get("limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500.")
        results = []
        for category in catalog["categories"]:
            if category_filter and category_filter != category["name"].casefold():
                continue
            for item in category["items"]:
                if language and language not in {lang.casefold() for lang in item["languages"]}:
                    continue
                haystack = f"{category['name']} {item['title']} {' '.join(item['languages'])}".casefold()
                if query and query not in haystack:
                    continue
                results.append({"category": category["name"], **item})
        return {"total": len(results), "results": results[:limit]}

    async def plan(self, catalog: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if self.gateway is None:
            raise IntegrationUnavailableError("Plan için yerel model geçidi gerekir.")
        url = payload.get("url")
        match = next(
            ({"category": category["name"], **item}
             for category in catalog["categories"] for item in category["items"] if item["url"] == url),
            None,
        )
        if match is None:
            raise IntegrationNotFoundError("Katalogda bu URL'ye sahip eğitim yok; önce search kullanın.")
        goal = str(payload.get("goal", "")).strip()[:2_000]
        message = (
            f"'{match['title']}' ({', '.join(match['languages'])}, kategori: {match['category']}, {match['url']}) "
            "eğitimini takip ederek sıfırdan kendi sürümümü yazmak istiyorum. Bağlantıyı açamazsın; konu bilgine göre "
            "5-8 adımlık, her adımda hedef, yazılacak bileşen ve kendini doğrulama testi olan bir öğrenme planı çıkar."
            + (f" Hedefim: {goal}" if goal else "")
        )
        request: dict[str, Any] = {"message": message}
        if isinstance(payload.get("model"), str) and payload["model"].strip():
            request["model"] = payload["model"].strip()
        result = await self.gateway.invoke("ollama", "chat", request)
        message_obj = result.get("message") if isinstance(result, dict) else None
        return {"tutorial": match, "plan": message_obj.get("content", "") if isinstance(message_obj, dict) else ""}

    def _read_cache(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and isinstance(data.get("categories"), list) else None

    def _write_cache(self, catalog: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.cache_path)
