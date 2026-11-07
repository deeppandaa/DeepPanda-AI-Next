import asyncio
import io
import json
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path

import httpx
from app.plugins.byox import BuildYourOwnXPlugin, parse_catalog
from app.plugins.database import DatabasePlugin
from app.plugins.graphify import GraphifyPlugin, KnowledgeGraph
from app.plugins.integration_errors import (
    IntegrationApprovalRequired,
    IntegrationNotFoundError,
    IntegrationUnavailableError,
)
from app.plugins.mcp_bridge import (
    McpBridgePlugin,
    _strip_jsonc,
    describe_server,
    load_server_configs,
    server_transport,
)
from app.plugins.openjarvis import OpenJarvisPlugin
from app.plugins.skills import SkillsPlugin, parse_skill_file


class DatabasePluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with sqlite3.connect(self.root / "memory.db") as connection:
            connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)")
            connection.executemany("INSERT INTO notes (body) VALUES (?)", [("a",), ("b",), ("c",)])
        connection.close()
        (self.root / "notes.txt").write_text("not a db", encoding="utf-8")
        self.plugin = DatabasePlugin(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_overview_lists_only_database_files(self) -> None:
        overview = self.plugin.overview({})
        self.assertEqual([item["name"] for item in overview["databases"]], ["memory.db"])
        self.assertEqual(overview["databases"][0]["tables"], 1)

    def test_tables_report_columns_and_row_counts(self) -> None:
        tables = self.plugin.tables({"database": "memory.db"})["tables"]
        self.assertEqual(tables[0]["name"], "notes")
        self.assertEqual(tables[0]["rows"], 3)
        self.assertEqual([column["name"] for column in tables[0]["columns"]], ["id", "body"])

    def test_query_is_read_only_and_limited(self) -> None:
        result = self.plugin.query({"database": "memory.db", "sql": "SELECT body FROM notes ORDER BY id", "limit": 2})
        self.assertEqual(result["rows"], [["a"], ["b"]])
        self.assertTrue(result["truncated"])
        for sql in ("DELETE FROM notes", "WITH x AS (SELECT 1) DELETE FROM notes", "ATTACH 'x.db' AS x"):
            with self.assertRaises(ValueError):
                self.plugin.query({"database": "memory.db", "sql": sql})
        self.assertEqual(self.plugin.tables({"database": "memory.db"})["tables"][0]["rows"], 3)

    def test_database_name_cannot_escape_data_dir(self) -> None:
        with self.assertRaises(ValueError):
            self.plugin.tables({"database": "../memory.db"})
        with self.assertRaises(IntegrationNotFoundError):
            self.plugin.tables({"database": "missing.db"})

    def test_check_and_backup_requires_approval(self) -> None:
        self.assertTrue(self.plugin.check({"database": "memory.db"})["ok"])
        with self.assertRaises(IntegrationApprovalRequired):
            self.plugin.backup({"database": "memory.db"})
        backup = self.plugin.backup({"database": "memory.db", "approved": True})
        self.assertTrue(Path(backup["backup"]).is_file())


class McpBridgeTests(unittest.TestCase):
    def test_reads_vscode_jsonc_and_mcpservers_formats(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vscode = Path(temp) / "mcp.json"
            vscode.write_text(
                '{\n // comment\n "servers": {"rea": {"type": "stdio", "command": "definitely-missing-cmd",'
                ' "args": ["mcp"]}, "github": {"type": "http", "url": "https://example.test/mcp/",'
                ' "headers": {"Authorization": "Bearer ${env:DP_TEST_MISSING_TOKEN}"}},},\n "inputs": []\n}',
                encoding="utf-8",
            )
            claude = Path(temp) / "claude.json"
            claude.write_text(json.dumps({"mcpServers": {"graphify": {"url": "https://example.test/sse", "type": "sse"}}}),
                              encoding="utf-8")
            servers = load_server_configs([vscode, claude, Path(temp) / "missing.json"])
        self.assertEqual(set(servers), {"rea", "github", "graphify"})
        rea = describe_server("rea", servers["rea"])
        self.assertFalse(rea["available"])
        github = describe_server("github", servers["github"])
        self.assertIn("DP_TEST_MISSING_TOKEN", github["reason"])
        self.assertEqual(server_transport(servers["graphify"]), "sse")
        self.assertEqual(server_transport({"url": "https://x"}), "http")

    def test_strip_jsonc_keeps_comment_markers_inside_strings(self) -> None:
        self.assertEqual(json.loads(_strip_jsonc('{"a": "http://x//y", /* c */ "b": [1,],}')),
                         {"a": "http://x//y", "b": [1]})

    def test_servers_action_and_unknown_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "mcp-servers.json"
            path.write_text(json.dumps({"servers": {}}), encoding="utf-8")
            plugin = McpBridgePlugin([path])
            listing = asyncio.run(plugin.invoke("servers", {}))
            self.assertEqual(listing["servers"], [])
            with self.assertRaises(IntegrationNotFoundError):
                asyncio.run(plugin.invoke("tools", {"server": "nope"}))


class SkillsPluginTests(unittest.TestCase):
    def test_discovers_skill_packs_and_parses_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill_dir = root / "replica-skill" / "replica-recon"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: replica-recon\ndescription: >-\n  Reverse-engineers any app\n  into a recon map.\n---\n\n# Body\nSteps",
                encoding="utf-8",
            )
            (skill_dir / "recon-map.md").write_text("template", encoding="utf-8")
            parsed = parse_skill_file(skill_dir / "SKILL.md")
            plugin = SkillsPlugin(roots=[root])
            listing = plugin.list_skills()
            detail = plugin.get_skill("replica-skill:replica-recon")
            by_name = plugin.get_skill("replica-recon")
        self.assertEqual(parsed["name"], "replica-recon")
        self.assertEqual(parsed["description"], "Reverse-engineers any app into a recon map.")
        self.assertIn("# Body", parsed["body"])
        self.assertEqual([skill["id"] for skill in listing["skills"]], ["replica-skill:replica-recon"])
        self.assertEqual(detail["files"], ["recon-map.md"])
        self.assertEqual(by_name["id"], detail["id"])

    def test_safe_extract_skips_traversal_and_links(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
            for name, data in (("repo-main/a/SKILL.md", b"---\nname: a\n---\nx"), ("repo-main/../evil.txt", b"x")):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("repo-main/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            bundle.addfile(link)
        with tempfile.TemporaryDirectory() as temp:
            plugin = SkillsPlugin(roots=[Path(temp)])
            target = Path(temp) / "pack"
            count = plugin._extract(buffer.getvalue(), target)
            self.assertEqual(count, 1)
            self.assertTrue((target / "a" / "SKILL.md").is_file())
            self.assertFalse((Path(temp) / "evil.txt").exists())
            self.assertFalse((target / "link").exists())

    def test_install_requires_approval(self) -> None:
        plugin = SkillsPlugin(roots=[])
        with self.assertRaises(IntegrationApprovalRequired):
            asyncio.run(plugin.invoke("install", {"repo": "Jakeschincariol/replica-skill"}))


README_SAMPLE = """
## Tutorials

#### Build your own `3D Renderer`

* [**C++**: _Ray Tracing in One Weekend_](https://raytracing.github.io/books/RayTracingInOneWeekend.html)
* [**Java / JavaScript**: _Build your own 3D renderer_](https://avik-das.github.io/build-your-own-raytracer/)

#### Build your own `Augmented Reality`

* [**C#**: _How To Unity ARCore_](https://www.youtube.com/playlist?list=abc) [video]

#### Build your own `Empty`

## Contribute
* [**Python**: _Not a tutorial_](https://example.com)
"""


class BuildYourOwnXTests(unittest.TestCase):
    def test_parse_catalog_extracts_categories_languages_and_video_flag(self) -> None:
        categories = parse_catalog(README_SAMPLE)
        self.assertEqual([category["name"] for category in categories], ["3D Renderer", "Augmented Reality"])
        self.assertEqual(categories[0]["items"][1]["languages"], ["Java", "JavaScript"])
        self.assertTrue(categories[1]["items"][0]["video"])

    def test_search_filters_by_language_query_and_category(self) -> None:
        catalog = {"categories": parse_catalog(README_SAMPLE)}
        plugin = BuildYourOwnXPlugin(data_dir=tempfile.gettempdir())
        self.assertEqual(plugin.search(catalog, {"language": "javascript"})["total"], 1)
        self.assertEqual(plugin.search(catalog, {"query": "ray"})["total"], 1)
        self.assertEqual(plugin.search(catalog, {"category": "augmented reality"})["total"], 1)
        with self.assertRaises(ValueError):
            plugin.search(catalog, {"limit": 0})

    def test_refresh_downloads_and_caches_catalog(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=README_SAMPLE))
        with tempfile.TemporaryDirectory() as temp:
            plugin = BuildYourOwnXPlugin(data_dir=temp, transport=transport)
            refreshed = asyncio.run(plugin.invoke("refresh", {}))
            categories = asyncio.run(plugin.invoke("categories", {}))
            self.assertTrue((Path(temp) / "byox" / "catalog.json").is_file())
        self.assertEqual(refreshed["items"], 3)
        self.assertEqual(categories["categories"][0]["count"], 2)


GRAPH = {
    "directed": False,
    "multigraph": False,
    "nodes": [
        {"id": "gateway", "label": "PluginGateway", "source_file": "backend/app/plugins/gateway.py", "community": 0},
        {"id": "main", "label": "create_app", "source_file": "backend/app/main.py", "community": 0},
        {"id": "ollama", "label": "OllamaPlugin", "source_file": "backend/app/plugins/ollama.py", "community": 1},
        {"id": "island", "label": "Unrelated", "community": 2},
    ],
    "links": [
        {"source": "main", "target": "gateway", "relation": "calls", "confidence": "EXTRACTED"},
        {"source": "gateway", "target": "ollama", "relation": "dispatches", "confidence": "INFERRED"},
        {"source": "main", "target": "ghost", "relation": "calls"},
    ],
}


class GraphifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "graphify-out" / "graph.json"
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(GRAPH), encoding="utf-8")
        self.plugin = GraphifyPlugin(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_summary_counts_and_hubs(self) -> None:
        summary = self.plugin.summary({})
        self.assertEqual((summary["nodes"], summary["edges"], summary["communities"]), (4, 2, 3))
        self.assertEqual(summary["god_nodes"][0]["label"], "PluginGateway")

    def test_query_neighbors_and_path(self) -> None:
        self.assertEqual(self.plugin.query({"query": "plugin"})["matches"][0]["id"], "gateway")
        neighbors = self.plugin.neighbors({"node": "create_app", "depth": 2})
        self.assertEqual({node["id"] for node in neighbors["nodes"]}, {"gateway", "ollama"})
        route = self.plugin.path({"source": "create_app", "target": "OllamaPlugin"})
        self.assertEqual([node["id"] for node in route["path"]], ["main", "gateway", "ollama"])
        self.assertFalse(self.plugin.path({"source": "main", "target": "island"})["found"])
        with self.assertRaises(IntegrationNotFoundError):
            self.plugin.neighbors({"node": "zzz-not-there"})

    def test_edges_key_and_missing_graph(self) -> None:
        graph = KnowledgeGraph({"nodes": GRAPH["nodes"], "edges": GRAPH["links"]})
        self.assertEqual(len(graph.edges), 2)
        missing = GraphifyPlugin(Path(self.temp.name) / "none" / "graph.json")
        self.assertFalse(missing.status({})["exists"])
        with self.assertRaises(IntegrationUnavailableError):
            missing.summary({})


class OpenJarvisTests(unittest.TestCase):
    def test_chat_uses_first_model_and_status_reports_unreachable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "qwen2.5-coder:7b"}]})
            body = json.loads(request.content)
            return httpx.Response(200, json={
                "model": body["model"],
                "choices": [{"message": {"role": "assistant", "content": "merhaba"}}],
            })

        plugin = OpenJarvisPlugin(base_url="http://jarvis.test/v1", api_key="", transport=httpx.MockTransport(handler))
        result = asyncio.run(plugin.invoke("chat", {"message": "selam"}))
        self.assertEqual(result, {"model": "qwen2.5-coder:7b", "answer": "merhaba", "provider": "openjarvis"})

        def down(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        offline = OpenJarvisPlugin(base_url="http://jarvis.test/v1", api_key="", transport=httpx.MockTransport(down))
        self.assertFalse(asyncio.run(offline.invoke("status", {}))["reachable"])


if __name__ == "__main__":
    unittest.main()
