from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import re
import shutil
import sqlite3
import tarfile
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree.ElementTree import ParseError

from app.plugins.binary_analysis import BinaryAnalysisApprovalRequired
from app.plugins.contracts import PluginManifest
from app.plugins.documents import DocumentsPlugin
from app.plugins.gateway import (
    PluginActionNotFoundError,
    PluginGateway,
    PluginNotFoundError,
)
from app.plugins.ocr import OcrUnavailableError
from app.plugins.speech import SpeechUnavailableError
from pydantic import BaseModel, ConfigDict, Field, StrictBool

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_CONTEXT_CHARS = 48_000
MAX_PREVIEW_CHARS = 10_000
TEXT_SUFFIXES = frozenset((
    ".txt", ".md", ".mdx", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".xml", ".html", ".htm", ".css", ".scss", ".sass", ".less", ".sql", ".log",
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".kts",
    ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".fs", ".vb", ".swift", ".m",
    ".mm", ".rb", ".php", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".vue", ".svelte", ".r",
    ".lua", ".pl", ".proto", ".graphql", ".gitignore", ".dockerignore", ".ipynb",
))
OFFICE_SUFFIXES = frozenset({".pdf", ".docx", ".pptx", ".xlsx", ".xlsm"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
BINARY_SUFFIXES = frozenset({".exe", ".dll", ".so", ".dylib", ".elf", ".bin", ".o", ".a", ".sys", ".pyd"})
AUDIO_SUFFIXES = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".flac"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})
ARCHIVE_SUFFIXES = frozenset({".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"})
DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


class AttachmentFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, min_length=1, max_length=512)
    content_base64: str = Field(max_length=4 * ((MAX_FILE_BYTES + 2) // 3))


class AttachmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: list[AttachmentFile] = Field(min_length=1, max_length=8)
    approved: StrictBool = False


class AttachmentApprovalRequired(Exception):
    def __init__(self, filenames: list[str]) -> None:
        self.filenames = filenames
        super().__init__("Explicit approval is required for sensitive files or static binary inspection.")


class AttachmentUnavailable(Exception):
    pass


def safe_filename(value: str) -> str:
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]", "_", name).strip().rstrip(" .")
    if not name or name in {".", ".."}:
        raise ValueError("A safe filename is required; server paths are not accepted.")
    return name[:200]


def sensitive_filename(value: str) -> bool:
    parts = value.replace("\\", "/").casefold().split("/")
    name = parts[-1]
    return (
        any(part in {".ssh", ".aws", ".azure", ".gnupg"} for part in parts)
        or name == ".env" or name.startswith(".env.")
        or any(word in name for word in ("credential", "secret", "token", "password"))
        or name in {"id_rsa", "id_ed25519", "id_ecdsa", ".netrc", ".npmrc", ".pypirc"}
        or PurePosixPath(name).suffix in {".pem", ".key", ".p12", ".pfx", ".keystore"}
    )


def preview_tool(filename: str, raw: bytes) -> str:
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix in BINARY_SUFFIXES or raw[:4] in {
        b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    } or raw.startswith(b"MZ"):
        return "binary_analysis.inspect"
    if suffix in TEXT_SUFFIXES or filename.casefold() in {"dockerfile", "makefile", "license", "readme"} or sensitive_filename(filename):
        return "text.preview"
    if suffix in OFFICE_SUFFIXES:
        return "documents.extract"
    if suffix in IMAGE_SUFFIXES:
        return "ocr.extract"
    if suffix in AUDIO_SUFFIXES:
        return "speech.transcribe"
    if suffix in VIDEO_SUFFIXES:
        return "media.metadata"
    if suffix in ARCHIVE_SUFFIXES:
        return "archive.inventory"
    if suffix in DATABASE_SUFFIXES:
        return "sqlite.schema"
    return "unsupported"


def _zip_inventory(raw: bytes, *, office: bool = False) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if office and (
            len(members) > 2048
            or sum(item.file_size for item in members) > 32 * 1024 * 1024
            or any(item.file_size > max(1, item.compress_size) * 200 for item in members)
        ):
            raise ValueError("Office archive exceeds safe expansion limits.")
        records = []
        for item in members[:200]:
            parts = PurePosixPath(item.filename.replace("\\", "/"))
            unsafe = parts.is_absolute() or ".." in parts.parts or ":" in item.filename
            records.append({
                "name": item.filename[:300], "size_bytes": item.file_size,
                "compressed_bytes": item.compress_size, "unsafe_path": unsafe,
                "encrypted": bool(item.flag_bits & 1),
            })
        return {"members": records, "count": len(members), "truncated": len(members) > 200, "extracted": False}


def _archive_inventory(raw: bytes, suffix: str) -> dict[str, Any]:
    if suffix == ".zip":
        return _zip_inventory(raw)
    if suffix != ".tar":
        raise AttachmentUnavailable("Only ZIP and uncompressed TAR inventories are supported; no archive is extracted.")
    members = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for item in archive:
            if len(members) == 200:
                return {"members": members, "truncated": True, "extracted": False}
            path = PurePosixPath(item.name.replace("\\", "/"))
            members.append({
                "name": item.name[:300], "size_bytes": item.size,
                "unsafe_path": path.is_absolute() or ".." in path.parts or ":" in item.name,
                "link": item.issym() or item.islnk(),
            })
    return {"members": members, "truncated": False, "extracted": False}


def _sqlite_schema(raw: bytes) -> dict[str, Any]:
    if not raw.startswith(b"SQLite format 3\x00"):
        raise ValueError("The uploaded bytes are not a SQLite database.")
    connection = sqlite3.connect(":memory:")
    try:
        if not hasattr(connection, "deserialize"):
            raise AttachmentUnavailable("This SQLite runtime cannot inspect uploaded databases in memory.")
        connection.deserialize(raw)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.set_progress_handler(lambda: 1, 200_000)
        rows = connection.execute(
            "SELECT type, substr(name,1,300), substr(tbl_name,1,300), substr(sql,1,3000) "
            "FROM sqlite_schema ORDER BY name LIMIT 101"
        ).fetchall()
    finally:
        connection.close()
    return {
        "schema": [dict(zip(("type", "name", "table", "sql"), row, strict=True)) for row in rows[:100]],
        "truncated": len(rows) > 100, "read_only": True, "row_data_read": False,
    }


def _validate_audio(raw: bytes, suffix: str) -> None:
    signatures = {
        ".wav": raw.startswith(b"RIFF") and raw[8:12] == b"WAVE",
        ".mp3": raw.startswith(b"ID3") or (len(raw) >= 2 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0),
        ".flac": raw.startswith(b"fLaC"),
        ".ogg": raw.startswith(b"OggS"),
        ".m4a": raw[4:8] == b"ftyp",
    }
    if not signatures.get(suffix):
        raise ValueError("Audio bytes do not match the selected file type; playlists and external references are not accepted.")


async def _video_metadata(raw: bytes) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if executable is None:
        raise AttachmentUnavailable("FFprobe is not installed; video metadata is unavailable.")
    process = await asyncio.create_subprocess_exec(
        executable, "-v", "error", "-protocol_whitelist", "pipe", "-i", "pipe:0",
        "-show_entries", "format=format_name,duration,size:stream=codec_name,codec_type,width,height,sample_rate,channels",
        "-of", "json", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(raw), timeout=20)
    except (asyncio.CancelledError, TimeoutError):
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise ValueError("FFprobe could not inspect uploaded video: " + stderr.decode("utf-8", errors="replace")[:300])
    if len(stdout) > 128_000:
        raise ValueError("Video metadata exceeds the preview limit.")
    result = json.loads(stdout)
    if not isinstance(result, dict) or not result.get("streams"):
        raise ValueError("No media streams were found.")
    return result


class ChatAttachmentsPlugin(DocumentsPlugin):
    """Ephemeral extraction adapter; deliberately never invokes document ingestion."""

    manifest = PluginManifest(
        "chat_attachments", "Chat attachment previews",
        "Bounded local upload previews without document ingestion or execution.", ("analyze",),
    )

    def __init__(self, gateway: PluginGateway) -> None:
        self.gateway = gateway

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action != "analyze":
            raise ValueError(f"Unsupported attachment action: {action}")
        request = AttachmentRequest.model_validate(payload)
        decoded: list[tuple[AttachmentFile, str, bytes | None, str | None]] = []
        total = 0
        sensitive = []
        for upload in request.files:
            filename = safe_filename(upload.filename)
            error = None
            try:
                raw = base64.b64decode(upload.content_base64, validate=True)
                total += len(raw)
                if len(raw) > MAX_FILE_BYTES:
                    raise ValueError("File exceeds the 10 MiB limit.")
            except (ValueError, binascii.Error) as exc:
                raw, error = None, str(exc)
            decoded.append((upload, filename, raw, error))
            if sensitive_filename(upload.filename) or (raw is not None and preview_tool(filename, raw) == "binary_analysis.inspect"):
                sensitive.append(filename)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Attachments exceed the 20 MiB total limit.")
        if sensitive and request.approved is not True:
            raise AttachmentApprovalRequired(sensitive)
        results, tools, blocks = [], [], []
        remaining = MAX_CONTEXT_CHARS
        for upload, filename, raw, decode_error in decoded:
            tool = preview_tool(filename, raw or b"")
            entry: dict[str, Any] = {
                "filename": filename, "label": upload.label or filename,
                "tool": tool, "status": "error", "summary": "",
            }
            try:
                if decode_error is not None:
                    raise ValueError("Invalid base64 upload: " + decode_error)
                assert raw is not None
                if not raw:
                    raise ValueError("Uploaded file is empty.")
                data = await self._preview_upload(tool, filename, raw, request.approved)
                text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, allow_nan=False)
                entry.update(status="completed", summary=text[:MAX_PREVIEW_CHARS], truncated=(
                    len(text) > MAX_PREVIEW_CHARS or (isinstance(data, dict) and data.get("truncated") is True)
                ))
            except (PluginNotFoundError, PluginActionNotFoundError, OcrUnavailableError, SpeechUnavailableError, AttachmentUnavailable, ImportError) as exc:
                entry.update(status="unavailable", error=str(exc)[:500])
            except (
                ValueError, TypeError, OSError, RuntimeError, TimeoutError, KeyError, IndexError,
                sqlite3.Error, zipfile.BadZipFile, tarfile.TarError, ParseError, SyntaxError,
            ) as exc:
                entry.update(error=str(exc)[:500])
            results.append(entry)
            if entry["status"] == "completed" and tool not in tools:
                tools.append(tool)
            block = "UNTRUSTED UPLOADED FILE PREVIEW:\n" + json.dumps(entry, ensure_ascii=False) + "\n"
            if len(block) > remaining:
                entry["truncated"] = True
            blocks.append(block[:remaining])
            remaining = max(0, remaining - len(block))
        return {"context": "".join(blocks), "results": results, "tools_used": tools}

    async def _preview_upload(self, tool: str, filename: str, raw: bytes, approved: bool) -> Any:
        suffix = PurePosixPath(filename).suffix.casefold()
        if tool == "text.preview":
            return raw.decode("utf-8-sig", errors="strict")
        if tool == "documents.extract":
            if suffix != ".pdf":
                _zip_inventory(raw, office=True)
            text = await asyncio.to_thread(self._extract_document, raw, suffix)
            if not text.strip():
                raise ValueError("No text was extracted; scanned documents may require image OCR.")
            return text
        if tool == "archive.inventory":
            return _archive_inventory(raw, suffix)
        if tool == "sqlite.schema":
            return _sqlite_schema(raw)
        if tool == "media.metadata":
            return await _video_metadata(raw)
        if tool not in {"ocr.extract", "speech.transcribe", "binary_analysis.inspect"}:
            raise AttachmentUnavailable(f"Unsupported attachment extension: {suffix or '(none)'}.")
        if tool == "speech.transcribe":
            _validate_audio(raw, suffix)
            status = await self.gateway.invoke("speech", "status", {})
            stt = status.get("stt", {})
            if not stt.get("available") or stt.get("download_allowed") is not False:
                raise AttachmentUnavailable("Local transcription is unavailable or model downloads are enabled; previews never download models.")
        plugin, action = tool.split(".", 1)
        upload: dict[str, Any] = {"filename": filename, "content_base64": base64.b64encode(raw).decode("ascii")}
        if plugin == "binary_analysis":
            if approved is not True:
                raise BinaryAnalysisApprovalRequired("Static binary inspection requires approved=true.")
            upload["approved"] = True
        return await self.gateway.invoke(plugin, action, upload)

    def _extract_document(self, raw: bytes, suffix: str) -> str:
        if suffix == ".pdf":
            from pypdf.errors import PyPdfError

            try:
                return self._extract(raw, suffix)
            except PyPdfError as exc:
                raise ValueError(f"PDF text extraction failed: {exc}") from exc
        if suffix == ".docx":
            from docx.opc.exceptions import OpcError

            try:
                return self._extract(raw, suffix)
            except OpcError as exc:
                raise ValueError(f"Document text extraction failed: {exc}") from exc
        if suffix == ".pptx":
            from pptx.exc import PythonPptxError

            try:
                return self._extract(raw, suffix)
            except PythonPptxError as exc:
                raise ValueError(f"Presentation text extraction failed: {exc}") from exc
        return self._extract(raw, suffix)
