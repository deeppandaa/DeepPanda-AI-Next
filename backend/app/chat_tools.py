from __future__ import annotations

import json
import re
from typing import Any

from app.plugins.gateway import (
    PluginActionNotFoundError,
    PluginGateway,
    PluginNotFoundError,
)
from app.plugins.jobs import JobNotFoundError

READ_ONLY_CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_local_models",
            "description": "List locally installed Ollama models.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workflows",
            "description": "List available chat workflows.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workflow",
            "description": "Get the instructions and details for one workflow.",
            "parameters": {
                "type": "object",
                "properties": {"mode": {"type": "string", "enum": ["standard", "plan", "debug", "review", "audit", "minimal"]}},
                "required": ["mode"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_jobs",
            "description": "List recent local background jobs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["queued", "running", "cancel_requested", "cancelled", "succeeded", "failed"],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job",
            "description": "Get the status and result of a local background job by its ID.",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"}},
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code_symbols",
            "description": "Search the existing local Python code graph for symbols. Does not build or change the graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_code_path",
            "description": "Find a call/import path between two symbols in the existing local Python code graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "minLength": 1, "maxLength": 300},
                    "target": {"type": "string", "minLength": 1, "maxLength": 300},
                },
                "required": ["source", "target"],
                "additionalProperties": False,
            },
        },
    },
]

MAX_TOOL_CALLS = 3
MAX_TOOL_ROUNDS = 3
MAX_TOOL_RESULT_CHARS = 12_000
_TOOL_NAMES = {tool["function"]["name"] for tool in READ_ONLY_CHAT_TOOLS}


