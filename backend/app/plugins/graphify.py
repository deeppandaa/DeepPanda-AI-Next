from __future__ import annotations

import json
import logging
import os
from collections import Counter, deque
from functools import partial
from pathlib import Path
from typing import Any

from app.plugins.contracts import PluginManifest
from app.plugins.integration_errors import IntegrationNotFoundError, IntegrationUnavailableError
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Undirected view of a graphify node-link graph.json (NetworkX format, 'links' or 'edges')."""

    def __init__(self, data: dict[str, Any]) -> None:
        nodes = data.get("nodes")
        links = data.get("links", data.get("edges"))
        if not isinstance(nodes, list) or not isinstance(links, list):
            raise ValueError("graph.json must contain 'nodes' and 'links' (or 'edges') lists.")
        self.nodes: dict[str, dict[str, Any]] = {}
        for node in nodes:
            if isinstance(node, dict) and "id" in node:
                self.nodes[str(node["id"])] = node
        self.adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {node_id: [] for node_id in self.nodes}
        self.edges: list[dict[str, Any]] = []
        for link in links:
            if not isinstance(link, dict):
                continue
            source, target = str(link.get("source")), str(link.get("target"))
            if source not in self.nodes or target not in self.nodes:
                continue
            self.edges.append(link)
            self.adjacency[source].append((target, link))
            self.adjacency[target].append((source, link))

    def label(self, node_id: str) -> str:
        return str(self.nodes[node_id].get("label") or node_id)

    def describe(self, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        return {
            "id": node_id,
            "label": self.label(node_id),
            "source_file": node.get("source_file", ""),
            "source_location": node.get("source_location", ""),
            "community": node.get("community"),
            "degree": len(self.adjacency[node_id]),
        }

    def find(self, term: str, limit: int = 20) -> list[str]:
        words = [word for word in term.casefold().split() if word]
        if not words:
            return []
        scored = []
        for node_id, node in self.nodes.items():
            label = self.label(node_id).casefold()
            source = str(node.get("source_file", "")).casefold()
            if term.casefold() == node_id.casefold() or term.casefold() == label:
                score = 100.0
            else:
                score = sum(1.0 for word in words if word in label) + sum(0.5 for word in words if word in source)
            if score:
                scored.append((score, len(self.adjacency[node_id]), node_id))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return [node_id for _score, _degree, node_id in scored[:limit]]

    def resolve(self, term: Any) -> str:
        if not isinstance(term, str) or not term.strip():
            raise ValueError("node must be a node label or id.")
        if term in self.nodes:
            return term
        matches = self.find(term, limit=1)
        if not matches:
            raise IntegrationNotFoundError(f"Grafikte düğüm bulunamadı: {term}")
        return matches[0]

    def neighbors(self, node_id: str, depth: int, relation: str | None, limit: int) -> dict[str, Any]:
        seen = {node_id: 0}
        edges = []
        queue = deque([node_id])
        while queue and len(seen) < limit:
            current = queue.popleft()
            if seen[current] >= depth:
                continue
            for neighbor, link in self.adjacency[current]:
                if relation and link.get("relation") != relation:
                    continue
                edges.append({
                    "source": self.label(current),
                    "relation": link.get("relation", ""),
                    "confidence": link.get("confidence", ""),
                    "target": self.label(neighbor),
                })
                if neighbor not in seen:
                    seen[neighbor] = seen[current] + 1
                    queue.append(neighbor)
                    if len(seen) >= limit:
                        break
        return {
            "node": self.describe(node_id),
            "nodes": [self.describe(item) for item in seen if item != node_id],
            "edges": edges[: limit * 4],
        }

    def shortest_path(self, source: str, target: str, max_hops: int) -> list[str] | None:
        previous: dict[str, str | None] = {source: None}
        queue = deque([(source, 0)])
        while queue:
            current, hops = queue.popleft()
            if current == target:
                path = []
                node: str | None = current
                while node is not None:
                    path.append(node)
                    node = previous[node]
                return path[::-1]
            if hops >= max_hops:
                continue
            for neighbor, _link in self.adjacency[current]:
                if neighbor not in previous:
                    previous[neighbor] = current
                    queue.append((neighbor, hops + 1))
        return None


class GraphifyPlugin:
    """Queries a graphify knowledge graph (graphify-out/graph.json) without needing networkx."""

    manifest = PluginManifest(
        plugin_id="graphify",
        display_name="graphify bilgi grafiği",
        description="graphify-out/graph.json bilgi grafiğinde özet, arama, komşular, en kısa yol ve GRAPH_REPORT.md okuma.",
        actions=("status", "summary", "query", "neighbors", "path", "report"),
    )

    def __init__(self, graph_path: str | Path | None = None) -> None:
        self.graph_path = Path(
            graph_path or os.getenv("GRAPHIFY_GRAPH", "/workspace/graphify-out/graph.json")
        ).expanduser()
        self._cache: tuple[float, KnowledgeGraph] | None = None

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "status": self.status,
            "summary": self.summary,
            "query": self.query,
            "neighbors": self.neighbors,
            "path": self.path,
            "report": self.report,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unsupported graphify action: {action}")
        return await run_thread(partial(handler, payload), logger)

    def graph(self) -> KnowledgeGraph:
        try:
            modified = self.graph_path.stat().st_mtime
        except OSError as exc:
            raise IntegrationUnavailableError(
                f"graph.json bulunamadı: {self.graph_path}. Önce Copilot CLI'da '/graphify .' çalıştırın."
            ) from exc
        if self._cache is not None and self._cache[0] == modified:
            return self._cache[1]
        if self.graph_path.stat().st_size > 300_000_000:
            raise IntegrationUnavailableError("graph.json 300 MB sınırını aşıyor.")
        try:
            data = json.loads(self.graph_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise IntegrationUnavailableError(f"graph.json okunamadı: {exc}") from exc
        if not isinstance(data, dict):
            raise IntegrationUnavailableError("graph.json bir JSON nesnesi olmalı.")
        graph = KnowledgeGraph(data)
        self._cache = (modified, graph)
        return graph

    def status(self, _payload: dict[str, Any]) -> dict[str, Any]:
        exists = self.graph_path.is_file()
        report = self.graph_path.with_name("GRAPH_REPORT.md")
        return {
            "graph_path": str(self.graph_path),
            "exists": exists,
            "report_exists": report.is_file(),
            "html_exists": self.graph_path.with_name("graph.html").is_file(),
            "hint": "" if exists else "pip install graphifyy; graphify install --platform copilot; sonra Copilot CLI'da /graphify .",
        }

    def summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph = self.graph()
        top = _limit(payload.get("top", 15), 1, 100)
        hubs = sorted(graph.nodes, key=lambda node_id: (-len(graph.adjacency[node_id]), node_id))[:top]
        communities = Counter(
            node.get("community") for node in graph.nodes.values() if node.get("community") is not None
        )
        return {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "communities": len(communities),
            "largest_communities": [{"community": cid, "size": size} for cid, size in communities.most_common(10)],
            "relations": dict(Counter(str(edge.get("relation", "")) for edge in graph.edges).most_common(20)),
            "confidence": dict(Counter(str(edge.get("confidence", "")) for edge in graph.edges)),
            "god_nodes": [graph.describe(node_id) for node_id in hubs],
        }

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph = self.graph()
        text = payload.get("query")
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError("query must be non-empty text up to 500 characters.")
        limit = _limit(payload.get("limit", 20), 1, 100)
        return {"query": text, "matches": [graph.describe(node_id) for node_id in graph.find(text, limit)]}

    def neighbors(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph = self.graph()
        node_id = graph.resolve(payload.get("node"))
        relation = payload.get("relation") if isinstance(payload.get("relation"), str) else None
        return graph.neighbors(
            node_id,
            depth=_limit(payload.get("depth", 1), 1, 3),
            relation=relation or None,
            limit=_limit(payload.get("limit", 50), 1, 300),
        )

    def path(self, payload: dict[str, Any]) -> dict[str, Any]:
        graph = self.graph()
        source = graph.resolve(payload.get("source"))
        target = graph.resolve(payload.get("target"))
        route = graph.shortest_path(source, target, _limit(payload.get("max_hops", 8), 1, 20))
        return {
            "source": graph.describe(source),
            "target": graph.describe(target),
            "found": route is not None,
            "path": [graph.describe(node_id) for node_id in route or []],
        }

    def report(self, _payload: dict[str, Any]) -> dict[str, Any]:
        report = self.graph_path.with_name("GRAPH_REPORT.md")
        try:
            text = report.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise IntegrationUnavailableError(f"GRAPH_REPORT.md bulunamadı: {report}") from exc
        return {"path": str(report), "markdown": text[:60_000], "truncated": len(text) > 60_000}


def _limit(value: Any, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ValueError(f"value must be an integer between {low} and {high}.")
    return value
