import asyncio
import tempfile
import unittest
from pathlib import Path

from app.plugins.code_graph import CodeGraphPlugin


class CodeGraphPluginTests(unittest.TestCase):
    def test_build_search_and_path_use_static_python_relations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            data = Path(directory) / "data"
            root.mkdir()
            (root / "demo.py").write_text(
                "def helper():\n    return 1\n\ndef main():\n    return helper()\n",
                encoding="utf-8",
            )
            plugin = CodeGraphPlugin(root, data)

            graph = asyncio.run(plugin.invoke("build", {}))
            search = asyncio.run(plugin.invoke("search", {"query": "helper"}))
            path = asyncio.run(plugin.invoke("path", {"source": "main", "target": "helper"}))

        self.assertEqual(graph["summary"]["functions"], 2)
        self.assertEqual(search["results"][0]["path"], "demo.py")
        self.assertTrue(path["found"])
        self.assertEqual(path["hops"], 1)

    def test_build_reports_syntax_errors_without_executing_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            data = Path(directory) / "data"
            root.mkdir()
            marker = Path(directory) / "executed.txt"
            (root / "broken.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('bad')\ndef broken(:\n    pass\n",
                encoding="utf-8",
            )

            graph = asyncio.run(CodeGraphPlugin(root, data).invoke("build", {}))

        self.assertFalse(marker.exists())
        self.assertEqual(graph["summary"]["parse_errors"], 1)

    def test_path_traverses_local_import_edges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            data = Path(directory) / "data"
            root.mkdir()
            (root / "helpers.py").write_text("def target():\n    return 1\n", encoding="utf-8")
            (root / "main.py").write_text("from helpers import target\n", encoding="utf-8")
            plugin = CodeGraphPlugin(root, data)

            asyncio.run(plugin.invoke("build", {}))
            path = asyncio.run(plugin.invoke("path", {"source": "module:main.py", "target": "target"}))

        self.assertTrue(path["found"])
        self.assertEqual([edge["kind"] for edge in path["edges"]], ["imports", "defines"])


if __name__ == "__main__":
    unittest.main()