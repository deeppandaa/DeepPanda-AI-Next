from __future__ import annotations

import importlib.util
import io
import logging
import os
import re
import shutil
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.local_models import decode_upload, upload_suffix
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class OcrUnavailableError(Exception):
    pass


_WINDOWS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def find_tesseract() -> str:
    configured = os.getenv("TESSERACT_CMD", "").strip()
    candidates = [configured, shutil.which("tesseract") or "", *_WINDOWS_TESSERACT]
    return next((path for path in candidates if path and Path(path).is_file()), "")


class OcrPlugin:
    manifest = PluginManifest(
        plugin_id="ocr",
        display_name="Local OCR",
        description="Tesseract ile yerel görsel metin çıkarma (opsiyonel bağımlılık).",
        actions=("status", "extract"),
    )

    image_suffixes: ClassVar[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
    max_image_bytes: ClassVar[int] = 20_000_000
    max_pixels: ClassVar[int] = 40_000_000
    max_text_chars: ClassVar[int] = 50_000

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            return await run_thread(self.status, logger)
        if action == "extract":
            return await self._extract(payload)
        raise ValueError(f"Unsupported OCR action: {action}")

    def status(self) -> dict[str, Any]:
        tesseract = find_tesseract()
        pytesseract_installed = importlib.util.find_spec("pytesseract") is not None
        pillow_installed = importlib.util.find_spec("PIL") is not None
        languages: list[str] = []
        language_error: str | None = None
        if tesseract and pytesseract_installed:
            try:
                import pytesseract

                pytesseract.pytesseract.tesseract_cmd = tesseract
                languages = sorted(pytesseract.get_languages(config=""))
            except Exception as exc:
                language_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Could not query installed Tesseract languages.")
        return {
            "available": bool(tesseract and pytesseract_installed and pillow_installed),
            "tesseract": tesseract,
            "pytesseract_installed": pytesseract_installed,
            "pillow_installed": pillow_installed,
            "languages": languages,
            "language_error": language_error,
            "setup_hint": "" if tesseract else "Docker imajında tesseract-ocr paketleri kurulur; Windows için UB-Mannheim Tesseract kurulumu gerekir.",
        }

    async def _extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        upload_suffix(payload, self.image_suffixes)
        raw = decode_upload(payload, self.max_image_bytes)
        language = payload.get("language", "tur+eng")
        if not isinstance(language, str) or not re.fullmatch(r"[a-z_]{3,12}(\+[a-z_]{3,12}){0,3}", language):
            raise ValueError("language must look like 'tur' or 'tur+eng'.")
        return await run_thread(partial(self.extract_bytes, raw, language), logger)

    def extract_bytes(self, raw: bytes, language: str = "tur+eng") -> dict[str, Any]:
        tesseract = find_tesseract()
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OcrUnavailableError("pytesseract and Pillow are required for OCR.") from exc
        if not tesseract:
            raise OcrUnavailableError("Tesseract OCR engine was not found.")
        pytesseract.pytesseract.tesseract_cmd = tesseract
        try:
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > self.max_pixels:
                raise ValueError("Image exceeds the OCR pixel limit.")
            image.load()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Image could not be decoded.") from exc
        available = set(pytesseract.get_languages(config=""))
        requested = language.split("+")
        usable = [item for item in requested if item in available] or ["eng"]
        text = pytesseract.image_to_string(image, lang="+".join(usable), timeout=120)
        return {
            "text": text[: self.max_text_chars],
            "truncated": len(text) > self.max_text_chars,
            "language": "+".join(usable),
            "missing_languages": [item for item in requested if item not in available],
            "width": image.width,
            "height": image.height,
        }
