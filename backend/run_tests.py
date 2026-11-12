from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def positive_seconds(value: str) -> int:
    seconds = int(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("Timeout must be greater than zero.")
    return seconds


def run_phase(command: list[str], label: str, timeout: int, env: dict[str, str]) -> int:
    print(f"[{label}] time limit: {timeout}s", flush=True)
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        print(f"[{label}] timed out after {timeout}s; child process stopped.", file=sys.stderr, flush=True)
        return 124
    except OSError as exc:
        print(f"[{label}] could not start: {exc}", file=sys.stderr, flush=True)
        return 2
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pytest with a bounded asyncio preflight and test deadline.")
    parser.add_argument("--timeout", type=positive_seconds, default=300, help="Whole pytest run limit in seconds.")
    parser.add_argument("--preflight-timeout", type=positive_seconds, default=10, help="Asyncio startup limit in seconds.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Arguments after -- are passed to pytest.")
    args = parser.parse_args(argv)
    temp = PROJECT_ROOT / "_tmp" / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "TEMP": str(temp),
        "TMP": str(temp),
        "TMPDIR": str(temp),
        "PIP_CACHE_DIR": str(PROJECT_ROOT / "_tmp" / "pip-cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(filter(None, (
            str(PROJECT_ROOT / "backend"), str(PROJECT_ROOT), os.environ.get("PYTHONPATH"),
        ))),
    }
    probe = (
        "import asyncio, faulthandler; "
        f"faulthandler.dump_traceback_later({max(0.1, args.preflight_timeout / 2)}); "
        "asyncio.run(asyncio.sleep(0)); "
        "faulthandler.cancel_dump_traceback_later()"
    )
    result = run_phase([sys.executable, "-c", probe], "asyncio preflight", args.preflight_timeout, env)
    if result != 0:
        print(
            "Asyncio startup failed; pytest was not started. On Windows, socketpair/accept in the trace "
            "indicates blocked local loopback communication. Check sandbox/firewall loopback permissions. "
            "No permissions were changed.",
            file=sys.stderr, flush=True,
        )
        return result
    pytest_args = args.pytest_args
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    if not pytest_args:
        pytest_args = [str(PROJECT_ROOT / "backend" / "tests"), "-q"]
    return run_phase(
        [sys.executable, "-m", "pytest", "-o", "faulthandler_timeout=30", *pytest_args],
        "pytest", args.timeout, env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
