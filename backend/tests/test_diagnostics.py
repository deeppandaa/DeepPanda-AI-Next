import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from app.main import create_app
from app.plugins.contracts import PluginManifest
from app.plugins.diagnostics import DiagnosticsPlugin
from app.plugins.gateway import PluginGateway


class FakeDiagnosticsPlugin:
    manifest = PluginManifest("diagnostics", "Diagnostics", "Test scan", ("scan",))

    async def invoke(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        return {
            "read_only": True,
            "scanned_files": 1,
            "summary": {"errors": 0, "warnings": 0, "total": 0},
            "diagnostics": [],
        }


class DiagnosticsPluginTests(unittest.TestCase):
    def test_api_routes_scan_through_plugin_gateway(self) -> None:
        gateway = PluginGateway()
        gateway.register(FakeDiagnosticsPlugin())
        app = create_app(gateway)

        async def send_request() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post("/api/plugins/diagnostics/scan")

        response = asyncio.run(send_request())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["read_only"])
        self.assertEqual(response.json()["scanned_files"], 1)

    def test_scan_reports_python_and_json_syntax_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
            (root / "broken.json").write_text('{"key": }', encoding="utf-8")
            (root / "valid.toml").write_text('name = "ok"\n', encoding="utf-8")

            result = asyncio.run(DiagnosticsPlugin(root).invoke("scan", {}))

        findings = {item["code"]: item for item in result["diagnostics"]}
        self.assertIn("PY-SYNTAX", findings)
        self.assertIn("JSON-SYNTAX", findings)
        self.assertEqual(result["summary"]["errors"], 2)
        self.assertEqual(result["scanned_files"], 3)

    def test_scan_does_not_read_env_files_or_return_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("API_TOKEN=do-not-return", encoding="utf-8")
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")

            result = asyncio.run(DiagnosticsPlugin(root).invoke("scan", {}))

        serialized = json.dumps(result)
        self.assertNotIn("API_TOKEN", serialized)
        self.assertNotIn("do-not-return", serialized)
        self.assertNotIn("def broken", serialized)
        self.assertTrue(result["read_only"])

    def test_scan_skips_excluded_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ignored = root / "node_modules"
            ignored.mkdir()
            (ignored / "broken.json").write_text("{", encoding="utf-8")

            result = asyncio.run(DiagnosticsPlugin(root).invoke("scan", {}))

        self.assertEqual(result["scanned_files"], 0)
        self.assertEqual(result["diagnostics"], [])

    def test_scan_reports_when_time_budget_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.json").write_text('{"ok": true}', encoding="utf-8")
            plugin = DiagnosticsPlugin(root)
            plugin.max_scan_seconds = 0

            result = asyncio.run(plugin.invoke("scan", {}))

        self.assertTrue(result["truncated"])
        self.assertEqual(result["scanned_files"], 0)


if __name__ == "__main__":
    unittest.main()