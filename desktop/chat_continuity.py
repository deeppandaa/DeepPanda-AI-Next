from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from desktop.chat_context import validate_attachment_path


class ChatContinuity:
    """Local opt-in references and status summaries, never raw tool results."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def location(self, server: str, session: str) -> Path:
        digest = hashlib.sha256(json.dumps([server.rstrip("/"), session]).encode()).hexdigest()
        return self.root / (digest + ".json")

    def save(self, server: str, session: str, paths: list[Path]) -> None:
        if len(paths) > 32:
            raise ValueError("En fazla 32 ek yolu saklanabilir.")
        values = [str(validate_attachment_path(path)) for path in paths]
        self._write(self.location(server, session), {"version": 1, "paths": values})

    def _write(self, target: Path, data: dict[str, object]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".continuity-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def load(self, server: str, session: str) -> tuple[bool, list[Path], list[str]]:
        target = self.location(server, session)
        try:
            if target.stat().st_size > 128_000:
                raise ValueError("Yerel ek yolu kaydı boyut sınırını aşıyor.")
            data = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False, [], []
        if (
            not isinstance(data, dict) or data.get("version") != 1
            or not isinstance(data.get("paths"), list) or len(data["paths"]) > 32
            or any(not isinstance(value, str) or not Path(value).is_absolute() for value in data["paths"])
        ):
            raise ValueError("Yerel ek yolu kaydı geçersiz.")
        paths, warnings = [], []
        for value in data["paths"]:
            try:
                path = validate_attachment_path(Path(value))
                if path not in paths:
                    paths.append(path)
            except (OSError, ValueError) as exc:
                warnings.append(f"Ek yeniden bağlanmadı: {value}: {exc}")
        return True, paths, warnings

    def forget(self, server: str, session: str) -> None:
        self.location(server, session).unlink(missing_ok=True)

    def summary_location(self, server: str, session: str) -> Path:
        return self.location(server, session).with_suffix(".tools.json")

    @staticmethod
    def _validate_summaries(items: object, omitted: object) -> None:
        if (
            not isinstance(items, list) or len(items) > 100
            or isinstance(omitted, bool) or not isinstance(omitted, int) or omitted < 0
        ):
            raise ValueError("Yerel araç özeti sınırları geçersiz.")
        for item in items:
            if (
                not isinstance(item, dict) or set(item) != {"name", "status"}
                or not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 200
                or any(ord(char) < 32 for char in item["name"])
                or item["status"] not in ("completed", "failed", "cancelled")
            ):
                raise ValueError("Yerel araç özeti yalnız geçerli ad/durum alanlarını kabul eder.")

    def save_summaries(self, server: str, session: str, items: list[dict[str, str]], omitted: int) -> None:
        self._validate_summaries(items, omitted)
        self._write(self.summary_location(server, session), {"version": 1, "items": items, "omitted": omitted})

    def load_summaries(self, server: str, session: str) -> tuple[bool, list[dict[str, str]], int]:
        target = self.summary_location(server, session)
        try:
            if target.stat().st_size > 128_000:
                raise ValueError("Yerel araç özeti boyut sınırını aşıyor.")
            data = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False, [], 0
        if not isinstance(data, dict) or set(data) != {"version", "items", "omitted"} or data["version"] != 1:
            raise ValueError("Yerel araç özeti kaydı geçersiz.")
        self._validate_summaries(data["items"], data["omitted"])
        return True, data["items"], data["omitted"]

    def forget_summaries(self, server: str, session: str) -> None:
        self.summary_location(server, session).unlink(missing_ok=True)
