from __future__ import annotations

import ast
import json
import logging
import os
import time
from functools import partial
from pathlib import Path
from typing import Any

from app.plugins.contracts import PluginManifest
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class _GraphVisitor(ast.NodeVisitor):
    def __init__(self, path: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        self.path = path
        self.nodes = nodes
        self.edges = edges
        module_id = f"module:{path}"
        self.scope_ids = [module_id]
        self.scope_names = [Path(path).with_suffix("").as_posix().replace("/", ".")]
        self.pending_calls: list[tuple[str, str, int]] = []
        self.nodes.append({"id": module_id, "kind": "module", "name": Path(path).stem, "qualified_name": self.scope_names[0], "path": path, "line": 1})

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_definition(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_definition(node, "function")

    def _visit_definition(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        qualified_name = f"{self.scope_names[-1]}.{node.name}"
        node_id = f"{kind}:{self.path}::{qualified_name}"
        self.nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "name": node.name,
                "qualified_name": qualified_name,
                "path": self.path,
                "line": node.lineno,
            }
        )
        self.edges.append({"source": self.scope_ids[-1], "target": node_id, "kind": "defines", "line": node.lineno})
        self.scope_ids.append(node_id)
        self.scope_names.append(qualified_name)
        for child in node.body:
            self.visit(child)
        self.scope_names.pop()
        self.scope_ids.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(
                {"source": self.scope_ids[-1], "target_name": alias.name, "kind": "imports", "line": node.lineno}
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        imported_module = "." * node.level + (node.module or "")
        self.edges.append(
            {"source": self.scope_ids[-1], "target_name": imported_module, "kind": "imports", "line": node.lineno}
        )

    def visit_Call(self, node: ast.Call) -> None:
        self.pending_calls.append((self.scope_ids[-1], ast.unparse(node.func), node.lineno))
        self.generic_visit(node)


class CodeGraphPlugin:
    manifest = PluginManifest(
        plugin_id="codegraph",
        display_name="Local Code Graph",
        description="Python AST tabanlı çevrimdışı sembol ve çağrı grafı.",
        actions=("build", "search", "path"),
    )

    excluded_directories = frozenset(
        {
            ".git", ".hg", ".svn", ".venv", ".tools", "venv", "env", "node_modules", "dist", "build", "out",
            ".next", ".cache", "__pycache__", ".pytest_cache", ".ruff_cache", "models", "ai-runtimes",
            "packages", "vendor", "target", "data", "runtimes", "_tmp", "_arsiv",
        }
    )
    max_files = 3000
    max_file_bytes = 1_000_000
    max_total_bytes = 50_000_000
    max_graph_nodes = 50_000
    max_seconds = 120

    def __init__(self, root: str | Path | None = None, data_dir: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("DIAGNOSTICS_ROOT", "/workspace")).expanduser().resolve()
        self.data_dir = Path(data_dir or os.getenv("AI_DATA_DIR", "/data")).expanduser().resolve()
        self.graph_path = self.data_dir / "code_graph.json"

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "build":
            return await run_thread(partial(self._build), logger)
        if action == "search":
            return self._search(payload)
        if action == "path":
            return self._path(payload)
        raise ValueError(f"Unsupported code graph action: {action}")

    def _build(self) -> dict[str, Any]:
        if not self.root.is_dir():
            raise ValueError("Code graph workspace is unavailable.")

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []
        scanned_files = 0
        total_bytes = 0
        truncated = False
        deadline = time.monotonic() + self.max_seconds

        for directory, child_directories, file_names in os.walk(self.root, followlinks=False):
            if time.monotonic() >= deadline:
                truncated = True
                break
            child_directories[:] = [
                name
                for name in child_directories
                if name.casefold() not in self.excluded_directories and not (Path(directory) / name).is_symlink()
            ]
            for file_name in file_names:
                path = Path(directory) / file_name
                if path.suffix.casefold() != ".py" or path.is_symlink():
                    continue
                try:
                    size = path.stat().st_size
                    if size > self.max_file_bytes:
                        continue
                    if scanned_files >= self.max_files or total_bytes + size > self.max_total_bytes:
                        truncated = True
                        break
                    source = path.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeError):
                    continue

                relative_path = path.relative_to(self.root).as_posix()
                scanned_files += 1
                total_bytes += size
                try:
                    tree = ast.parse(source, filename=relative_path)
                except SyntaxError as exc:
                    parse_errors.append({"path": relative_path, "line": exc.lineno, "message": exc.msg})
                    continue

                visitor = _GraphVisitor(relative_path, nodes, edges)
                visitor.visit(tree)
                for source_id, target_name, line in visitor.pending_calls:
                    edges.append({"source": source_id, "target_name": target_name, "kind": "calls", "line": line})
                if len(nodes) + len(edges) >= self.max_graph_nodes:
                    truncated = True
                    break
            if truncated:
                break

        self._resolve_local_edges(nodes, edges)
        graph = {
            "schema_version": 1,
            "workspace": ".",
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "truncated": truncated,
            "nodes": nodes,
            "edges": edges,
            "parse_errors": parse_errors,
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.graph_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary_path, self.graph_path)
        return {
            "status": "built",
            "graph_path": "data/code_graph.json",
            "scanned_files": scanned_files,
            "truncated": truncated,
            "summary": {
                "modules": sum(node["kind"] == "module" for node in nodes),
                "classes": sum(node["kind"] == "class" for node in nodes),
                "functions": sum(node["kind"] == "function" for node in nodes),
                "edges": len(edges),
                "parse_errors": len(parse_errors),
            },
        }

    @staticmethod
    def _resolve_local_edges(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        symbols_by_name: dict[str, list[str]] = {}
        modules_by_name: dict[str, list[str]] = {}
        for node in nodes:
            if node["kind"] in {"function", "class"}:
                symbols_by_name.setdefault(node["name"], []).append(node["id"])
                symbols_by_name.setdefault(node["qualified_name"], []).append(node["id"])
            elif node["kind"] == "module":
                module_name = node["path"][:-3].replace("/", ".")
                modules_by_name.setdefault(module_name, []).append(node["id"])
                modules_by_name.setdefault(node["qualified_name"], []).append(node["id"])
                if module_name.endswith(".__init__"):
                    modules_by_name.setdefault(module_name.removesuffix(".__init__"), []).append(node["id"])
        for edge in edges:
            target_name = edge.get("target_name")
            if not target_name:
                continue
            if edge["kind"] == "imports":
                candidates = modules_by_name.get(target_name.lstrip("."), [])
            else:
                candidates = symbols_by_name.get(target_name, [])
                if not candidates and "." in target_name:
                    candidates = symbols_by_name.get(target_name.rsplit(".", maxsplit=1)[-1], [])
            candidates = list(dict.fromkeys(candidates))
            if len(candidates) == 1:
                edge["target"] = candidates[0]
                edge.pop("target_name", None)

    def _load_graph(self) -> dict[str, Any]:
        try:
            return json.loads(self.graph_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("Build the code graph before searching it.") from exc

    def _search(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = self._required_text(payload, "query", 200).casefold()
        limit = self._limit(payload.get("limit"), default=20, maximum=100)
        graph = self._load_graph()
        matches = [
            node
            for node in graph["nodes"]
            if query in node["name"].casefold() or query in node["qualified_name"].casefold()
        ]
        return {"results": matches[:limit], "truncated": len(matches) > limit}

    def _path(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._required_text(payload, "source", 300)
        target = self._required_text(payload, "target", 300)
        graph = self._load_graph()
        source_matches = self._find_nodes(graph["nodes"], source)
        target_matches = self._find_nodes(graph["nodes"], target)
        if len(source_matches) != 1 or len(target_matches) != 1:
            if len(source_matches) > 1 or len(target_matches) > 1:
                return {
                    "found": False,
                    "reason": "Symbol name is ambiguous; use a qualified name.",
                    "source_candidates": source_matches[:10],
                    "target_candidates": target_matches[:10],
                }
            return {"found": False, "reason": "Source or target symbol was not found."}
        source_node = source_matches[0]
        target_node = target_matches[0]
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for edge in graph["edges"]:
            if "target" in edge:
                adjacency.setdefault(edge["source"], []).append((edge["target"], edge))
        queue = [source_node["id"]]
        previous: dict[str, tuple[str, dict[str, Any]] | None] = {source_node["id"]: None}
        for current in queue:
            if current == target_node["id"]:
                break
            for neighbor, edge in adjacency.get(current, []):
                if neighbor not in previous:
                    previous[neighbor] = (current, edge)
                    queue.append(neighbor)
        if target_node["id"] not in previous:
            return {"found": False, "source": source_node, "target": target_node}
        path_nodes = [target_node["id"]]
        path_edges: list[dict[str, Any]] = []
        current = target_node["id"]
        while previous[current] is not None:
            prior, edge = previous[current]
            path_edges.append(edge)
            path_nodes.append(prior)
            current = prior
        path_nodes.reverse()
        path_edges.reverse()
        node_by_id = {node["id"]: node for node in graph["nodes"]}
        return {
            "found": True,
            "hops": len(path_edges),
            "nodes": [node_by_id[node_id] for node_id in path_nodes],
            "edges": path_edges,
        }

    @staticmethod
    def _find_nodes(nodes: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
        exact = [node for node in nodes if node["id"] == name or node["qualified_name"] == name]
        if exact:
            return exact
        return [node for node in nodes if node["name"] == name]

    @staticmethod
    def _required_text(payload: dict[str, Any], key: str, max_length: int) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()

    @staticmethod
    def _limit(value: Any, default: int, maximum: int) -> int:
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("limit must be an integer.")
        return max(1, min(value, maximum))