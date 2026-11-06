from __future__ import annotations

import base64
import io
import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.local_models import decode_upload, upload_suffix

logger = logging.getLogger(__name__)


class ReportApprovalRequired(Exception):
    pass


class ReportDependencyError(Exception):
    pass


_TURKISH_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)


class ReportsPlugin:
    manifest = PluginManifest(
        plugin_id="reports",
        display_name="Reports",
        description="Onaylı Markdown/PDF rapor dışa aktarma ve PDF'e metin sayfası ekleme.",
        actions=("status", "export", "append_pdf"),
    )

    max_markdown_chars: ClassVar[int] = 200_000
    max_pdf_bytes: ClassVar[int] = 20_000_000

    def __init__(self, gateway: PluginGateway, font_path: str | None = None) -> None:
        self.gateway = gateway
        self.font_path = font_path or os.getenv("REPORT_FONT_PATH", "")

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            return self._status()
        if action == "export":
            return await self._export(payload)
        if action == "append_pdf":
            return await self._append_pdf(payload)
        raise ValueError(f"Unsupported reports action: {action}")

    def _status(self) -> dict[str, Any]:
        return {
            "markdown": True,
            "pdf": self._reportlab_available(),
            "pdf_append": self._reportlab_available() and self._pypdf_available(),
            "unicode_font": self._font_file() or "",
        }

    async def _export(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise ReportApprovalRequired("Exporting a report requires approved=true.")
        title = self._text(payload.get("title", "DeepPanda Raporu"), "title", 200)
        output_format = payload.get("format", "md")
        if output_format not in {"md", "pdf"}:
            raise ValueError("format must be md or pdf.")
        markdown = self.render_markdown(title, payload.get("content"), payload.get("report"), payload.get("sources"))
        if output_format == "md":
            data = markdown.encode("utf-8")
            media_type = "text/markdown"
        else:
            data = self._markdown_pdf(title, markdown)
            media_type = "application/pdf"
        return await self._store(data, f"{self._slug(title)}.{output_format}", media_type, {"title": title, "format": output_format})

    async def _append_pdf(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise ReportApprovalRequired("Appending to a PDF requires approved=true.")
        upload_suffix(payload, {".pdf"})
        original = decode_upload(payload, self.max_pdf_bytes)
        addition = self._text(payload.get("addition"), "addition", 50_000)
        heading = self._text(payload.get("heading", "Ek Bilgi"), "heading", 200)
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError as exc:
            raise ReportDependencyError("pypdf is not installed.") from exc
        appended = PdfReader(io.BytesIO(self._markdown_pdf(heading, addition)))
        try:
            reader = PdfReader(io.BytesIO(original))
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
        except Exception as exc:
            raise ValueError(f"PDF could not be read: {exc}") from exc
        for page in appended.pages:
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        filename = Path(str(payload["filename"]).replace("\\", "/")).stem[:80] or "document"
        return await self._store(output.getvalue(), f"{filename}-ekli.pdf", "application/pdf", {"heading": heading, "source_filename": payload["filename"]})

    @staticmethod
    def render_markdown(title: str, content: Any, report: Any, sources: Any) -> str:
        if sources is None:
            sources = []
        if not isinstance(sources, list) or len(sources) > 100 or any(not isinstance(item, str) or len(item) > 2_000 for item in sources):
            raise ValueError("sources must be a list of up to 100 strings.")
        lines = [f"# {title}", ""]
        if content is not None:
            if not isinstance(content, str) or len(content) > ReportsPlugin.max_markdown_chars:
                raise ValueError("content must be a string up to 200000 characters.")
            lines.extend([content.strip(), ""])
        if report is not None:
            encoded = json.dumps(report, ensure_ascii=False, indent=2, default=str)
            if len(encoded) > ReportsPlugin.max_markdown_chars:
                raise ValueError("report is too large.")
            lines.extend(["## Rapor", "", "```json", encoded, "```", ""])
        if content is None and report is None:
            raise ValueError("content or report is required.")
        lines.append("## Kaynaklar")
        lines.extend(f"- {source}" for source in sources or ["Belirtilmedi"])
        return "\n".join(lines) + "\n"

    def _markdown_pdf(self, title: str, text: str) -> bytes:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.pdfgen import canvas
        except ImportError as exc:
            raise ReportDependencyError("reportlab is not installed; PDF export is unavailable.") from exc

        font_name = "Helvetica"
        font_file = self._font_file()
        if font_file:
            try:
                pdfmetrics.registerFont(TTFont("DeepPandaUnicode", font_file))
                font_name = "DeepPandaUnicode"
            except Exception:
                logger.warning(
                    "Could not register PDF Unicode font %s; falling back to Helvetica with transliteration.",
                    font_file,
                    exc_info=True,
                )
                font_name = "Helvetica"

        def printable(value: str) -> str:
            return value if font_name != "Helvetica" else value.translate(_TURKISH_ASCII).encode("latin-1", "replace").decode("latin-1")

        buffer = io.BytesIO()
        width, height = A4
        margin = 48
        font_size = 10
        leading = 14
        pdf = canvas.Canvas(buffer, pagesize=A4)
        pdf.setTitle(printable(title))
        y = height - margin
        max_width = width - 2 * margin

        def wrap(paragraph: str, size: int) -> Iterator[str]:
            line = ""
            for word in printable(paragraph).split(" "):
                candidate = f"{line} {word}" if line else word
                if pdfmetrics.stringWidth(candidate, font_name, size) <= max_width:
                    line = candidate
                    continue
                if line:
                    yield line
                offset = 0
                while offset < len(word):
                    remaining = len(word) - offset
                    low, high = 0, 1
                    while high < remaining and pdfmetrics.stringWidth(
                        word[offset:offset + high], font_name, size
                    ) <= max_width:
                        low = high
                        high = min(high * 2, remaining)
                    while low < high:
                        middle = (low + high + 1) // 2
                        if pdfmetrics.stringWidth(word[offset:offset + middle], font_name, size) <= max_width:
                            low = middle
                        else:
                            high = middle - 1
                    if low == 0:
                        raise ValueError("A character is too wide to fit on the PDF page.")
                    if low == remaining:
                        break
                    yield word[offset:offset + low]
                    offset += low
                line = word[offset:]
            yield line

        def draw_line(line: str, size: int) -> None:
            nonlocal y
            if y < margin:
                pdf.showPage()
                y = height - margin
            pdf.setFont(font_name, size)
            pdf.drawString(margin, y, line)
            y -= leading

        for line in wrap(title, font_size + 4):
            draw_line(line, font_size + 4)
        y -= leading
        for paragraph in text.splitlines() or [""]:
            for line in wrap(paragraph, font_size):
                draw_line(line, font_size)
        pdf.save()
        return buffer.getvalue()

    async def _store(self, data: bytes, filename: str, media_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return await self.gateway.invoke(
            "assets",
            "store",
            {
                "approved": True,
                "kind": "report",
                "filename": filename,
                "media_type": media_type,
                "source": "reports",
                "metadata": metadata,
                "content_base64": base64.b64encode(data).decode("ascii"),
            },
        )

    def _font_file(self) -> str | None:
        candidates = [self.font_path] if self.font_path else []
        candidates.extend(_FONT_CANDIDATES)
        return next((item for item in candidates if item and Path(item).is_file()), None)

    @staticmethod
    def _reportlab_available() -> bool:
        try:
            import reportlab  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _pypdf_available() -> bool:
        try:
            import pypdf  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = "".join(char if char.isalnum() else "-" for char in value.translate(_TURKISH_ASCII).casefold())
        return "-".join(part for part in cleaned.split("-") if part)[:60] or "rapor"

    @staticmethod
    def _text(value: Any, key: str, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise ValueError(f"{key} must be a non-empty string up to {max_length} characters.")
        return value.strip()
