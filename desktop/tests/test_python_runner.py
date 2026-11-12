from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from desktop.chat_context import ChatCancelled
from desktop.config import PROJECT_ROOT
from desktop.python_runner import ProcessJob, execution_environment, run_python
from desktop.windows_host import HostError, WindowsHost


@unittest.skipUnless(os.name == "nt", "Windows Job Objects required")
class PythonExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "program.py"
        self.path.write_text("print('hello')\n", encoding="utf-8")
        self.host = WindowsHost(self.root / "operations")
        self.admin = patch.object(self.host, "is_admin", return_value=False)
        self.admin.start()
        self.addCleanup(self.admin.stop)

    def preview(self, **kwargs: object) -> dict:
        return self.host.preview("python_run", {"path": str(self.path), **kwargs})

    def apply(self, preview: dict) -> dict:
        return self.host.apply("python_run", {"plan_id": preview["plan_id"], "approved": True})

    def test_preview_has_source_hash_interpreter_arguments_and_no_execution(self) -> None:
        preview = self.preview(arguments=["--example", "a & b"])
        self.assertIn("print('hello')", preview["source_preview"])
        self.assertEqual(preview["arguments"], ["--example", "a & b"])
        self.assertEqual(len(preview["before"]["script"]["sha256"]), 64)
        self.assertEqual(len(preview["interpreter_sha256"]), 64)
        self.assertTrue(Path(preview["interpreter"]).is_relative_to(PROJECT_ROOT))
        self.assertNotIn("base64", preview["before"]["script"])
        self.assertFalse(preview["reversible"])
        self.assertFalse(self.host.storage.exists())
        with self.assertRaises(HostError):
            self.host.apply("python_run", {"plan_id": preview["plan_id"], "approved": False})

    def test_real_execution_captures_output_arguments_and_literal_shell_metacharacters(self) -> None:
        self.path.write_text(
            "import json,sys\nprint(json.dumps(sys.argv[1:]))\nprint('error stream',file=sys.stderr)\n",
            encoding="utf-8",
        )
        result = self.apply(self.preview(arguments=["a & b", "$(whoami)", '"quoted"', "Türkçe"]))
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(json.loads(result["stdout"]), ["a & b", "$(whoami)", '"quoted"', "Türkçe"])
        self.assertEqual(result["stderr"], "error stream" + os.linesep)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["isolation_mode"], "windows_job_object_process_tree_lifetime_only")
        self.assertFalse(result["sandboxed"])
        record = self.host._record(result["operation_id"])
        self.assertEqual(record["execution"]["exit_code"], 0)
        self.assertEqual(record["execution"]["isolation_mode"], result["isolation_mode"])
        self.assertFalse(record["execution"]["sandboxed"])
        with self.assertRaisesRegex(ValueError, "Yalnız"):
            self.host.preview("rollback", {"operation_id": result["operation_id"]})

    def test_changed_script_is_not_executed_and_plan_is_single_use(self) -> None:
        preview = self.preview()
        self.path.write_text("print('changed')", encoding="utf-8")
        with self.assertRaisesRegex(HostError, "değişmiş"):
            self.apply(preview)
        preview = self.preview()
        self.apply(preview)
        with self.assertRaises(HostError):
            self.apply(preview)

    def test_nonzero_exit_is_failure_with_persistent_output_and_no_retry(self) -> None:
        self.path.write_text("print('before failure')\nraise RuntimeError('expected failure')", encoding="utf-8")
        preview = self.preview()
        with self.assertRaisesRegex(HostError, "expected failure") as error:
            self.apply(preview)
        self.assertEqual(error.exception.status, 502)
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["execution"]["exit_code"], 1)
        self.assertEqual(record["execution"]["stdout"], "before failure" + os.linesep)
        with self.assertRaises(HostError):
            self.apply(preview)

    def test_output_is_bounded_and_truncation_is_explicit(self) -> None:
        self.path.write_text(
            "import sys\nprint('x'*200000)\nprint('y'*200000,file=sys.stderr)", encoding="utf-8",
        )
        result = self.apply(self.preview())
        self.assertEqual(len(result["stdout"]), 32000)
        self.assertEqual(len(result["stderr"]), 32000)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])

    def test_timeout_stops_process_tree_before_descendant_side_effect(self) -> None:
        marker = self.root / "should-not-exist.txt"
        child_pid = self.root / "child.pid"
        child = "import time;from pathlib import Path;time.sleep(3);Path('should-not-exist.txt').write_text('bad')"
        self.path.write_text(
            "import subprocess,sys,time\nfrom pathlib import Path\n"
            f"p=subprocess.Popen([sys.executable,'-I','-c',{child!r}])\n"
            "Path('child.pid').write_text(str(p.pid))\ntime.sleep(30)\n", encoding="utf-8",
        )
        started = time.monotonic()
        preview = self.preview(timeout=1)
        with self.assertRaises(HostError) as error:
            self.apply(preview)
        self.assertEqual(error.exception.status, 504)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(child_pid.exists())
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        api.OpenProcess.restype = ctypes.c_void_p
        api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        api.WaitForSingleObject.restype = ctypes.c_ulong
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.OpenProcess(0x00100000, False, int(child_pid.read_text()))
        if handle:
            try:
                self.assertEqual(api.WaitForSingleObject(handle, 2000), 0)
            finally:
                api.CloseHandle(handle)
        time.sleep(3)
        self.assertFalse(marker.exists())
        self.assertTrue(self.host._record(preview["plan_id"])["execution"]["timed_out"])

    def test_normal_exit_also_stops_background_descendants(self) -> None:
        child = "import time;from pathlib import Path;time.sleep(2);Path('background.txt').write_text('bad')"
        self.path.write_text(
            f"import subprocess,sys\nsubprocess.Popen([sys.executable,'-I','-c',{child!r}])\n",
            encoding="utf-8",
        )
        self.apply(self.preview())
        time.sleep(3)
        self.assertFalse((self.root / "background.txt").exists())

    def test_job_assignment_failure_never_releases_user_code(self) -> None:
        self.path.write_text("from pathlib import Path\nPath('executed.txt').touch()", encoding="utf-8")
        preview = self.preview()
        with (
            patch("desktop.python_runner.ProcessJob.assign", side_effect=OSError("job denied")),
            self.assertRaisesRegex(OSError, "job denied"),
        ):
            self.apply(preview)
        self.assertFalse((self.root / "executed.txt").exists())
        self.assertEqual(self.host._record(preview["plan_id"])["status"], "failed")

    def test_cancel_stops_real_process_tree_keeps_output_and_audits_without_retry(self) -> None:
        cancelled = Event()
        ready = self.root / "child.pid"
        marker = self.root / "should-not-exist.txt"
        child = "import time;from pathlib import Path;time.sleep(3);Path('should-not-exist.txt').touch()"
        self.path.write_text(
            "import subprocess,sys,time\nfrom pathlib import Path\n"
            "print('before cancel',flush=True)\n"
            f"p=subprocess.Popen([sys.executable,'-I','-c',{child!r}])\n"
            "Path('child.pid').write_text(str(p.pid))\ntime.sleep(30)\n", encoding="utf-8",
        )
        observed = Event()

        def cancel_when_running() -> None:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                if cancelled.wait(0.02):
                    return
            if ready.exists():
                observed.set()
            cancelled.set()

        preview = self.preview(timeout=30)
        watcher = Thread(target=cancel_when_running)
        watcher.start()
        started = time.monotonic()
        try:
            with self.assertRaises(ChatCancelled):
                self.host.apply("python_run", {"plan_id": preview["plan_id"], "approved": True}, cancelled=cancelled)
        finally:
            cancelled.set()
            watcher.join(6)
        self.assertTrue(observed.is_set(), "Python child never started; cancellation was not tested during execution")
        self.assertLess(time.monotonic() - started, 3)
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "cancelled")
        self.assertTrue(record["execution"]["cancelled"])
        self.assertFalse(record["execution"]["timed_out"])
        self.assertIn("before cancel", record["execution"]["stdout"])
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        api.OpenProcess.restype = ctypes.c_void_p
        api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        api.WaitForSingleObject.restype = ctypes.c_ulong
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.OpenProcess(0x00100000, False, int(ready.read_text()))
        if handle:
            try:
                self.assertEqual(api.WaitForSingleObject(handle, 2000), 0)
            finally:
                api.CloseHandle(handle)
        time.sleep(3)
        self.assertFalse(marker.exists())
        with self.assertRaises(HostError):
            self.apply(preview)

    def test_precancelled_call_never_spawns_or_consumes_approved_plan(self) -> None:
        preview = self.preview()
        cancelled = Event()
        cancelled.set()
        with patch("desktop.python_runner.subprocess.Popen") as spawn:
            with self.assertRaises(ChatCancelled):
                run_python(
                    Path(preview["interpreter"]), self.path, "", [], 30, PROJECT_ROOT, cancelled=cancelled,
                )
            with self.assertRaises(ChatCancelled):
                self.host.apply("python_run", {"plan_id": preview["plan_id"], "approved": True}, cancelled=cancelled)
        spawn.assert_not_called()
        self.assertIn(preview["plan_id"], self.host._plans)
        self.assertFalse(self.host.storage.exists())

    def test_cancel_during_containment_never_releases_user_code(self) -> None:
        self.path.write_text("from pathlib import Path\nPath('executed.txt').touch()", encoding="utf-8")
        preview = self.preview()
        cancelled = Event()
        assign = ProcessJob.assign

        def assign_and_cancel(job, pid):
            assign(job, pid)
            cancelled.set()

        with patch.object(ProcessJob, "assign", assign_and_cancel), self.assertRaises(ChatCancelled):
            self.host.apply("python_run", {"plan_id": preview["plan_id"], "approved": True}, cancelled=cancelled)
        self.assertFalse((self.root / "executed.txt").exists())
        self.assertEqual(self.host._record(preview["plan_id"])["status"], "cancelled")

    def test_source_is_the_approved_bytes_not_a_late_reopen(self) -> None:
        preview = self.preview()
        approved = base64.b64decode(self.host._plans[preview["plan_id"]]["before"]["script"]["base64"])
        self.assertEqual(approved, self.path.read_bytes())
        from desktop.python_runner import run_python
        self.path.write_text("raise RuntimeError('late replacement')", encoding="utf-8")
        result = run_python(
            Path(preview["interpreter"]), self.path, base64.b64encode(approved).decode(),
            [], 10, PROJECT_ROOT,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "hello" + os.linesep)

    def test_invalid_source_extension_bounds_and_elevated_execution_are_rejected(self) -> None:
        for values in ({"timeout": 0}, {"timeout": 121}, {"arguments": ["x"] * 33},
                       {"arguments": ["x" * 1025]}, {"arguments": "not a list"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.preview(**values)
        self.path.write_text("def broken(", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sözdizimi"):
            self.preview()
        self.path.write_text("print('valid')", encoding="utf-8")
        with patch.object(self.host, "is_admin", return_value=True), self.assertRaises(HostError):
            self.preview()
        with patch("desktop.windows_host.hashlib.file_digest") as digest:
            digest.return_value.hexdigest.return_value = "tampered"
            with self.assertRaisesRegex(ValueError, "hash"):
                self.preview()

    def test_execution_environment_does_not_inherit_credentials_or_python_injection(self) -> None:
        with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture", "PYTHONPATH": "fixture", "OPENAI_API_KEY": "fixture"}):
            env = execution_environment(PROJECT_ROOT)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("PYTHONPATH", env)
        for key in ("TEMP", "PIP_CACHE_DIR", "HF_HOME", "TORCH_HOME"):
            self.assertTrue(Path(env[key]).is_relative_to(PROJECT_ROOT))


if __name__ == "__main__":
    unittest.main()
