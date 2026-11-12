from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from desktop.chat_context import ChatCancelled
from desktop.program_delivery import create_delivery


class ProgramDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        self.app = self.output / "dist" / "sample"
        (self.app / "_internal").mkdir(parents=True)
        (self.app / "sample.exe").write_bytes(b"EXE fixture")
        (self.app / "_internal" / "python312.dll").write_bytes(b"DLL fixture")
        (self.app / "_internal" / "LICENSE.txt").write_text("License fixture")
        (self.output / "dependencies.json").write_text('{"dependencies":[]}')
        (self.output / "private.log").write_text("PRIVATE_LOG")
        (self.output / "work").mkdir()
        (self.output / "work" / "source.py").write_text("PRIVATE_SOURCE")

    def create(self, check=lambda: None) -> dict[str, str]:
        return create_delivery(self.output, "sample", check=check)

    def test_complete_portable_tree_and_report_with_exact_hash_manifest_and_no_build_logs(self) -> None:
        result = self.create()
        archive = Path(result["delivery_archive"])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), result["delivery_sha256"])
        manifest = json.loads(Path(result["delivery_manifest"]).read_text())
        self.assertEqual(manifest["executable"], "sample/sample.exe")
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {
                "sample/sample.exe", "sample/_internal/python312.dll",
                "sample/_internal/LICENSE.txt", "dependencies.json", "delivery-manifest.json",
            })
            self.assertEqual(json.loads(bundle.read("delivery-manifest.json")), manifest)
            for entry in manifest["files"]:
                raw = bundle.read(entry["path"])
                self.assertEqual(len(raw), entry["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
                self.assertNotIn(str(self.output), entry["path"])
            self.assertNotIn(b"PRIVATE_LOG", archive.read_bytes())
            self.assertNotIn(b"PRIVATE_SOURCE", archive.read_bytes())
        self.assertEqual(result["executable_sha256"], hashlib.sha256(b"EXE fixture").hexdigest())

    def test_existing_archive_is_never_overwritten(self) -> None:
        first = self.create()
        archive = Path(first["delivery_archive"])
        before = archive.read_bytes()
        with self.assertRaisesRegex(ValueError, "üzerine yazılmaz"):
            self.create()
        self.assertEqual(archive.read_bytes(), before)

    def test_missing_exe_or_report_does_not_produce_deliverable(self) -> None:
        (self.app / "sample.exe").unlink()
        with self.assertRaisesRegex(ValueError, "EXE"):
            self.create()
        (self.app / "sample.exe").write_bytes(b"fixture")
        (self.output / "dependencies.json").unlink()
        with self.assertRaises(OSError):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())
        self.assertFalse((self.output / "sample-windows.zip.partial").exists())

    def test_size_and_entry_limits_reject_without_success_archive(self) -> None:
        with patch("desktop.program_delivery.MAX_BYTES", 1), self.assertRaisesRegex(ValueError, "512 MiB"):
            self.create()
        with patch("desktop.program_delivery.MAX_FILES", 1), self.assertRaisesRegex(ValueError, "5000"):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())

    def test_exact_byte_limit_is_accepted_without_silent_truncation(self) -> None:
        total = sum(path.stat().st_size for path in self.app.rglob("*") if path.is_file())
        total += (self.output / "dependencies.json").stat().st_size
        with patch("desktop.program_delivery.MAX_BYTES", total):
            result = self.create()
        manifest = json.loads(Path(result["delivery_manifest"]).read_text())
        self.assertEqual(sum(entry["bytes"] for entry in manifest["files"]), total)

    def test_cancel_during_streaming_cleans_partial_and_never_advertises_archive(self) -> None:
        def cancel_on_write(*args, **kwargs):
            raise ChatCancelled()
        with patch("zipfile._ZipWriteFile.write", side_effect=cancel_on_write), self.assertRaises(ChatCancelled):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())
        self.assertFalse((self.output / "sample-windows.zip.partial").exists())
        self.assertFalse((self.output / "delivery-manifest.json").exists())

    def test_timeout_during_archive_verification_cleans_partial(self) -> None:
        with patch("zipfile.ZipExtFile.read", side_effect=TimeoutError("fixture deadline")), self.assertRaises(TimeoutError):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())

    def test_deadline_callback_is_checked_while_streaming_not_only_before_start(self) -> None:
        calls = 0

        def check():
            nonlocal calls
            calls += 1
            if (self.output / "sample-windows.zip.partial").exists():
                raise TimeoutError("fixture deadline")
        with self.assertRaises(TimeoutError):
            self.create(check)
        self.assertGreater(calls, 1)
        self.assertFalse((self.output / "sample-windows.zip.partial").exists())
        self.assertFalse((self.output / "sample-windows.zip.partial").exists())

    def test_corrupted_archive_hash_is_rejected(self) -> None:
        original_read = zipfile.ZipExtFile.read

        def corrupt(stream, size=-1):
            raw = original_read(stream, size)
            return b"x" * len(raw)
        with patch("zipfile.ZipExtFile.read", new=corrupt), self.assertRaisesRegex(ValueError, "hash"):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())

    def test_invalid_archive_crc_is_explicit_validation_failure(self) -> None:
        with (
            patch("zipfile.ZipExtFile.read", side_effect=zipfile.BadZipFile("fixture CRC failure")),
            self.assertRaisesRegex(ValueError, "CRC"),
        ):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())

    def test_hardlinked_file_is_rejected(self) -> None:
        os.link(self.app / "sample.exe", self.app / "alias.exe")
        with self.assertRaisesRegex(ValueError, "hardlink"):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction validation")
    def test_junction_dist_root_is_rejected_before_traversal(self) -> None:
        with (
            patch.object(Path, "is_junction", autospec=True, side_effect=lambda path: path == self.app),
            self.assertRaisesRegex(ValueError, "junction"),
        ):
            self.create()
        self.assertFalse((self.output / "sample-windows.zip").exists())
