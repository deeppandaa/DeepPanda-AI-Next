from __future__ import annotations

import asyncio
import base64
import hashlib
import unittest
from unittest.mock import patch

import capstone
import httpx
from app.main import create_app
from app.plugins.binary_analysis import (
    BinaryAnalysisApprovalRequired,
    BinaryAnalysisPlugin,
)
from app.plugins.gateway import PluginGateway


class BinaryAnalysisPluginTests(unittest.TestCase):
    def test_inspect_requires_explicit_approval(self) -> None:
        async def exercise() -> None:
            with self.assertRaises(BinaryAnalysisApprovalRequired):
                await BinaryAnalysisPlugin().invoke("inspect", {
                    "filename": "sample.exe",
                    "content_base64": base64.b64encode(b"binary bytes").decode("ascii"),
                })

        asyncio.run(exercise())

    def test_api_registers_binary_plugin_and_maps_missing_approval(self) -> None:
        gateway = PluginGateway()
        gateway.register(BinaryAnalysisPlugin())
        app = create_app(gateway)

        async def exercise() -> int:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/plugins/binary_analysis/actions/inspect",
                    json={
                        "payload": {
                            "filename": "sample.exe",
                            "content_base64": base64.b64encode(b"bytes").decode("ascii"),
                        }
                    },
                )
                return response.status_code

        self.assertEqual(asyncio.run(exercise()), 403)

    def test_inspect_bounds_input_and_returns_static_hash_metadata(self) -> None:
        raw = b"bounded PE fixture bytes"
        plugin = BinaryAnalysisPlugin()
        expected = {"format": "PE", "architecture": "AMD64", "bits": 64, "sections": [], "imports": []}

        async def exercise() -> dict[str, object]:
            with patch("app.plugins.binary_analysis.lief.parse", return_value=object()) as parse:
                with patch.object(plugin, "_metadata", return_value=expected):
                    result = await plugin.invoke("inspect", {
                        "approved": True,
                        "filename": "sample.exe",
                        "content_base64": base64.b64encode(raw).decode("ascii"),
                    })
            parse.assert_called_once()
            return result

        result = asyncio.run(exercise())
        self.assertEqual(result["status"], "inspected")
        self.assertTrue(result["static_only"])
        self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["metadata"], expected)

    def test_disassembly_is_bounded_and_reports_addresses(self) -> None:
        plugin = BinaryAnalysisPlugin()
        plugin.max_disassembly_instructions = 2
        code = bytes.fromhex("554889e5c3")

        instructions, truncated = plugin._disassemble_code(
            [(".text", 0x140001000, code)], capstone.CS_ARCH_X86, capstone.CS_MODE_64
        )

        self.assertEqual(len(instructions), 2)
        self.assertEqual(instructions[0]["address"], "0x140001000")
        self.assertEqual(instructions[0]["mnemonic"], "push")
        self.assertTrue(truncated)

    def test_disassembly_starts_at_entrypoint_when_it_is_inside_executable_section(self) -> None:
        plugin = BinaryAnalysisPlugin()
        entrypoint = 0x140001004
        sections = plugin._entrypoint_first(
            [(".text", 0x140001000, b"\xcc" * 4 + bytes.fromhex("554889e5c3"))], entrypoint
        )

        instructions, _ = plugin._disassemble_code(
            sections, capstone.CS_ARCH_X86, capstone.CS_MODE_64
        )

        self.assertEqual(instructions[0]["address"], f"0x{entrypoint:x}")
        self.assertEqual(instructions[0]["mnemonic"], "push")

    def test_function_records_are_bounded_without_inventing_names(self) -> None:
        class FakeFunction:
            def __init__(self, name: str | None, address: int, size: int) -> None:
                self.name = name
                self.address = address
                self.size = size

        plugin = BinaryAnalysisPlugin()
        plugin.max_function_records = 1
        records, truncated = plugin._function_records([
            FakeFunction("entry", 0x1000, 12),
            FakeFunction(None, 0x2000, 8),
        ])

        self.assertEqual(records, [{"name": "entry", "address": "0x1000", "size": 12}])
        self.assertTrue(truncated)

    def test_string_extraction_handles_ascii_utf16_and_caps_output(self) -> None:
        plugin = BinaryAnalysisPlugin()
        raw = b"ASCII sample\x00\x00" + "Wide sample".encode("utf-16le") + b"\x00\x00"

        strings, truncated = plugin._extract_strings(raw, 1)
        all_strings, all_truncated = plugin._extract_strings(raw, 10)

        self.assertEqual(len(strings), 1)
        self.assertTrue(truncated)
        self.assertFalse(all_truncated)
        self.assertEqual({item["encoding"] for item in all_strings}, {"ascii", "utf-16le"})
        self.assertIn("Wide sample", [item["value"] for item in all_strings])

    def test_inspect_rejects_invalid_or_oversized_content_before_parsing(self) -> None:
        plugin = BinaryAnalysisPlugin()

        async def exercise(payload: dict[str, object]) -> None:
            await plugin.invoke("inspect", payload)

        with patch("app.plugins.binary_analysis.lief.parse") as parse:
            with self.assertRaisesRegex(ValueError, "invalid"):
                asyncio.run(exercise({"approved": True, "filename": "x.exe", "content_base64": "!!!"}))
            with self.assertRaisesRegex(ValueError, "size limit"):
                asyncio.run(exercise({
                    "approved": True,
                    "filename": "x.exe",
                    "content_base64": "A" * (BinaryAnalysisPlugin.max_binary_bytes * 4 // 3 + 17),
                }))
        parse.assert_not_called()

    def test_unparseable_binary_is_rejected_without_execution(self) -> None:
        async def exercise() -> None:
            with patch("app.plugins.binary_analysis.lief.parse", return_value=None):
                with self.assertRaisesRegex(ValueError, "could not parse"):
                    await BinaryAnalysisPlugin().invoke("inspect", {
                        "approved": True,
                        "filename": "unknown.bin",
                        "content_base64": base64.b64encode(b"not a supported binary").decode("ascii"),
                    })

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()