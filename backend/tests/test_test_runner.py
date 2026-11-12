from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_tests


class TestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        root_patch = patch.object(run_tests, "PROJECT_ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def test_runs_preflight_then_selected_tests_with_local_environment(self) -> None:
        with patch("run_tests.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            result = run_tests.main([
                "--timeout", "45", "--preflight-timeout", "2", "--", "-q", "backend/tests/test_multi_agent.py",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(run.call_count, 2)
        probe, tests = run.call_args_list
        self.assertEqual(probe.kwargs["timeout"], 2)
        self.assertIn("asyncio.run", probe.args[0][-1])
        self.assertEqual(tests.kwargs["timeout"], 45)
        self.assertEqual(tests.kwargs["cwd"], self.root)
        self.assertEqual(tests.args[0], [
            sys.executable, "-m", "pytest", "-o", "faulthandler_timeout=30",
            "-q", "backend/tests/test_multi_agent.py",
        ])
        env = tests.kwargs["env"]
        for key in ("TEMP", "TMP", "TMPDIR"):
            self.assertEqual(env[key], str(self.root / "_tmp" / "temp"))
            self.assertTrue(Path(env[key]).is_dir())
        self.assertEqual(env["PIP_CACHE_DIR"], str(self.root / "_tmp" / "pip-cache"))
        self.assertEqual(env["PYTHONPATH"].split(os.pathsep)[:2], [str(self.root / "backend"), str(self.root)])
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_default_suite_and_test_failure_exit_code(self) -> None:
        with patch("run_tests.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1),
        ]) as run:
            self.assertEqual(run_tests.main([]), 1)
        self.assertEqual(run.call_args.args[0][-2:], [str(self.root / "backend" / "tests"), "-q"])

    def test_preflight_timeout_stops_before_pytest(self) -> None:
        output = io.StringIO()
        with (
            patch("run_tests.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 2)) as run,
            contextlib.redirect_stderr(output),
        ):
            result = run_tests.main(["--preflight-timeout", "2"])
        self.assertEqual(result, 124)
        self.assertEqual(run.call_count, 1)
        self.assertIn("pytest was not started", output.getvalue())
        self.assertIn("loopback", output.getvalue())

    def test_test_timeout_is_not_reported_as_success(self) -> None:
        with patch("run_tests.subprocess.run", side_effect=[
            subprocess.CompletedProcess([], 0), subprocess.TimeoutExpired("pytest", 3),
        ]):
            self.assertEqual(run_tests.main(["--timeout", "3"]), 124)

    def test_start_failure_is_reported_without_running_tests(self) -> None:
        with patch("run_tests.subprocess.run", side_effect=PermissionError("blocked")) as run:
            self.assertEqual(run_tests.main([]), 2)
        self.assertEqual(run.call_count, 1)

    def test_preflight_nonzero_exit_is_preserved(self) -> None:
        with patch("run_tests.subprocess.run", return_value=subprocess.CompletedProcess([], 7)) as run:
            self.assertEqual(run_tests.main([]), 7)
        self.assertEqual(run.call_count, 1)

    def test_invalid_deadlines_are_rejected(self) -> None:
        for option in ("--timeout", "--preflight-timeout"):
            for value in ("0", "-1", "invalid"):
                with self.subTest(option=option, value=value), self.assertRaises(SystemExit) as exc:
                    run_tests.main([option, value])
                self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
