from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.plugins.code_graph import CodeGraphPlugin
from app.plugins.diagnostics import DiagnosticsPlugin
from app.plugins.workspace import WorkspacePlugin


class ToolRuntimeExclusionTests(unittest.TestCase):
    private_directories = (".tools", "nested/.TOOLS", "data", "runtimes", "_tmp", "_arsiv")
    private_env_files = (".env", ".env.local", ".freellmapi.env", ".ai-next-cloud.env", "SETTINGS.ENV")

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.root = base / "workspace"
        self.root.mkdir()
        self.data = base / "data"
        (self.root / "source.py").write_text("value = 1\n", encoding="utf-8")
        for folder in self.private_directories:
            directory = self.root / folder
            directory.mkdir(parents=True)
            (directory / "runtime.py").write_text("this is not valid Python !!!", encoding="utf-8")
        for name in self.private_env_files:
            (self.root / name).write_text("TEST_VALUE=not-a-real-secret\n", encoding="utf-8")

    def test_workspace_neither_lists_nor_reads_private_runtime(self) -> None:
        plugin = WorkspacePlugin(self.root, self.data)
        paths = {entry["path"] for entry in plugin._list({})["entries"]}
        self.assertIn("source.py", paths)
        for folder in self.private_directories:
            with self.subTest(folder=folder):
                self.assertFalse(any(path == folder or path.startswith(folder + "/") for path in paths))
                with self.assertRaisesRegex(ValueError, "excluded"):
                    plugin._read({"path": f"{folder}/runtime.py"})
                with self.assertRaisesRegex(ValueError, "excluded"):
                    plugin._safe_path(f"{folder}/new.py")

    def test_workspace_excludes_local_environment_files_but_allows_examples(self) -> None:
        plugin = WorkspacePlugin(self.root, self.data)
        paths = {entry["path"] for entry in plugin._list({})["entries"]}
        for name in self.private_env_files:
            with self.subTest(name=name):
                self.assertNotIn(name, paths)
                with self.assertRaisesRegex(ValueError, "excluded"):
                    plugin._read({"path": name})
        for name in (".env.example", ".ai-next-cloud.env.example"):
            (self.root / name).write_text("TEST_VALUE=\n", encoding="utf-8")
            with self.subTest(example=name):
                self.assertEqual(plugin._safe_path(name), self.root / name)
                self.assertIn(name, {entry["path"] for entry in plugin._list({})["entries"]})

    def test_code_graph_does_not_index_runtime_or_cache(self) -> None:
        result = CodeGraphPlugin(self.root, self.data)._build()
        self.assertEqual(result["scanned_files"], 1)
        self.assertEqual(result["summary"]["parse_errors"], 0)

    def test_diagnostics_does_not_scan_runtime_or_cache(self) -> None:
        plugin = DiagnosticsPlugin(self.root)
        with patch.object(plugin, "_run_ruff", return_value=[]) as ruff:
            result = plugin._scan_workspace()
        self.assertEqual(result["scanned_files"], 1)
        self.assertEqual(result["summary"]["errors"], 0)
        self.assertEqual(ruff.call_args.args[0], [self.root / "source.py"])


if __name__ == "__main__":
    unittest.main()