async def execute_read_only_chat_tool(
    gateway: PluginGateway,
    name: str,
    arguments: Any,
) -> tuple[Any, bool]:
    if name not in _TOOL_NAMES:
        return {"error": "This tool is not available in chat."}, True
    if not isinstance(arguments, dict):
        return {"error": "Tool arguments must be a JSON object."}, True

    try:
        if name == "list_local_models":
            _validate_keys(arguments, set())
            result = await gateway.invoke("ollama", "models", {})
        elif name == "list_workflows":
            _validate_keys(arguments, set())
            result = await gateway.invoke("workflows", "catalog", {})
        elif name == "get_workflow":
            _validate_keys(arguments, {"mode"})
            result = await gateway.invoke("workflows", "get", arguments)
        elif name == "list_jobs":
            _validate_keys(arguments, {"status", "limit"})
            status, limit = arguments.get("status"), arguments.get("limit", 5)
            if status is not None and status not in {
                "queued", "running", "cancel_requested", "cancelled", "succeeded", "failed",
            }:
                raise ValueError("status is not a known job state.")
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
                raise ValueError("limit must be an integer from 1 to 10.")
            result = await gateway.invoke("jobs", "list", {"status": status, "limit": limit})
        elif name == "get_job":
            _validate_keys(arguments, {"job_id"}, required={"job_id"})
            if not isinstance(arguments["job_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", arguments["job_id"]):
                raise ValueError("job_id must be a valid job identifier.")
            result = (await gateway.invoke("jobs", "get", arguments))["job"]
        elif name == "search_code_symbols":
            _validate_keys(arguments, {"query", "limit"}, required={"query"})
            query, limit = arguments["query"], arguments.get("limit", 10)
            if not isinstance(query, str) or not query.strip() or len(query) > 200:
                raise ValueError("query must be non-empty text up to 200 characters.")
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
                raise ValueError("limit must be an integer from 1 to 10.")
            result = await gateway.invoke("codegraph", "search", {"query": query, "limit": limit})
        else:
            _validate_keys(arguments, {"source", "target"}, required={"source", "target"})
            if any(
                not isinstance(arguments[key], str) or not arguments[key].strip() or len(arguments[key]) > 300
                for key in ("source", "target")
            ):
                raise ValueError("source and target must be non-empty text up to 300 characters.")
            result = await gateway.invoke("codegraph", "path", arguments)
    except (PluginNotFoundError, PluginActionNotFoundError, JobNotFoundError, TypeError, ValueError) as exc:
        return {"error": str(exc)[:500]}, True
    return result, False


def _validate_keys(arguments: dict[str, Any], allowed: set[str], required: set[str] | None = None) -> None:
    if set(arguments) - allowed or (required or set()) - set(arguments):
        raise ValueError("Tool arguments do not match the declared schema.")


def _tool_message_content(result: Any) -> str:
    try:
        content = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        content = json.dumps({"error": "Tool returned a non-JSON result."})
    if len(content) > MAX_TOOL_RESULT_CHARS:
        content = json.dumps({
            "truncated": True,
            "message": "Tool result exceeded the chat context limit.",
            "preview": content[: MAX_TOOL_RESULT_CHARS - 200],
        }, ensure_ascii=False)
    return content


async def complete_with_read_only_tools(
    gateway: PluginGateway,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    response = await gateway.invoke("ollama", "chat", {**payload, "tools": READ_ONLY_CHAT_TOOLS})
    context_messages = list(payload.get("messages") or [])
    context_messages.append({"role": "user", "content": payload["message"]})
    tools_used: list[dict[str, str]] = []
    tool_calls_used = 0

    for round_index in range(MAX_TOOL_ROUNDS):
        response_message = response.get("message") if isinstance(response, dict) else None
        tool_calls = response_message.get("tool_calls") if isinstance(response_message, dict) else None
        if tool_calls is None or tool_calls == []:
            content = response_message.get("content") if isinstance(response_message, dict) else None
            try:
                text_call = json.loads(content) if isinstance(content, str) else None
            except json.JSONDecodeError:
                text_call = None
            if (
                isinstance(text_call, dict)
                and set(text_call) == {"name", "arguments"}
                and isinstance(text_call.get("name"), str)
                and text_call["name"] in _TOOL_NAMES
                and isinstance(text_call.get("arguments"), dict)
            ):
                tool_calls = [{
                    "function": {
                        "name": text_call["name"],
                        "arguments": text_call["arguments"],
                    },
                }]
            else:
                return response, tools_used
        if not isinstance(tool_calls, list):
            raise TypeError("Model returned malformed tool calls.")

        normalized_calls: list[dict[str, Any]] = []
        for call in tool_calls:
            function = call.get("function") if isinstance(call, dict) else None
            name = function.get("name") if isinstance(function, dict) else None
            arguments = function.get("arguments") if isinstance(function, dict) else None
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise TypeError("Model returned malformed tool call arguments.")
            normalized = {"function": {"name": name, "arguments": arguments}}
            call_id = call.get("id")
            if isinstance(call_id, str):
                normalized["id"] = call_id
            normalized_calls.append(normalized)
        context_messages.append({
            "role": "assistant",
            "content": response_message.get("content") if isinstance(response_message.get("content"), str) else "",
            "tool_calls": normalized_calls,
        })

        for call in normalized_calls:
            name = call["function"]["name"]
            if tool_calls_used >= MAX_TOOL_CALLS:
                result, failed = {"error": "The read-only tool call limit for this turn was reached."}, True
            else:
                result, failed = await execute_read_only_chat_tool(
                    gateway, name, call["function"]["arguments"],
                )
                tool_calls_used += 1
            context_messages.append({
                "role": "tool",
                "tool_name": name,
                "content": _tool_message_content(result),
            })
            tools_used.append({"name": name, "status": "error" if failed else "completed"})

        follow_up = {
            key: value for key, value in payload.items()
            if key not in {"message", "messages"}
        }
        follow_up["messages"] = context_messages
        follow_up["tools"] = READ_ONLY_CHAT_TOOLS if round_index + 1 < MAX_TOOL_ROUNDS else []
        response = await gateway.invoke("ollama", "chat", follow_up)

    return response, tools_used
