from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx

from app.plugins.contracts import PluginManifest
from app.plugins.integration_errors import (
    IntegrationNotFoundError,
    IntegrationUnavailableError,
    require_approval,
)

_ENV_REF = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}")
_INPUT_REF = re.compile(r"\$\{input:[^}]+\}")
_SERVER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,80}")


def default_config_paths() -> list[Path]:
    configured = os.getenv("MCP_SERVERS_CONFIG", "")
    paths = [Path(item).expanduser() for item in configured.split(os.pathsep) if item.strip()]
    return paths or [Path("/workspace/mcp-servers.json")]


def vscode_user_config_path() -> Path | None:
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Code" / "User" / "mcp.json"


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments plus trailing commas (VS Code mcp.json is JSONC)."""
    out: list[str] = []
    index, length, in_string = 0, len(text), False
    while index < length:
        char = text[index]
        if in_string:
            out.append(char)
            if char == "\\" and index + 1 < length:
                out.append(text[index + 1])
                index += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline == -1 else newline
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end == -1 else end + 2
            continue
        else:
            out.append(char)
        index += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_server_configs(paths: list[Path]) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            raw = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            raise IntegrationUnavailableError(f"MCP yapılandırması okunamadı: {path} ({exc})") from exc
        entries = (raw.get("servers") or raw.get("mcpServers") or {}) if isinstance(raw, dict) else {}
        if not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if isinstance(name, str) and _SERVER_NAME.fullmatch(name) and isinstance(entry, dict):
                servers[name] = {**entry, "_source": str(path)}
    return servers


def describe_server(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    transport = server_transport(entry)
    unresolved = sorted(set(_INPUT_REF.findall(json.dumps(entry))))
    missing_env = sorted({
        match for match in _ENV_REF.findall(json.dumps(entry)) if not os.getenv(match)
    })
    available = True
    reason = ""
    if transport == "stdio":
        command = entry.get("command")
        if not isinstance(command, str) or shutil.which(command) is None:
            available, reason = False, f"Komut bulunamadı: {command}"
    elif transport not in {"http", "sse"}:
        available, reason = False, f"Desteklenmeyen MCP türü: {transport}"
    if unresolved:
        available, reason = False, "VS Code ${input:...} değeri gerekiyor."
    if missing_env:
        available, reason = False, "Eksik ortam değişkeni: " + ", ".join(missing_env)
    return {
        "name": name,
        "transport": transport,
        "target": entry.get("url") if transport in {"http", "sse"} else " ".join(
            [str(entry.get("command", ""))] + [str(arg) for arg in entry.get("args", []) if isinstance(arg, str)]
        ),
        "source": entry.get("_source", ""),
        "available": available,
        "reason": reason,
    }


def server_transport(entry: dict[str, Any]) -> str:
    kind = entry.get("type")
    if isinstance(kind, str) and kind:
        return {"streamable-http": "http", "streamableHttp": "http"}.get(kind, kind)
    return "http" if "url" in entry else "stdio"


def _expand(value: str) -> str:
    return _ENV_REF.sub(lambda match: os.getenv(match.group(1), ""), value)


async def _open_session(stack: AsyncExitStack, entry: dict[str, Any]) -> Any:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.sse import sse_client
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client
    except ImportError as exc:
        raise IntegrationUnavailableError("MCP istemci paketi kurulu değil (pip install mcp).") from exc

    transport = server_transport(entry)
    if transport == "stdio":
        env = {**os.environ, **{key: _expand(str(value)) for key, value in (entry.get("env") or {}).items()}}
        params = StdioServerParameters(
            command=str(entry.get("command")),
            args=[_expand(str(arg)) for arg in entry.get("args", [])],
            env=env,
            cwd=entry.get("cwd") or None,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
    else:
        headers = {str(key): _expand(str(value)) for key, value in (entry.get("headers") or {}).items()}
        url = _expand(str(entry.get("url", "")))
        if not url.startswith(("http://", "https://")):
            raise ValueError("MCP url must be http(s).")
        if transport == "sse":
            read, write = await stack.enter_async_context(sse_client(url, headers=headers, timeout=15))
        else:
            http_client = await stack.enter_async_context(
                create_mcp_http_client(headers=headers, timeout=httpx.Timeout(30.0, read=300.0))
            )
            read, write, _session_id = await stack.enter_async_context(
                streamable_http_client(url, http_client=http_client)
            )
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session


async def list_tools(entry: dict[str, Any]) -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        session = await _open_session(stack, entry)
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for _page in range(20):
            result = await session.list_tools(cursor)
            for tool in result.tools:
                tools.append({
                    "name": tool.name,
                    "description": (tool.description or "")[:2_000],
                    "input_schema": tool.inputSchema,
                    "read_only": bool(getattr(tool.annotations, "readOnlyHint", False)) if tool.annotations else False,
                })
            cursor = result.nextCursor
            if not cursor:
                break
        return tools


async def call_tool(entry: dict[str, Any], tool: str, arguments: dict[str, Any], timeout_seconds: float = 300) -> dict[str, Any]:
    async with AsyncExitStack() as stack:
        session = await _open_session(stack, entry)
        result = await session.call_tool(tool, arguments, read_timeout_seconds=timedelta(seconds=timeout_seconds))
    content: list[dict[str, Any]] = []
    for block in result.content:
        kind = getattr(block, "type", "")
        if kind == "text":
            content.append({"type": "text", "text": block.text[:200_000]})
        elif kind == "image":
            content.append({"type": "image", "mime_type": block.mimeType, "bytes": len(block.data or "")})
        elif kind == "resource":
            resource = block.resource
            content.append({"type": "resource", "uri": str(resource.uri), "text": getattr(resource, "text", "")[:50_000]})
        else:
            content.append({"type": kind or "unknown"})
    return {
        "tool": tool,
        "is_error": bool(result.isError),
        "content": content,
        "structured": result.structuredContent,
    }


class McpBridgePlugin:
    """Connects DeepPanda to the same MCP servers GitHub Copilot uses (VS Code mcp.json format)."""

    manifest = PluginManifest(
        plugin_id="mcp",
        display_name="MCP / Copilot araçları",
        description="VS Code/Copilot mcp.json biçimindeki MCP sunucularını (GitHub, rea, Docker, graphify...) listeler ve araçlarını çağırır.",
        actions=("servers", "tools", "call"),
    )

    def __init__(self, config_paths: list[Path] | None = None) -> None:
        self.config_paths = config_paths or default_config_paths()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        servers = load_server_configs(self.config_paths)
        if action == "servers":
            return {
                "config_paths": [str(path) for path in self.config_paths],
                "servers": [describe_server(name, entry) for name, entry in sorted(servers.items())],
            }
        name = payload.get("server")
        if not isinstance(name, str) or name not in servers:
            raise IntegrationNotFoundError(f"MCP sunucusu bulunamadı: {name}")
        entry = servers[name]
        status = describe_server(name, entry)
        if not status["available"]:
            raise IntegrationUnavailableError(f"{name}: {status['reason']}")
        if action == "tools":
            return {"server": name, "tools": await self._guard(list_tools(entry))}
        if action == "call":
            tool = payload.get("tool")
            arguments = payload.get("arguments") or {}
            if not isinstance(tool, str) or not tool.strip() or len(tool) > 200:
                raise ValueError("tool must be a tool name.")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object.")
            require_approval(payload, f"MCP aracı '{name}/{tool}' çalıştırmak için onay gerekir.")
            return {"server": name, **await self._guard(call_tool(entry, tool, arguments))}
        raise ValueError(f"Unsupported MCP action: {action}")

    @staticmethod
    async def _guard(coroutine: Any) -> Any:
        try:
            return await coroutine
        except (IntegrationUnavailableError, IntegrationNotFoundError, ValueError):
            raise
        except Exception as exc:
            inner = exc.exceptions[0] if isinstance(exc, ExceptionGroup) and exc.exceptions else exc
            raise IntegrationUnavailableError(f"MCP sunucusuna bağlanılamadı: {inner}") from exc
