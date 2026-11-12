from __future__ import annotations

import base64
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from desktop.config import ensure_backend_importable

ensure_backend_importable()
from app.plugins.workspace import WorkspacePlugin, _is_private_environment_file

MAX_FILES = 32
MAX_ENTRIES = 1000
MAX_FILE_BYTES = 10_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_CONTEXT_CHARS = 48_000
PRIVATE_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".kdbx"}


class ChatCancelled(Exception):
    pass


def check_cancelled(cancelled: Event) -> None:
    if cancelled.is_set():
        raise ChatCancelled("İstek iptal edildi.")


def _excluded(path: Path) -> bool:
    return any(
        part.casefold() in WorkspacePlugin.excluded_directories or _is_private_environment_file(part)
        for part in path.parts
    ) or path.suffix.casefold() in PRIVATE_SUFFIXES


def _linked(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def validate_attachment_path(path: Path) -> Path:
    absolute = path.expanduser().absolute()
    if _excluded(absolute):
        raise ValueError(f"Gizli veya çalışma zamanı yolu sohbete eklenemez: {absolute.name}")
    if any(_linked(part) for part in (absolute, *absolute.parents)):
        raise ValueError(f"Sembolik bağlantı/junction sohbete eklenemez: {absolute.name}")
    if not absolute.is_file() and not absolute.is_dir():
        raise ValueError(f"Normal dosya veya klasör değil: {absolute.name}")
    return absolute


@dataclass
class AttachmentBundle:
    files: list[dict[str, str]] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_bytes: int = 0

    def context(self) -> str:
        sections = ["Kullanıcının seçtiği yerel bağlam (tam klasör taraması değildir):", *self.inventory]
        if self.warnings:
            sections.extend(["Sınırlar / atlananlar:", *self.warnings])
        return "\n".join(sections)[:8000]


def collect_attachments(paths: list[Path], cancelled: Event) -> AttachmentBundle:
    bundle = AttachmentBundle()
    seen: set[Path] = set()
    examined = 0

    def add_file(path: Path, label: str, *, explicit: bool) -> None:
        nonlocal examined
        check_cancelled(cancelled)
        if explicit:
            examined += 1
        if path in seen:
            return
        seen.add(path)
        if _excluded(path) or _linked(path):
            bundle.warnings.append(f"Özel/bağlantı yolu atlandı: {label}")
            return
        size = path.stat().st_size
        bundle.inventory.append(f"{label} ({size} bayt, {path.suffix or 'uzantısız'})")
        problem = ""
        if len(bundle.files) >= MAX_FILES:
            problem = f"{MAX_FILES} dosya sınırı"
        elif size > MAX_FILE_BYTES:
            problem = "10 MB dosya sınırı"
        elif bundle.total_bytes + size > MAX_TOTAL_BYTES:
            problem = "20 MB toplam bağlam sınırı"
        if problem:
            if explicit:
                raise ValueError(f"{label}: {problem}. Daha küçük bir seçim yapın.")
            bundle.warnings.append(f"İçeriği alınmadı: {label} ({problem})")
            return
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) != size:
            raise ValueError(f"Okuma sırasında dosya değişti: {label}; yeniden seçin.")
        bundle.total_bytes += len(data)
        bundle.files.append({
            "filename": path.name,
            "content_base64": base64.b64encode(data).decode("ascii"),
            "label": label,
        })

    def walk(directory: Path, base: Path, depth: int) -> None:
        nonlocal examined
        check_cancelled(cancelled)
        if depth > 12:
            bundle.warnings.append(f"Derinlik sınırı: {directory.relative_to(base)}")
            return
        with os.scandir(directory) as entries:
            for entry in entries:
                check_cancelled(cancelled)
                examined += 1
                if examined > MAX_ENTRIES:
                    return
                child = Path(entry.path)
                label = str(child.relative_to(base))
                if _excluded(child) or _linked(child):
                    bundle.warnings.append(f"Özel/bağlantı yolu atlandı: {label}")
                elif entry.is_dir(follow_symlinks=False):
                    walk(child, base, depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    add_file(child, label, explicit=False)

    for selected in paths:
        check_cancelled(cancelled)
        path = validate_attachment_path(selected)
        if path.is_file():
            add_file(path, path.name, explicit=True)
        else:
            bundle.inventory.append(f"Seçili klasör: {path.name}")
            walk(path, path.parent, 0)
    if examined > MAX_ENTRIES:
        bundle.warnings.append(f"En fazla {MAX_ENTRIES} girdi incelendi; kalan klasör içeriği taranmadı.")
    if paths and not bundle.files:
        raise ValueError("Seçimde okunabilir dosya yok. Özel yollar/bağlantılar bağlam dışında tutulur.")
    return bundle


def bounded_context(parts: list[str]) -> str:
    text = "\n\n".join(part for part in parts if part)
    if len(text) <= MAX_CONTEXT_CHARS:
        return text
    marker = "\n\n[Bağlam 48.000 karakter sınırında kesildi; kalan içerik modele verilmedi.]"
    return text[: MAX_CONTEXT_CHARS - len(marker)] + marker
