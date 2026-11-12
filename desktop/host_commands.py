from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
COMPOSE_STATUS = ("docker", "compose", "--profile", "web", "--profile", "manager", "ps")
API_LOGS = ("docker", "compose", "logs", "--tail", "200", "api")


def run_host_command(
    args: list[str], project_dir: str, timeout: int = 1800, env: dict[str, str] | None = None,
) -> dict[str, Any]:
    executable = shutil.which(args[0])
    if executable is None:
        return {"ok": False, "code": -1, "output": f"Komut bulunamadı: {args[0]}"}
    try:
        completed = subprocess.run(
            [executable, *args[1:]], check=False, cwd=project_dir, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            env={**os.environ, **(env or {})}, creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "output": f"Zaman aşımı ({timeout} sn): {' '.join(args)}"}
    except OSError as exc:
        return {"ok": False, "code": -1, "output": str(exc)}
    output = (completed.stdout or "") + (completed.stderr or "")
    return {"ok": completed.returncode == 0, "code": completed.returncode, "output": output.strip()}
