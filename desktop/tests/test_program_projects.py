from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock, patch

from desktop.api import ApiClient, ApiError
from desktop.chat_agent import ChatAgent, api_tool_definitions, compact_result
from desktop.chat_context import ChatCancelled
from desktop.config import PROJECT_ROOT, Settings
from desktop.program_projects import ProgramProjects
from desktop.windows_host import HostError, WindowsHost


@unittest.skipUnless(os.name == "nt", "Windows host project execution")
class ProgramProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.host = WindowsHost(self.root / "operations")
        self.host.projects = ProgramProjects(self.root, self.host._atomic)
        patcher = patch.object(self.host, "is_admin", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.host.projects.interpreter = lambda: ProgramProjects(PROJECT_ROOT, self.host._atomic).interpreter()
        self.files = [
            {"path": "app.py", "content": "def add(a,b):\n    return a+b\n"},
            {"path": "test_app.py", "content": (
                "import unittest\nfrom app import add\n"
                "class AppTests(unittest.TestCase):\n"
                "    def test_add(self): self.assertEqual(add(20,22),42)\n"
            )},
            {"path": "README.md", "content": "Addition example; run tests with project_test."},
        ]

    def apply(self, action: str, **kwargs: object) -> dict:
        preview = self.host.preview(action, {"project": "sample", **kwargs})
        return self.host.apply(action, {"plan_id": preview["plan_id"], "approved": True})

    def create(self) -> dict:
        return self.apply("project_create", files=self.files, criteria="20+22=42; unittest must pass")

    def test_multifile_create_is_approved_atomic_and_never_owns_an_existing_directory(self) -> None:
        preview = self.host.preview("project_create", {
            "project": "sample", "files": self.files, "criteria": "Addition",
        })
        self.assertIn("files", preview)
        self.assertFalse((self.root / "projects" / "sample").exists())
        with self.assertRaises(HostError):
            self.host.apply("project_create", {"plan_id": preview["plan_id"], "approved": False})
        result = self.host.apply("project_create", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(len(result["written_files"]), 3)
        self.assertFalse(result["tested"])
        self.assertEqual((self.root / "projects" / "sample" / "app.py").read_text(), self.files[0]["content"])
        with self.assertRaisesRegex(ValueError, "zaten"):
            self.create()
        existing = self.root / "projects" / "existing"
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, "sahiplenilmez"):
            self.host.preview("project_update", {"project": "existing", "files": self.files})

    def test_tree_change_between_preview_and_approval_is_rejected(self) -> None:
        self.create()
        preview = self.host.preview("project_update", {
            "project": "sample", "files": [{"path": "app.py", "content": "answer=42\n"}],
        })
        (self.root / "projects" / "sample" / "new.txt").write_text("concurrent")
        with self.assertRaisesRegex(HostError, "değişmiş"):
            self.host.apply("project_update", {"plan_id": preview["plan_id"], "approved": True})

    def test_acceptance_source_evidence_is_exact_bounded_and_change_checked(self) -> None:
        target = self.root / "projects" / "sample"
        target.mkdir(parents=True)
        (target / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (target / "test_app.py").write_text("def test_add():\n    assert add(20, 22) == 42\n", encoding="utf-8")
        tree = self.host.projects.tree(target)
        evidence = self.host.projects.source_evidence(target, tree)
        self.assertEqual(evidence[0]["path"], "test_app.py")
        self.assertFalse(evidence[0]["truncated"])
        self.assertIn("assert add(20, 22) == 42", evidence[0]["content"])
        self.assertEqual(sum(len(item["content"]) for item in evidence), 81)
        (target / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.host.projects.source_evidence(target, tree)

    def test_update_saves_previous_bytes_and_requires_new_approval(self) -> None:
        self.create()
        preview = self.host.preview("project_update", {
            "project": "sample", "files": [{"path": "app.py", "content": "answer=42\n"}],
        })
        self.assertNotIn("previous_content", preview["before"])
        result = self.host.apply("project_update", {"plan_id": preview["plan_id"], "approved": True})
        record = self.host._record(result["operation_id"])
        old = base64.b64decode(record["before"]["previous_content"]["app.py"]).decode()
        self.assertEqual(old, self.files[0]["content"])
        self.assertIn("-def add", preview["files"][0]["diff"])

    def test_paths_duplicates_private_files_syntax_and_required_tests_are_validated(self) -> None:
        for path in (r"..\evil.py", r"C:\evil.py", r"\\server\evil.py", ".env", ".venv/main.py",
                     "con.py", "app.py.", "a/../evil.py", "app.py:ads", "binary.exe"):
            files = [*self.files, {"path": path, "content": ""}]
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.host.preview("project_create", {"project": "sample", "files": files, "criteria": "test"})
        with self.assertRaisesRegex(ValueError, "Yinelenen"):
            self.host.preview("project_create", {
                "project": "sample", "files": [*self.files, {"path": "APP.py", "content": ""}], "criteria": "test",
            })
        for files in ([{"path": "main.py", "content": "def broken("}], self.files[:1]):
            with self.assertRaises(ValueError):
                self.host.preview("project_create", {"project": "sample", "files": files, "criteria": "test"})
        with self.assertRaisesRegex(ValueError, "sözdizimi"):
            self.host.preview("project_create", {
                "project": "sample", "files": [*self.files, {"path": "broken.PY", "content": "def broken("}],
                "criteria": "test",
            })
        for name in ("con", "../sample", "Sample", "sample.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.host.preview("project_create", {"project": name, "files": self.files, "criteria": "test"})

    def test_isolated_environment_and_real_tests_then_repair(self) -> None:
        criteria_hash = "a" * 64
        created = self.apply(
            "project_create", files=self.files, criteria="20+22=42; unittest must pass",
            criteria_request_sha256=criteria_hash,
        )
        self.assertEqual(created["criteria"], "20+22=42; unittest must pass")
        self.assertEqual(created["criteria_request_sha256"], criteria_hash)
        env = self.apply("project_environment", packages=[])
        self.assertTrue(env["environment_ready"], env)
        self.assertEqual(env["criteria"], created["criteria"])
        self.assertEqual(env["criteria_request_sha256"], criteria_hash)
        manifest = json.loads(self.host.projects.marker("sample").read_text(encoding="utf-8"))
        self.assertEqual(manifest["environment"]["packages"], [])
        self.assertIn("pip==", manifest["environment"]["output"])
        self.assertTrue(self.host.projects.environment("sample").is_relative_to(self.root / ".tools"))
        passed = self.apply("project_test")
        self.assertEqual(passed["status"], "completed")
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["criteria"], created["criteria"])
        self.assertEqual(passed["criteria_request_sha256"], criteria_hash)
        self.assertEqual(passed["tests"]["tests"], 1)
        self.assertEqual(passed["tests"]["test_ids"], ["test_app.AppTests.test_add"])
        self.assertFalse(passed["tests"]["test_ids_truncated"])
        executed_test = passed["tests"]["executed_test_lines"][0]
        self.assertEqual(executed_test["test_id"], "test_app.AppTests.test_add")
        self.assertEqual(executed_test["path"], "test_app.py")
        self.assertIn(4, executed_test["lines"])
        self.assertFalse(executed_test["truncated"])
        self.assertEqual(passed["tests"]["skipped_test_ids"], [])
        self.assertEqual(passed["failure_details"], {"items": [], "omitted": 0})
        self.apply("project_update", files=[{"path": "app.py", "content": "def add(a,b):\n    return a-b\n"}])
        failed = self.apply("project_test")
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["tests"]["failures"], 1)
        details = failed["failure_details"]
        self.assertEqual(details["items"][0]["test_id"], "test_app.AppTests.test_add")
        self.assertEqual(details["items"][0]["kind"], "failure")
        self.assertIn("AssertionError", details["items"][0]["traceback"])
        self.assertEqual(details["omitted"], 0)
        self.assertIn("return a-b", failed["source_files"][0]["content"])
        self.assertFalse(any((self.root / "_tmp" / "temp").glob("program-sample-*")))
        self.assertEqual(self.host._record(failed["operation_id"])["status"], "failed")
        self.apply("project_update", files=[self.files[0]])
        self.assertTrue(self.apply("project_test")["passed"])

    def test_test_time_python_source_mutations_invalidate_success(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        for change in (
            "Path('app.py').write_text('changed=True\\n')",
            "Path('test_app.py').write_text('')",
            "Path('extra.py').write_text('added=True\\n')",
            "Path('app.py').unlink()",
        ):
            with self.subTest(change=change):
                self.apply("project_update", files=[
                    self.files[0],
                    {"path": "test_app.py", "content": (
                        "import unittest\nfrom pathlib import Path\n"
                        "class Mutation(unittest.TestCase):\n"
                        "    def test_mutation(self):\n"
                        f"        {change}\n"
                )}])
                result = self.apply("project_test")
                self.assertTrue(result["tests"]["passed"])
                self.assertFalse(result["passed"])
                self.assertFalse(result["source_integrity"]["unchanged"])
                self.assertTrue(result["source_integrity"]["changed_paths"])

    def test_source_integrity_reports_bounded_paths_and_explicit_omissions(self) -> None:
        self.create()
        target = self.root / "projects" / "sample"
        before = self.host.projects.tree(target)
        for index in range(10):
            (target / f"extra{index}.py").write_text("added=True\n")
        integrity = self.host.projects.source_integrity(target, before)
        self.assertFalse(integrity["unchanged"])
        self.assertEqual(len(integrity["changed_paths"]), 8)
        self.assertEqual(integrity["omitted"], 2)

    def test_failure_details_bound_long_errors_and_report_omissions(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        content = (
            "import unittest\n"
            "class Broken(unittest.TestCase):\n"
            "    def fail_long(self):\n"
            "        raise ValueError('\\u4e00' * 3000)\n"
            "for index in range(12):\n"
            "    setattr(Broken, 'test_' + str(index), Broken.fail_long)\n"
        )
        self.apply("project_update", files=[{"path": "test_app.py", "content": content}])
        failed = self.apply("project_test")
        self.assertEqual(failed["tests"]["errors"], 12)
        details = failed["failure_details"]
        self.assertLessEqual(len(json.dumps(details)), 10000)
        self.assertEqual(len(details["items"]) + details["omitted"], 12)
        self.assertTrue(all(item["truncated"] for item in details["items"]))
        self.assertTrue(all(item["kind"] == "error" for item in details["items"]))

    def test_real_project_test_cancellation_is_not_success_and_cleans_scratch(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        self.apply("project_update", files=[{
            "path": "test_app.py",
            "content": (
                "import unittest,time\nfrom pathlib import Path\n"
                "class SlowTests(unittest.TestCase):\n"
                "    def test_slow(self):\n"
                "        Path('running.txt').touch()\n"
                "        print('test started',flush=True)\n"
                "        time.sleep(30)\n"
            ),
        }])
        ready = self.root / "projects" / "sample" / "running.txt"
        cancelled, observed = Event(), Event()

        def cancel_when_running() -> None:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                if cancelled.wait(0.02):
                    return
            if ready.exists():
                observed.set()
            cancelled.set()

        preview = self.host.preview("project_test", {"project": "sample", "timeout": 30})
        watcher = Thread(target=cancel_when_running)
        watcher.start()
        started = time.monotonic()
        try:
            with self.assertRaises(ChatCancelled):
                self.host.apply("project_test", {"plan_id": preview["plan_id"], "approved": True}, cancelled=cancelled)
        finally:
            cancelled.set()
            watcher.join(6)
        self.assertTrue(observed.is_set())
        self.assertLess(time.monotonic() - started, 3)
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "cancelled")
        self.assertFalse(record["execution"]["passed"])
        self.assertIsNone(record["execution"]["tests"])
        self.assertIn("test started", record["execution"]["stdout"])
        self.assertFalse(any((self.root / "_tmp" / "temp").glob("program-sample-*")))
        self.assertTrue(ready.exists(), "Cancellation must not claim to roll back file side effects")

    def test_cancelled_environment_is_audited_not_ready_and_never_saved_as_installed(self) -> None:
        self.create()
        preview = self.host.preview("project_environment", {"project": "sample"})
        cancelled = Event()
        result = {
            "exit_code": 1, "timed_out": False, "cancelled": True,
            "stdout": "partial install", "stderr": "", "stdout_truncated": False, "stderr_truncated": False,
        }
        with patch("desktop.program_projects.run_python", return_value=result) as run, self.assertRaises(ChatCancelled):
            self.host.apply(
                "project_environment", {"plan_id": preview["plan_id"], "approved": True}, cancelled=cancelled,
            )
        self.assertIs(run.call_args.kwargs["cancelled"], cancelled)
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "cancelled")
        self.assertFalse(record["execution"]["environment_ready"])
        self.assertNotIn("environment", json.loads(self.host.projects.marker("sample").read_text()))

    def test_real_environment_setup_can_be_cancelled_after_it_starts(self) -> None:
        self.create()
        ready = self.host.projects.environment("sample") / "Scripts" / "python.exe"
        cancelled, observed = Event(), Event()

        def cancel_when_running() -> None:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                if cancelled.wait(0.01):
                    return
            if ready.exists():
                observed.set()
            cancelled.set()

        preview = self.host.preview("project_environment", {"project": "sample", "packages": []})
        watcher = Thread(target=cancel_when_running)
        watcher.start()
        try:
            with self.assertRaises(ChatCancelled):
                self.host.apply(
                    "project_environment", {"plan_id": preview["plan_id"], "approved": True}, cancelled=cancelled,
                )
        finally:
            cancelled.set()
            watcher.join(11)
        self.assertTrue(observed.is_set(), "Real environment setup did not start")
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "cancelled")
        self.assertTrue(record["execution"]["cancelled"])
        self.assertFalse(record["execution"]["environment_ready"])
        self.assertNotIn("environment", json.loads(self.host.projects.marker("sample").read_text()))

    def test_no_tests_and_all_skipped_are_not_success(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        for content in (
            "# no tests\n",
            ("import unittest\n@unittest.skip('not implemented')\n"
             "class Tests(unittest.TestCase):\n    def test_missing(self): pass\n"),
        ):
            self.apply("project_update", files=[{"path": "test_app.py", "content": content}])
            result = self.apply("project_test")
            self.assertFalse(result["passed"])
            self.assertEqual(result["status"], "failed")
            if result["tests"] is not None:
                self.assertEqual(result["tests"]["test_ids"], ["test_app.Tests.test_missing"])
                self.assertEqual(result["tests"]["skipped_test_ids"], ["test_app.Tests.test_missing"])

    def test_test_spawned_python_does_not_create_cache_or_block_next_preview(self) -> None:
        self.files[1]["content"] = (
            "import subprocess,sys,unittest\n"
            "class ChildTests(unittest.TestCase):\n"
            "    def test_child_import(self):\n"
            "        result=subprocess.run([sys.executable,'-c','from app import add; assert add(20,22)==42'],"
            "capture_output=True,timeout=10)\n"
            "        self.assertEqual(result.returncode,0,result.stderr)\n"
        )
        self.create()
        self.apply("project_environment", packages=[])
        target = self.root / "projects" / "sample"
        before = self.host.projects.tree(target)
        result = self.apply("project_test")
        self.assertTrue(result["passed"], result)
        self.assertFalse((target / "__pycache__").exists())
        self.assertEqual(self.host.projects.tree(target), before)
        self.host.preview("project_update", {
            "project": "sample", "files": [{"path": "app.py", "content": "answer=42\n"}],
        })

    def test_package_options_urls_and_unpinned_versions_are_rejected(self) -> None:
        self.create()
        for packages in (["requests"], ["-r requirements.txt"], ["https://example.test/a.whl"],
                         ["x==1 --extra-index-url other"], ["x>=1"]):
            with self.subTest(packages=packages), self.assertRaises(ValueError):
                self.host.preview("project_environment", {"project": "sample", "packages": packages})

    def test_package_install_uses_fixed_pypi_wheel_only_flags_and_separate_environment(self) -> None:
        self.create()
        preview = self.host.preview("project_environment", {"project": "sample", "packages": ["six==1.17.0"]})
        self.assertTrue(preview["network_access"])
        with patch("desktop.program_projects.run_python", return_value={
            "exit_code": 0, "timed_out": False, "stdout": "", "stderr": "", "stdout_truncated": False,
        }) as run:
            self.host.apply("project_environment", {"plan_id": preview["plan_id"], "approved": True})
        args = run.call_args.args
        setup = base64.b64decode(args[2]).decode()
        self.assertIn("--only-binary=:all:", setup)
        self.assertIn("https://pypi.org/simple", setup)
        config = json.loads(args[3][0])
        self.assertEqual(config["packages"], ["six==1.17.0"])
        self.assertNotIn(str(PROJECT_ROOT / ".venv"), config["environment"])

    def test_exe_packaging_requires_managed_environment_entrypoint_and_separate_approval(self) -> None:
        self.create()
        with self.assertRaisesRegex(ValueError, "project_environment"):
            self.host.preview("project_package", {"project": "sample", "entrypoint": "app.py"})
        self.apply("project_environment", packages=[])
        for path in (r"..\app.py", "missing.py", "README.md", r"C:\evil.py"):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                self.host.preview("project_package", {"project": "sample", "entrypoint": path})
        preview = self.host.preview("project_package", {
            "project": "sample", "entrypoint": "app.py", "smoke_arguments": ["--smoke"],
        })
        self.assertFalse(preview["network_access"])
        self.assertEqual(preview["required_package"], "pyinstaller==6.16.0")
        self.assertIn("lisans", preview["package_warning"].casefold())
        with self.assertRaises(HostError):
            self.host.apply("project_package", {"plan_id": preview["plan_id"], "approved": False})
        with patch("desktop.program_projects.run_python", return_value={
            "exit_code": 1, "timed_out": False, "cancelled": False, "stdout": "", "stderr": "missing PyInstaller",
        }) as run:
            result = self.host.apply("project_package", {"plan_id": preview["plan_id"], "approved": True})
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["packaged"])
        source = base64.b64decode(run.call_args.args[2]).decode()
        self.assertIn("config['test_source']", source)
        self.assertIn("'-B', '-c'", source)
        self.assertEqual(run.call_args.kwargs["environment"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertIn("'--onedir'", source)
        self.assertNotIn("'install'", source)
        config = json.loads(run.call_args.args[3][0])
        self.assertEqual(config["smoke_arguments"], ["--smoke"])
        self.assertTrue(Path(config["output"]).is_relative_to(self.root / "data" / "program-builds"))
        self.assertEqual(self.host._record(result["operation_id"])["status"], "failed")

    def test_packaging_source_mutation_blocks_delivery_even_if_build_reports_success(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])

        def fake_build(*args: object, **kwargs: object) -> dict:
            config = json.loads(args[3][0])
            output = Path(config["output"])
            exe = output / "dist" / "sample" / "sample.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"fixture")
            (output / "dependencies.json").write_text('{"dependencies":[]}')
            (self.root / "projects" / "sample" / "app.py").write_text("changed=True\n")
            return {"exit_code": 0, "timed_out": False, "cancelled": False,
                    "stdout": 'DEEPPANDA_PACKAGE_RESULT={"smoke_exit_code":0}\n', "stderr": ""}

        with (
            patch("desktop.program_projects.run_python", side_effect=fake_build),
            patch("desktop.program_projects.create_delivery") as delivery,
        ):
            result = self.apply("project_package", entrypoint="app.py")
        delivery.assert_not_called()
        self.assertFalse(result["packaged"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["source_integrity"]["changed_paths"], ["app.py"])
        self.assertIn("integrity_error", result)
        self.assertNotIn("delivery_archive", result)

    def test_exe_result_requires_actual_file_and_uses_unique_outputs(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        outputs = []

        def fake_build(*args: object, **kwargs: object) -> dict:
            config = json.loads(args[3][0])
            output = Path(config["output"])
            outputs.append(output)
            executable = output / "dist" / "sample" / "sample.exe"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"exe fixture")
            (output / "dependencies.json").write_text('{"dependencies":[]}')
            return {"exit_code": 0, "timed_out": False, "cancelled": False,
                    "stdout": 'DEEPPANDA_PACKAGE_RESULT={"smoke_exit_code":0}\n', "stderr": ""}

        before = self.host.projects.tree(self.host.projects.managed("sample"))
        with patch("desktop.program_projects.run_python", side_effect=fake_build):
            for _ in range(2):
                result = self.apply("project_package", entrypoint="app.py")
                self.assertTrue(result["packaged"])
                self.assertEqual(len(result["executable_sha256"]), 64)
                self.assertTrue(Path(result["delivery_archive"]).is_file())
                self.assertTrue(Path(result["delivery_manifest"]).is_file())
                self.assertEqual(len(result["delivery_sha256"]), 64)
        self.assertNotEqual(*outputs)
        self.assertEqual(self.host.projects.tree(self.host.projects.managed("sample")), before)
        with patch("desktop.program_projects.run_python", return_value={
            "exit_code": 0, "timed_out": False, "cancelled": False,
            "stdout": 'DEEPPANDA_PACKAGE_RESULT={"smoke_exit_code":0}\n', "stderr": "",
        }):
            self.assertFalse(self.apply("project_package", entrypoint="app.py")["packaged"])

    def test_timeout_and_nonzero_smoke_are_failed_even_when_executable_exists(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        for timed_out, smoke_code in ((True, 0), (False, 2)):
            def fake_build(
                *args: object, timed_out: bool = timed_out, smoke_code: int = smoke_code, **kwargs: object,
            ) -> dict:
                config = json.loads(args[3][0])
                output = Path(config["output"])
                executable = output / "dist" / "sample" / "sample.exe"
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"exe fixture")
                (output / "dependencies.json").write_text('{"dependencies":[]}')
                return {"exit_code": 0, "timed_out": timed_out, "cancelled": False,
                        "stdout": "DEEPPANDA_PACKAGE_RESULT=" + json.dumps({"smoke_exit_code": smoke_code}),
                        "stderr": ""}
            with self.subTest(timed_out=timed_out, smoke_code=smoke_code), patch(
                "desktop.program_projects.run_python", side_effect=fake_build,
            ):
                result = self.apply("project_package", entrypoint="app.py")
                self.assertFalse(result["packaged"])
                self.assertEqual(result["status"], "failed")
                self.assertNotIn("executable", result)

    def test_archive_timeout_or_cancel_does_not_advertise_successful_build(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])

        def fake_build(*args: object, **kwargs: object) -> dict:
            config = json.loads(args[3][0])
            output = Path(config["output"])
            exe = output / "dist" / "sample" / "sample.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"fixture")
            (output / "dependencies.json").write_text('{"dependencies":[]}')
            return {"exit_code": 0, "timed_out": False, "cancelled": False,
                    "stdout": 'DEEPPANDA_PACKAGE_RESULT={"smoke_exit_code":0}\n', "stderr": ""}

        with (
            patch("desktop.program_projects.run_python", side_effect=fake_build),
            patch("desktop.program_projects.create_delivery", side_effect=TimeoutError("ZIP deadline")),
        ):
            result = self.apply("project_package", entrypoint="app.py")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["packaged"])
        self.assertIn("ZIP deadline", result["delivery_error"])
        self.assertNotIn("delivery_archive", result)
        preview = self.host.preview("project_package", {"project": "sample", "entrypoint": "app.py"})
        with (
            patch("desktop.program_projects.run_python", side_effect=fake_build),
            patch("desktop.program_projects.create_delivery", side_effect=ChatCancelled()),
            self.assertRaises(ChatCancelled),
        ):
            self.host.apply("project_package", {"plan_id": preview["plan_id"], "approved": True})
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "cancelled")
        self.assertFalse(record["execution"]["packaged"])

    def test_exe_cancellation_preserves_failed_evidence_and_no_success(self) -> None:
        self.create()
        self.apply("project_environment", packages=[])
        preview = self.host.preview("project_package", {"project": "sample", "entrypoint": "app.py"})
        with (
            patch("desktop.program_projects.run_python", return_value={
                "exit_code": 1, "timed_out": False, "cancelled": True, "stdout": "partial build", "stderr": "",
            }),
            self.assertRaises(ChatCancelled),
        ):
            self.host.apply("project_package", {"plan_id": preview["plan_id"], "approved": True}, cancelled=Event())
        record = self.host._record(preview["plan_id"])
        self.assertEqual(record["status"], "cancelled")
        self.assertFalse(record["execution"]["packaged"])
        self.assertEqual(record["execution"]["stdout"], "partial build")


class ProgrammingAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.plugins.windows_host import WindowsHostPlugin
        manifest = WindowsHostPlugin.manifest
        self.api = Mock(spec=ApiClient)
        self.api.plugins.return_value = [{
            "id": manifest.plugin_id, "name": manifest.display_name, "description": manifest.description,
            "actions": list(manifest.actions),
        }]
        self.api.stream_chat.return_value = {"message": {"content": "model says done"}, "tools_used": []}
        self.events = []
        self.agent = ChatAgent(
            self.api, Settings(include_vscode_mcp=False), Event(), self.events.append, Mock(return_value=True),
        )
        self.agent._servers = dict
        self.plans = []

    @staticmethod
    def failure(content="broken=True\n") -> dict:
        return {
            "passed": False, "exit_code": 1, "stderr": "AssertionError: actual differs from expected",
            "source_files": [{"path": "app.py", "content": content, "truncated": False}],
        }

    def action(self, action: str, **args: object) -> None:
        self.plans.extend([
            {"tool": "api:windows_host", "arguments": {}, "reason": "program"},
            {"tool": "windows_host." + action, "arguments": {"project": "sample", **args}, "reason": "requested"},
        ])

    def execute_agent(self) -> dict:
        self.api.plan_tool.side_effect = self.plans
        return self.agent.run(
            message="Create and test sample", model="local", workflow="standard", session_id=None,
            paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
        )

    def test_project_schema_has_typed_file_content_and_no_model_approval(self) -> None:
        definition = next(item for item in api_tool_definitions(self.api.plugins.return_value[0])
                          if item["name"] == "windows_host.project_create")
        files = definition["parameters"]["properties"]["files"]
        self.assertEqual(files["type"], "array")
        self.assertEqual(files["items"]["required"], ["path", "content"])
        self.assertNotIn("approved", definition["parameters"]["properties"])

    def test_approved_create_criteria_reach_the_checklist_without_becoming_verified(self) -> None:
        criteria = "- Exact row total\n- Reject malformed input"
        request = "Create a report that totals rows and rejects malformed input."
        criteria_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        self.api.plan_tool.side_effect = [
            {"tool": "api:windows_host", "arguments": {}, "reason": "program"},
            {"tool": "windows_host.project_create", "arguments": {
                "project": "sample", "files": [
                    {"path": "app.py", "content": "value = 1\n"},
                    {"path": "test_app.py", "content": "import unittest\n"},
                    {"path": "README.md", "content": "Sample\n"},
                ], "criteria": criteria,
            }, "reason": "requested"},
            {"tool": None, "arguments": {}, "reason": "done"},
        ]
        with patch.object(self.agent, "_api_action", return_value={
            "project": "sample", "path": "projects/sample", "tested": False, "criteria": criteria,
            "criteria_request_sha256": criteria_hash,
        }) as host_action:
            result = self.agent.run(
                message=request,
                model="local", workflow="standard", session_id=None, paths=[], mode="agent",
                tool_results=[], context_cloud_approved=False,
            )
        payload = self.api.stream_chat.call_args.args[0]
        create = next(item for item in payload["tool_results"] if item["name"].endswith("project_create"))
        self.assertEqual(create["approved_criteria"], criteria)
        self.assertEqual(create["criteria_request_sha256"], criteria_hash)
        self.assertEqual(host_action.call_args.args[2]["criteria_request_sha256"], criteria_hash)
        self.assertEqual(result["program_verification"]["criteria_request_sha256"], criteria_hash)
        self.assertEqual([item["status"] for item in result["program_verification"]["criteria"]],
                         ["not_verified", "not_verified"])
        self.assertFalse(result["program_verification"]["criteria_coverage_verified"])

    def test_independent_review_is_advisory_and_success_requires_second_real_test(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "review.report", "arguments": {
                "root_cause": "wrong operator", "recommended_change": "fix implementation", "checks": ["same test"],
                "source_evidence": [{"path": "app.py", "quote": "broken=True"}],
                "test_conflicts": [],
            }},
            {"tool": "windows_host.project_update", "arguments": {
                "project": "sample", "files": [{"path": "app.py", "content": "fixed=True\n"}],
            }},
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
        ]
        with patch.object(self.agent, "_api_action", side_effect=[
            self.failure(), {"written_files": ["app.py"]},
            {"passed": True, "tests": {"tests": 1}}, {"passed": True, "tests": {"tests": 1}},
        ]) as actions:
            results = self.agent._tools("Use project_test for sample", "primary:local", "", [], [])
        self.assertEqual(actions.call_count, 4)
        review = next(r for r in results if r["name"] == "planner / independent review")
        self.assertTrue(review["result"]["advisory_only"])
        self.assertEqual(self.api.plan_tool.call_args_list[1].args[3], "reviewer:local")
        self.assertEqual(self.api.plan_tool.call_args_list[2].args[3], "primary:local")
        self.assertIn("Independent review", self.api.plan_tool.call_args_list[2].args[0])
        self.assertEqual([r["status"] for r in results[-2:]], ["completed", "completed"])

    def test_passing_tests_receive_separate_advisory_criteria_review_with_exact_source_quotes(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "acceptance.review", "arguments": {
                "summary": "The requirement is linked to a test but not independently verified.",
                "request_coverage": {"status": "no_obvious_gaps", "omissions": []},
                "criteria": [{
                    "id": "C1", "assessment": "test_linked", "rationale": "The assertion checks the sum.",
                    "evidence": [{
                        "path": "test_app.py",
                        "quote": "def test_add():\n    assert add(20, 22) == 42",
                        "test_id": "test_app.test_add",
                    }],
                }],
                "findings": [],
                "source_evidence": [{
                    "path": "app.py", "quote": "def add(a, b):\n    return a + b",
                }],
            }},
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
        ]
        evidence = {
            "passed": True, "tests": {
                "tests": 1, "test_ids": ["test_app.test_add"], "test_ids_truncated": False,
                "skipped_test_ids": [], "skipped_test_ids_truncated": False,
                "executed_test_lines": [{
                    "test_id": "test_app.test_add", "path": "test_app.py",
                    "lines": [1, 2], "truncated": False,
                }],
            }, "project": "sample",
            "criteria": "- Add values",
            "criteria_request_sha256": hashlib.sha256(
                b"Use project_test for sample: Add values, expected 42."
            ).hexdigest(),
            "source_integrity": {"unchanged": True, "changed_paths": [], "omitted": 0},
            "source_files": [
                {"path": "app.py", "content": "def add(a, b):\n    return a + b\n", "truncated": False},
                {"path": "test_app.py", "content": "def test_add():\n    assert add(20, 22) == 42\n", "truncated": False},
            ],
        }
        with patch.object(self.agent, "_api_action", side_effect=[evidence, {"passed": True}]) as actions:
            results = self.agent._tools(
                "Use project_test for sample: Add values, expected 42.",
                "primary:local", "", [], [],
            )
        self.assertEqual(actions.call_count, 2)
        review = next(item for item in results if item["name"] == "planner / independent acceptance review")
        self.assertEqual(review["status"], "completed")
        self.assertTrue(review["result"]["advisory_only"])
        self.assertFalse(review["result"]["criteria_coverage_verified"])
        self.assertEqual(review["result"]["request_coverage_status"], "no_obvious_gaps")
        self.assertEqual(review["result"]["original_requirements_status"], "available")
        self.assertEqual(review["result"]["report"]["criteria"][0]["assessment"], "test_linked")
        self.assertEqual(self.api.plan_tool.call_args_list[1].args[3], "reviewer:local")
        self.assertEqual(self.api.plan_tool.call_args_list[0].args[3], "primary:local")

    def test_invalid_acceptance_review_citation_is_reported_without_repairing_or_hiding_test_result(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "acceptance.review", "arguments": {
                "summary": "The requirement is covered.",
                "request_coverage": {"status": "no_obvious_gaps", "omissions": []},
                "criteria": [{
                    "id": "C1", "assessment": "test_linked", "rationale": "A test checks addition.",
                    "evidence": [{"path": "test_app.py", "quote": "assert add(2, 3) == 5"}],
                }],
                "findings": [],
                "source_evidence": [{"path": "app.py", "quote": "def add(a, b): return a + b"}],
            }},
        ]
        evidence = {
            "passed": True, "tests": {"tests": 1}, "project": "sample", "criteria": "- Add values",
            "criteria_request_sha256": hashlib.sha256(b"Use project_test for sample: Add values").hexdigest(),
            "source_integrity": {"unchanged": True, "changed_paths": [], "omitted": 0},
            "source_files": [
                {"path": "app.py", "content": "def add(a, b):\n    return a + b\n", "truncated": False},
                {"path": "test_app.py", "content": "def test_add():\n    assert add(2, 3) == 5\n", "truncated": False},
            ],
        }
        with patch.object(self.agent, "_api_action", side_effect=[evidence, {"passed": True}]) as actions:
            result = self.agent.run(
                message="Use project_test for sample: Add values",
                model="primary:local", workflow="standard", session_id=None,
                paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
            )
        self.assertEqual(actions.call_count, 2)
        self.assertFalse(any(call.args[1] == "project_update" for call in actions.call_args_list))
        review = next(
            item for item in result["tools_used"]
            if item["name"] == "planner / independent acceptance review"
        )
        self.assertEqual(review["status"], "failed")
        self.assertTrue(result["program_verification"]["tests_passed"])
        self.assertEqual(result["program_verification"]["requirements_status"], "not_verified")

    def test_confirmation_failure_or_rejection_cannot_claim_passed(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        for confirmation in ({"passed": False}, ApiError(403, "confirmation rejected")):
            with self.subTest(confirmation=confirmation):
                self.api.plan_tool.side_effect = [
                    {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
                ]
                with patch.object(self.agent, "_api_action", side_effect=[{"passed": True}, confirmation]):
                    result = self.agent.run(
                        message="Use project_test for sample", model="primary:local",
                        workflow="standard", session_id=None, paths=[], mode="agent",
                        tool_results=[], context_cloud_approved=False,
                    )
                self.assertFalse(result["program_verification"]["tests_passed"])
                self.assertEqual(result["tools_used"][-1]["status"], "failed")

    def test_explicit_delivery_continues_after_confirmed_tests_in_same_turn(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_environment", "arguments": {
                "project": "sample", "packages": ["pyinstaller==6.16.0"],
            }},
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "windows_host.project_package", "arguments": {
                "project": "sample", "entrypoint": "app.py", "smoke_arguments": ["--help"],
            }},
        ]
        with patch.object(self.agent, "_api_action", side_effect=[
            {"environment_ready": True},
            {"passed": True, "tests": {"tests": 1}},
            {"passed": True, "tests": {"tests": 1}},
            {"packaged": True},
        ]) as actions:
            result = self.agent.run(
                message="Use project_test for sample then project_package app.py with --help.",
                model="primary:local", workflow="standard", session_id=None,
                paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
            )
        self.assertEqual(actions.call_count, 4)
        self.assertTrue(result["package_verification"]["verified"])
        self.assertEqual(actions.call_args_list[0].args[:3], (
            "windows_host", "project_environment", {"project": "sample", "packages": ["pyinstaller==6.16.0"]},
        ))
        self.assertTrue(result["program_verification"]["tests_passed"])
        environment_schema = self.api.plan_tool.call_args_list[0].args[1][0]["parameters"]
        self.assertEqual(environment_schema["properties"]["packages"]["contains"], {"const": "pyinstaller==6.16.0"})

    def test_delivery_never_runs_after_environment_or_confirmation_failure(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        for outputs in (
            [{"environment_ready": False}],
            [{"environment_ready": True}, {"passed": True}, {"passed": False}],
            [{"environment_ready": True}, {"passed": True}, ApiError(403, "confirmation rejected")],
        ):
            with self.subTest(outputs=outputs):
                self.api.stream_chat.return_value = {"message": {"content": "done"}}
                self.api.plan_tool.side_effect = [
                    {"tool": "windows_host.project_environment", "arguments": {
                        "project": "sample", "packages": ["pyinstaller==6.16.0"],
                    }},
                    {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
                ]
                with patch.object(self.agent, "_api_action", side_effect=outputs) as actions:
                    result = self.agent.run(
                        message="Use project_test for sample then project_package app.py with --help.",
                        model="primary:local", workflow="standard", session_id=None,
                        paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
                    )
                self.assertEqual(actions.call_count, len(outputs))
                self.assertNotIn("package_verification", result)
                self.assertFalse(result["program_verification"]["tests_passed"])

    def test_delivery_requires_pinned_packager_before_host_installation(self) -> None:
        self.api.plan_tool.return_value = {
            "tool": "windows_host.project_environment", "arguments": {"project": "sample", "packages": []},
        }
        with patch.object(self.agent, "_api_action") as actions, self.assertRaisesRegex(ValueError, "PyInstaller"):
            self.agent._tools("Use project_test then project_package sample", "local", "", [], [])
        actions.assert_not_called()

    def test_mentioning_or_declining_packaging_does_not_install_or_deliver(self) -> None:
        for message in (
            "Use project_test for sample; do not use project_package.",
            "Use project_test for sample. Explain what project_package does without running it.",
            "Use project_test for sample then do not call project_package.",
        ):
            with self.subTest(message=message):
                self.api.plan_tool.return_value = {
                    "tool": "windows_host.project_test", "arguments": {"project": "sample"},
                }
                with patch.object(self.agent, "_api_action", return_value={"passed": True}) as actions:
                    results = self.agent._tools(message, "local", "", [], [])
                self.assertEqual(actions.call_count, 1)
                self.assertEqual(actions.call_args.args[1], "project_test")
                self.assertTrue(results[-1]["result"]["passed"])

    def test_delivery_retains_two_repairs_and_fits_eight_planned_steps(self) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_create", "arguments": {"project": "sample", "files": []}},
            {"tool": "windows_host.project_environment", "arguments": {
                "project": "sample", "packages": ["pyinstaller==6.16.0"],
            }},
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "windows_host.project_update", "arguments": {
                "project": "sample", "files": [{"path": "app.py", "content": "fixed=1\n"}],
            }},
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "windows_host.project_update", "arguments": {
                "project": "sample", "files": [{"path": "app.py", "content": "fixed=2\n"}],
            }},
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "windows_host.project_package", "arguments": {"project": "sample", "entrypoint": "app.py"}},
        ]
        with patch.object(self.agent, "_api_action", side_effect=[
            {"written_files": ["app.py"]}, {"environment_ready": True}, self.failure(),
            {"written_files": ["app.py"]}, self.failure("fixed=1\n"),
            {"written_files": ["app.py"]}, {"passed": True}, {"packaged": True},
        ]) as actions:
            results = self.agent._tools("Use project_create sample then project_package", "local", "", [], [])
        self.assertEqual(actions.call_count, 8)
        self.assertTrue(results[-1]["result"]["packaged"])

    def test_unavailable_cloud_same_or_invalid_reviewer_blocks_writing(self) -> None:
        self.api.models.return_value = {"models": []}
        for reviewer in ("missing:local", "cloud:nvidia", "primary:local"):
            with self.subTest(reviewer=reviewer):
                self.agent.settings.program_review_model = reviewer
                self.api.plan_tool.side_effect = [
                    {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
                ]
                with patch.object(self.agent, "_api_action", return_value=self.failure()) as actions:
                    results = self.agent._tools("Use project_test for sample", "primary:local", "", [], [])
                self.assertEqual(actions.call_count, 1)
                self.assertEqual(results[-1]["status"], "failed")

    def test_invalid_review_schema_blocks_writing(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "review.report", "arguments": {"approved": True}},
        ]
        with patch.object(self.agent, "_api_action", return_value=self.failure()) as actions:
            results = self.agent._tools("Use project_test for sample", "primary:local", "", [], [])
        self.assertEqual(actions.call_count, 1)
        self.assertEqual(results[-1]["status"], "failed")

    def test_fabricated_review_source_is_recorded_and_stops_before_write(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        report = {
            "root_cause": "invented", "recommended_change": "fix", "checks": [],
            "source_evidence": [{"path": "app.py", "quote": "imaginary_function()"}],
            "test_conflicts": [],
        }
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "review.report", "arguments": report},
        ]
        with patch.object(self.agent, "_api_action", return_value=self.failure()) as actions:
            results = self.agent._tools("Use project_test for sample", "primary:local", "", [], [])
        self.assertEqual(actions.call_count, 1)
        self.assertEqual(results[-2]["status"], "failed")
        self.assertEqual(results[-2]["result"]["report"], report)
        self.assertIn("imaginary_function()", results[-2]["result"]["error"])

    def test_automatic_primary_cannot_silently_review_itself(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
        ]
        with patch.object(self.agent, "_api_action", return_value=self.failure()) as actions:
            results = self.agent._tools("Use project_test for sample", None, "", [], [])
        self.assertEqual(actions.call_count, 1)
        self.assertEqual(results[-1]["status"], "failed")
        self.assertIn("açıkça", results[-1]["result"]["error"])

    def test_cancellation_during_review_prevents_update_or_confirmation(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}

        def plan(message, tools, context, model):
            if tools[0]["name"] == "review.report":
                self.agent.cancelled.set()
                return {"tool": "review.report", "arguments": {
                    "root_cause": "cause", "recommended_change": "fix", "checks": [],
                    "source_evidence": [{"path": "app.py", "quote": "broken=True"}],
                    "test_conflicts": [],
                }}
            return {"tool": "windows_host.project_test", "arguments": {"project": "sample"}}

        self.api.plan_tool.side_effect = plan
        with patch.object(self.agent, "_api_action", return_value=self.failure()) as actions, self.assertRaises(
            ChatCancelled,
        ):
            self.agent._tools("Use project_test for sample", "primary:local", "", [], [])
        self.assertEqual(actions.call_count, 1)

    def test_integrated_review_stops_at_two_repairs_without_third_review(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        plans = [{"tool": "windows_host.project_test", "arguments": {"project": "sample"}}]
        for index in range(2):
            plans.extend([
                {"tool": "review.report", "arguments": {
                    "root_cause": "cause", "recommended_change": "fix", "checks": [],
                    "source_evidence": [{"path": "app.py", "quote": "broken=True" if index == 0 else "attempt=0\n"}],
                    "test_conflicts": [],
                }},
                {"tool": "windows_host.project_update", "arguments": {
                    "project": "sample", "files": [{"path": "app.py", "content": f"attempt={index}\n"}],
                }},
                {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            ])
        self.api.plan_tool.side_effect = plans
        with patch.object(self.agent, "_api_action", side_effect=[
            self.failure(), {"written_files": ["app.py"]},
            self.failure("attempt=0\n"), {"written_files": ["app.py"]}, self.failure("attempt=1\n"),
        ]) as actions:
            results = self.agent._tools("Use project_test for sample", "primary:local", "", [], [])
        self.assertEqual(actions.call_count, 5)
        self.assertEqual(self.api.plan_tool.call_count, 7)
        self.assertFalse(results[-1]["result"]["passed"])
        context = json.loads(self.api.plan_tool.call_args_list[4].args[2])
        self.assertIsNone(context["repair_history"][0]["before_tests"])
        self.assertIn("+attempt=0", context["repair_history"][0]["changes"][0]["diff"])

    def test_reported_test_contract_conflict_stops_without_code_or_test_changes(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.models.return_value = {"models": [{"name": "reviewer:local"}]}
        report = {
            "root_cause": "Incorrect expected sum", "recommended_change": "Request review of the test",
            "checks": ["Recompute expected output from the inputs"],
            "source_evidence": [{"path": "test_app.py", "quote": "assert 90 + 165 == 150"}],
            "test_conflicts": [{"test_id": "test_app.Checks.test_add", "explanation": "Expected output contradicts input"}],
        }
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}},
            {"tool": "review.report", "arguments": report},
        ]
        evidence = self.failure()
        evidence["failure_details"] = {"items": [{"test_id": "test_app.Checks.test_add"}], "omitted": 0}
        evidence["source_files"].append({
            "path": "test_app.py", "content": "assert 90 + 165 == 150\n", "truncated": False,
        })
        with patch.object(self.agent, "_api_action", return_value=evidence) as actions:
            results = self.agent._tools("Use project_test for sample; exact sum required", "primary:local", "", [], [])
        self.assertEqual(actions.call_count, 1)
        self.assertEqual(self.api.plan_tool.call_count, 2)
        self.assertEqual(results[-1]["name"], "planner / test conflict")
        self.assertEqual(results[-1]["status"], "failed")
        self.assertIn("exact sum required", self.api.plan_tool.call_args.args[0])
        self.assertEqual(results[-1]["result"]["conflicts"], report["test_conflicts"])

    def test_create_environment_failed_test_update_retest_is_bounded_and_verified(self) -> None:
        self.action("project_create", files=[{"path": "app.py", "content": ""}], criteria="test")
        self.action("project_environment", packages=[])
        self.action("project_test")
        self.action("project_update", files=[{"path": "app.py", "content": "fixed"}])
        self.action("project_test")
        with patch.object(self.agent, "_api_action", side_effect=[
            {"written_files": ["app.py"]}, {"environment_ready": True},
            self.failure(), {"written_files": ["app.py"]},
            {"passed": True, "exit_code": 0, "tests": {"tests": 1}},
        ]) as actions:
            result = self.execute_agent()
        self.assertEqual(actions.call_count, 5)
        self.assertTrue(result["program_verification"]["tests_passed"])
        self.assertEqual([item["status"] for item in result["tools_used"]],
                         ["completed", "completed", "failed", "completed", "completed"])

    def test_failed_test_cannot_be_retried_without_update_even_with_different_arguments(self) -> None:
        self.action("project_test", timeout=10)
        self.action("project_test", timeout=11)
        with (
            patch.object(self.agent, "_api_action", return_value={"passed": False, "exit_code": 1}) as actions,
            self.assertRaisesRegex(ValueError, "geçersiz"),
        ):
            self.execute_agent()
        self.assertEqual(actions.call_count, 1)

    def test_repair_uses_raw_sources_not_compact_display_and_respects_planner_limits(self) -> None:
        from app.chat_planning import ToolPlanRequest

        self.action("project_test")
        self.action("project_update", files=[{"path": "app.py", "content": "fixed=True\n"}])
        self.action("project_test")
        failure = {
            **self.failure(), "stdout": "x" * 32000,
            "stderr": "AssertionError: expected 15, got 5",
        }
        with patch.object(self.agent, "_api_action", side_effect=[
            failure, {"written_files": ["app.py"]}, {"passed": True, "exit_code": 0},
        ]):
            self.execute_agent()
        repair_call = next(
            call for call in self.api.plan_tool.call_args_list
            if call.args[1][0]["name"] == "windows_host.project_update"
        )
        message, definitions, context, model = repair_call.args
        parsed = json.loads(context)
        self.assertEqual(parsed["source_files"], failure["source_files"])
        self.assertEqual(parsed["stderr"], failure["stderr"])
        ToolPlanRequest(message=message, tools=definitions, context=context, model=model)

    def test_automatic_repair_guard_rejects_test_readme_and_noop_before_host_action(self) -> None:
        for path, content in (
            ("test_app.py", "pass"), ("README.md", "fixed"),
            ("app.py", "# comment only\nbroken=True\n"),
        ):
            with self.subTest(path=path):
                self.plans = []
                self.action("project_test")
                self.action("project_update", files=[{"path": path, "content": content}])
                with patch.object(self.agent, "_api_action", return_value=self.failure()) as actions:
                    result = self.execute_agent()
                self.assertEqual(actions.call_count, 1)
                self.assertEqual(result["tools_used"][-1]["name"], "planner / repair")
                self.assertEqual(result["tools_used"][-1]["status"], "failed")
                self.assertFalse(result["program_verification"]["tests_passed"])

    def test_explicit_manual_project_update_can_still_edit_tests(self) -> None:
        self.action("project_update", files=[{"path": "test_app.py", "content": "assert True\n"}])
        self.action("project_test")
        with patch.object(self.agent, "_api_action", side_effect=[
            {"written_files": ["test_app.py"]}, {"passed": True, "exit_code": 0},
        ]) as actions:
            result = self.execute_agent()
        self.assertEqual(actions.call_count, 2)
        self.assertTrue(result["program_verification"]["tests_passed"])

    def test_bad_json_planning_surfaces_failure_without_executing_or_repeating(self) -> None:
        self.api.plan_tool.side_effect = ApiError(422, "Tool planner returned invalid JSON.")
        result = self.agent.run(
            message="Create app", model=None, workflow="standard", session_id=None,
            paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
        )
        self.api.action.assert_not_called()
        self.assertEqual(result["tools_used"][0]["status"], "failed")
        self.assertEqual(self.api.plan_tool.call_count, 1)

    def test_explicit_project_tool_routes_to_host_without_model_group_guess(self) -> None:
        self.api.plan_tool.side_effect = [
            {"tool": "windows_host.project_test", "arguments": {"project": "sample"}, "reason": "explicit"},
        ]
        with patch.object(self.agent, "_api_action", return_value={"passed": True, "exit_code": 0}):
            result = self.agent.run(
                message="Use project_test for sample", model=None, workflow="standard", session_id=None,
                paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
            )
        self.assertEqual(self.api.plan_tool.call_count, 1)
        self.assertTrue(result["program_verification"]["tests_passed"])
        definitions = self.api.plan_tool.call_args.args[1]
        self.assertEqual([tool["name"] for tool in definitions], ["windows_host.project_test"])

    def test_large_test_output_preserves_structured_verification(self) -> None:
        compact = compact_result({
            "stdout": "a" * 32000, "passed": True, "tests": {"tests": 3},
            "project": "sample", "exit_code": 0, "timed_out": False,
            "isolation_mode": "windows_job_object_process_tree_lifetime_only", "sandboxed": False,
        })
        self.assertTrue(compact["passed"])
        self.assertEqual(compact["tests"]["tests"], 3)
        self.assertEqual(compact["isolation_mode"], "windows_job_object_process_tree_lifetime_only")
        self.assertFalse(compact["sandboxed"])
        self.assertLessEqual(len(json.dumps(compact, ensure_ascii=False)), 5000)

    def test_large_test_line_trace_is_omitted_from_bounded_chat_summary(self) -> None:
        test_ids = [f"test_app.TestCase.test_{index}" for index in range(40)]
        compact = compact_result({
            "stdout": "a" * 32000, "passed": True,
            "tests": {
                "tests": 40, "test_ids": test_ids, "test_ids_truncated": False,
                "skipped_test_ids": [], "skipped_test_ids_truncated": False,
                "executed_test_lines": [{
                    "test_id": test_id, "path": "test_app.py",
                    "lines": list(range(1, 201)), "truncated": False,
                } for test_id in test_ids],
            },
            "project": "sample", "exit_code": 0, "timed_out": False,
        })
        self.assertTrue(compact["tests"]["executed_test_lines_omitted_from_chat_summary"])
        self.assertTrue(compact["tests"]["test_ids_truncated"])
        self.assertLessEqual(len(json.dumps(compact, ensure_ascii=False)), 5000)

    def test_package_evidence_survives_large_output(self) -> None:
        compact = compact_result({
            "stdout": "a" * 32000, "packaged": True, "smoke_test": {"smoke_exit_code": 0},
            "project": "sample", "executable": r"F:\output\sample.exe", "exit_code": 0, "timed_out": False,
            "delivery_archive": r"F:\output\sample-windows.zip", "delivery_sha256": "a" * 64,
            "delivery_manifest": r"F:\output\delivery-manifest.json",
            "isolation_mode": "windows_job_object_process_tree_lifetime_only", "sandboxed": False,
        })
        self.assertTrue(compact["packaged"])
        self.assertEqual(compact["smoke_test"]["smoke_exit_code"], 0)
        self.assertEqual(compact["isolation_mode"], "windows_job_object_process_tree_lifetime_only")
        self.assertFalse(compact["sandboxed"])
        self.assertEqual(compact["delivery_archive"], r"F:\output\sample-windows.zip")
        self.assertEqual(compact["delivery_sha256"], "a" * 64)
        self.assertLessEqual(len(json.dumps(compact, ensure_ascii=False)), 5000)

    def test_explicit_package_reports_verified_status_instead_of_trusting_model_success(self) -> None:
        self.api.plan_tool.return_value = {
            "tool": "windows_host.project_package",
            "arguments": {"project": "sample", "entrypoint": "app.py"}, "reason": "explicit",
        }
        for packaged in (False, True):
            with self.subTest(packaged=packaged), patch.object(
                self.agent, "_api_action", return_value={"packaged": packaged, "exit_code": 0 if packaged else 1},
            ):
                result = self.agent.run(
                    message="Use project_package for sample", model=None, workflow="standard", session_id=None,
                    paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
                )
                self.assertEqual(result["package_verification"]["verified"], packaged)
                self.assertEqual(result["tools_used"][0]["status"], "completed" if packaged else "failed")
                self.assertIn("GEÇTİ" if packaged else "BAŞARISIZ", result["message"]["content"])

    def test_program_repairs_stop_after_two_approved_updates(self) -> None:
        self.action("project_test")
        for index in range(3):
            self.action("project_update", files=[{"path": "app.py", "content": f"attempt={index}\n"}])
            self.action("project_test")
        with patch.object(self.agent, "_api_action", side_effect=[
            self.failure(), {"written_files": ["app.py"]},
            self.failure("attempt=0\n"), {"written_files": ["app.py"]}, self.failure("attempt=1\n"),
        ]) as actions:
            result = self.execute_agent()
        self.assertEqual(actions.call_count, 5)
        self.assertFalse(result["program_verification"]["tests_passed"])

    def test_full_program_turn_with_previous_large_outputs_stays_within_api_budget(self) -> None:
        from app.chat_context import ChatContextRequest

        self.action("project_test")
        previous = [
            {"name": f"manual-{index}", "status": "completed", "result": {"output": "x" * 4900}}
            for index in range(5)
        ]
        generated = [{"name": "api:windows_host / windows_host.project_update", "status": "completed",
                      "result": {"output": "y" * 4900}} for _ in range(7)]
        generated.append({"name": "api:windows_host / windows_host.project_test", "status": "completed",
                          "result": {"passed": True, "tests": {"tests": 1}, "stdout": "z" * 4900}})
        with patch.object(self.agent, "_tools", return_value=generated):
            result = self.agent.run(
                message="Create app", model="local", workflow="standard", session_id=None,
                paths=[], mode="agent", tool_results=previous, context_cloud_approved=False,
            )
        self.assertTrue(result["program_verification"]["tests_passed"])
        payload = self.api.stream_chat.call_args.args[0]
        self.assertLessEqual(len(json.dumps(payload["tool_results"], ensure_ascii=False)), 48000)
        self.assertEqual(len(ChatContextRequest(tool_results=payload["tool_results"]).tool_results), 8)

    def test_source_mutation_stops_before_reviewer_or_repair(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.api.plan_tool.return_value = {
            "tool": "windows_host.project_test", "arguments": {"project": "sample"},
        }
        evidence = {
            **self.failure(), "source_integrity": {"unchanged": False, "changed_paths": ["test_app.py"]},
        }
        with patch.object(self.agent, "_api_action", return_value=evidence) as actions:
            result = self.agent.run(
                message="Use project_test for sample", model="primary:local", workflow="standard", session_id=None,
                paths=[], mode="agent", tool_results=[], context_cloud_approved=False,
            )
        self.assertEqual(actions.call_count, 1)
        self.assertEqual(self.api.plan_tool.call_count, 1)
        self.api.models.assert_not_called()
        self.assertFalse(result["program_verification"]["tests_passed"])

    def test_previous_or_lookalike_results_cannot_certify_current_turn(self) -> None:
        passed = {"status": "completed", "result": {"passed": True, "packaged": True}}
        previous = [
            {**passed, "name": "api:windows_host / windows_host.project_test"},
            {**passed, "name": "api:windows_host / windows_host.project_package"},
        ]
        for mode, generated in (
            ("ask", []),
            ("agent", []),
            ("agent", [{**passed, "name": "mcp:other / windows_host.project_test"}]),
            ("agent", [{**passed, "name": "mcp:other / windows_host.project_package"}]),
        ):
            with self.subTest(mode=mode, generated=generated), patch.object(
                self.agent, "_tools", return_value=generated,
            ):
                self.api.stream_chat.return_value = {"message": {"content": "done"}}
                result = self.agent.run(
                    message="Check current state", model="local", workflow="standard", session_id=None,
                    paths=[], mode=mode, tool_results=previous, context_cloud_approved=False,
                )
                self.assertNotIn("program_verification", result)
                self.assertNotIn("package_verification", result)

    def test_write_only_does_not_claim_program_is_tested(self) -> None:
        self.action("project_update", files=[{"path": "app.py", "content": "changed"}])
        self.plans.append({"tool": None, "arguments": {}, "reason": "stop"})
        with patch.object(self.agent, "_api_action", return_value={"written_files": ["app.py"]}):
            result = self.execute_agent()
        self.assertFalse(result["program_verification"]["tests_passed"])
        self.assertEqual(result["program_verification"]["requirements_status"], "not_verified")

    def test_equivalent_repair_cycle_stops_before_second_write(self) -> None:
        self.action("project_test")
        self.action("project_update", files=[{"path": "app.py", "content": "fixed=True\n"}])
        self.action("project_test")
        self.action("project_update", files=[{"path": "app.py", "content": "broken = True\n"}])
        with patch.object(self.agent, "_api_action", side_effect=[
            self.failure(), {"written_files": ["app.py"]}, self.failure("fixed=True\n"),
        ]) as actions:
            result = self.execute_agent()
        self.assertEqual(actions.call_count, 3)
        self.assertFalse(result["program_verification"]["tests_passed"])
        errors = [event["result"]["result"]["error"] for event in self.events
                  if event.get("result", {}).get("name") == "planner / repair"]
        self.assertTrue(any("denenmiş" in error for error in errors))

    def test_timeout_stops_before_review_or_automatic_repair(self) -> None:
        self.agent.settings.program_review_model = "reviewer:local"
        self.action("project_test")
        with patch.object(self.agent, "_api_action", return_value={
            **self.failure(), "timed_out": True,
        }) as actions:
            result = self.execute_agent()
        self.assertEqual(actions.call_count, 1)
        self.api.models.assert_not_called()
        self.assertFalse(result["program_verification"]["tests_passed"])


if __name__ == "__main__":
    unittest.main()
