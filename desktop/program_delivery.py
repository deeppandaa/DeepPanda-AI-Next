from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

MAX_FILES = 5000
MAX_BYTES = 512 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


def create_delivery(
    output: Path, name: str, *, check: Callable[[], None],
) -> dict[str, str]:
    """Archive only the verified build's onedir tree and dependency inventory."""
    app = output / "dist" / name
    report = output / "dependencies.json"
    archive = output / (name + "-windows.zip")
    temporary = output / (name + "-windows.zip.partial")
    manifest_path = output / "delivery-manifest.json"
    for path in (output, *output.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Teslim yolu bağlantı/junction içeremez.")
    if archive.exists() or temporary.exists() or manifest_path.exists():
        raise ValueError("Teslim dosyaları zaten var; mevcut çıktı üzerine yazılmaz.")
    sources: list[tuple[Path, str]] = [(report, "dependencies.json")]
    for path in (app.parent, app):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Paket klasörü bağlantı/junction içeremez.")
    for index, path in enumerate(app.rglob("*")):
        check()
        if index >= MAX_FILES:
            raise ValueError("Teslim 5000 dosya/dizin sınırını aşıyor.")
        if path.is_symlink() or path.is_junction():
            raise ValueError("Paket içindeki bağlantı/junction teslim edilemez.")
        if path.is_file():
            sources.append((path, name + "/" + path.relative_to(app).as_posix()))
        elif not path.is_dir():
            raise ValueError("Paket özel dosya içeremez.")
        if len(sources) > MAX_FILES:
            raise ValueError("Teslim 5000 dosya sınırını aşıyor.")
    if not any(path == app / (name + ".exe") for path, _ in sources):
        raise ValueError("Teslim için doğrulanmış EXE bulunamadı.")
    entries: list[dict[str, str | int]] = []
    total = 0
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as bundle:
            seen: set[str] = set()
            for path, relative in sorted(sources, key=lambda pair: pair[1]):
                check()
                if relative.casefold() in seen:
                    raise ValueError("Teslim dosya yolları çakışıyor.")
                seen.add(relative.casefold())
                if path.is_symlink() or path.is_junction() or path.stat().st_nlink != 1:
                    raise ValueError("Teslim dosyası link/hardlink içeremez.")
                before = path.stat()
                total += before.st_size
                if total > MAX_BYTES:
                    raise ValueError("Teslim toplam 512 MiB sınırını aşıyor.")
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as source, bundle.open(relative, "w") as destination:
                    while chunk := source.read(CHUNK_BYTES):
                        check()
                        size += len(chunk)
                        if size > before.st_size:
                            raise ValueError("Teslim dosyası okunurken büyüdü; yeniden paketleyin.")
                        digest.update(chunk)
                        destination.write(chunk)
                after = path.stat()
                if size != before.st_size or (
                    after.st_size, after.st_mtime_ns, after.st_ino,
                ) != (before.st_size, before.st_mtime_ns, before.st_ino):
                    raise ValueError("Teslim dosyası oluşturma sırasında değişti.")
                entries.append({"path": relative, "bytes": size, "sha256": digest.hexdigest()})
            manifest = {
                "version": 1, "project": name, "platform": "windows",
                "executable": name + "/" + name + ".exe", "files": entries,
                "notice": (
                    "Extract the whole ZIP before running. File hashes detect corruption, not authenticity. "
                    "Review dependencies.json and bundled licenses before redistribution. "
                    "Build sources, logs and environment are not included. No code signing or installer."
                ),
            }
            raw_manifest = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            bundle.writestr("delivery-manifest.json", raw_manifest)
        with zipfile.ZipFile(temporary) as bundle:
            if set(bundle.namelist()) != {str(item["path"]) for item in entries} | {"delivery-manifest.json"}:
                raise ValueError("Teslim ZIP dosya listesi doğrulanamadı.")
            for item in entries:
                check()
                digest = hashlib.sha256()
                with bundle.open(str(item["path"])) as source:
                    while chunk := source.read(CHUNK_BYTES):
                        check()
                        digest.update(chunk)
                if digest.hexdigest() != item["sha256"]:
                    raise ValueError("Teslim ZIP içeriği hash doğrulamasını geçemedi.")
            if bundle.read("delivery-manifest.json") != raw_manifest:
                raise ValueError("Teslim doğrulama listesi ZIP içinde değişti.")
        check()
        digest = hashlib.sha256()
        with temporary.open("rb") as source:
            while chunk := source.read(CHUNK_BYTES):
                check()
                digest.update(chunk)
        manifest_path.write_bytes(raw_manifest)
        temporary.rename(archive)
        executable = next(item for item in entries if item["path"] == name + "/" + name + ".exe")
        return {
            "delivery_archive": str(archive), "delivery_sha256": digest.hexdigest(),
            "delivery_manifest": str(manifest_path),
            "executable_sha256": str(executable["sha256"]),
        }
    except zipfile.BadZipFile as exc:
        raise ValueError("Teslim ZIP yapısı veya CRC doğrulaması başarısız.") from exc
    finally:
        temporary.unlink(missing_ok=True)
