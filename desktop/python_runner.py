from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from desktop.chat_context import check_cancelled

OUTPUT_BYTES = 32_000
ISOLATION_MODE = "windows_job_object_process_tree_lifetime_only"
BOOTSTRAP = (
    "import base64,json,sys;"
    "p=json.loads(sys.stdin.readline());sys.stdin.close();"
    "sys.argv=[p['path'],*p['arguments']];"
    "sys.path.insert(0,p['cwd']);"
    "exec(compile(base64.b64decode(p['source']).decode('utf-8-sig'),p['path'],'exec'),"
    "{'__name__':'__main__','__file__':p['path'],'__package__':None,'__spec__':None,'__cached__':None})"
)


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimits),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class ProcessJob:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def assign(self, pid: int) -> None:
        handle = self.api.OpenProcess(0x0001 | 0x0100, False, pid)  # TERMINATE | SET_QUOTA
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.api.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.api.CloseHandle(handle)

    def close(self) -> None:
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


def execution_environment(root: Path) -> dict[str, str]:
    # Keep Windows runtime variables, not the assistant's provider credentials or Python injection settings.
    allowed = ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE",
               "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
    env = {key: value for key, value in os.environ.items() if key.upper() in {item.upper() for item in allowed}}
    system = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join((str(system / "System32"), str(system)))
    for key, folder in {
        "TEMP": "_tmp/temp", "TMP": "_tmp/temp", "TMPDIR": "_tmp/temp",
        "PIP_CACHE_DIR": "_tmp/pip-cache", "XDG_CACHE_HOME": ".tools/cache",
        "HF_HOME": ".tools/cache/huggingface", "TORCH_HOME": ".tools/cache/torch",
        "CUPY_CACHE_DIR": ".tools/cache/cupy", "CUDA_CACHE_PATH": ".tools/cache/cuda",
    }.items():
        target = root.joinpath(*folder.split("/"))
        target.mkdir(parents=True, exist_ok=True)
        env[key] = str(target)
    env.update(PYTHONNOUSERSITE="1", PYTHONIOENCODING="utf-8")
    return env


def run_python(
    interpreter: Path, path: Path, source: str, arguments: list[str], timeout: int, root: Path,
    *, environment: dict[str, str] | None = None,
    cancelled: threading.Event | None = None,
) -> dict[str, Any]:
    if os.name != "nt":
        raise OSError("Approved host Python execution requires Windows Job Objects.")
    if cancelled is not None:
        check_cancelled(cancelled)
    job = ProcessJob()
    process = None
    readers: list[threading.Thread] = []
    output: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = {"stdout": False, "stderr": False}
    reader_errors: list[OSError] = []

    def drain(name: str, stream: Any) -> None:
        try:
            while chunk := stream.read(4096):
                remaining = OUTPUT_BYTES - len(output[name])
                output[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated[name] = True
        except OSError as exc:
            reader_errors.append(exc)
        finally:
            stream.close()

    timed_out = False
    was_cancelled = False
    try:
        process = subprocess.Popen(
            [str(interpreter), "-I", "-B", "-X", "utf8", "-u", "-c", BOOTSTRAP],
            cwd=path.parent, env=environment if environment is not None else execution_environment(root), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # The trusted bootstrap blocks on stdin until containment is established.
        job.assign(process.pid)
        if cancelled is not None:
            check_cancelled(cancelled)
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            reader = threading.Thread(target=drain, args=(name, stream), daemon=True)
            reader.start()
            readers.append(reader)
        payload = {"path": str(path), "cwd": str(path.parent), "source": source, "arguments": arguments}
        assert process.stdin is not None
        process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        process.stdin.close()
        deadline = time.monotonic() + timeout
        while True:
            if cancelled is not None and cancelled.is_set():
                was_cancelled = True
                break
            if process.poll() is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                process.wait(timeout=min(0.1, remaining))
            except subprocess.TimeoutExpired:
                continue
    finally:
        job.close()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            for reader in readers:
                reader.join(timeout=10)
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
    if any(reader.is_alive() for reader in readers):
        raise OSError("Python output reader did not terminate after process-tree cleanup.")
    if reader_errors:
        raise reader_errors[0]
    assert process is not None
    return {
        "exit_code": process.returncode, "timed_out": timed_out, "cancelled": was_cancelled,
        "stdout": output["stdout"].decode("utf-8", errors="replace"),
        "stderr": output["stderr"].decode("utf-8", errors="replace"),
        "stdout_truncated": truncated["stdout"], "stderr_truncated": truncated["stderr"],
        "isolation_mode": ISOLATION_MODE, "sandboxed": False,
    }
