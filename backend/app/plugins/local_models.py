from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any


def models_dir() -> Path:
    return Path(os.getenv("DEEPPANDA_MODELS_DIR", "/models")).expanduser()


def runtimes_dir() -> Path:
    return Path(os.getenv("DEEPPANDA_RUNTIMES_DIR", "/runtimes")).expanduser()


def model_path(setting: str, default: str) -> Path:
    configured = os.getenv(setting, "").strip()
    path = Path(configured or default).expanduser()
    return path if path.is_absolute() else models_dir() / path


def piper_model_path() -> Path:
    return model_path("PIPER_MODEL_PATH", "piper-voices/tr_TR-dfki-medium/tr_TR-dfki-medium.onnx")


def image_model_path() -> Path:
    return model_path("IMAGE_MODEL_PATH", "tiny-sd")


def video_model_path() -> Path:
    return model_path("VIDEO_MODEL_PATH", "text-to-video-ms-1.7b")


def whisper_model() -> str:
    return os.getenv("WHISPER_MODEL", "small").strip() or "small"


def whisper_download_allowed() -> bool:
    return os.getenv("WHISPER_ALLOW_DOWNLOAD", "false").strip().casefold() in {"1", "true", "yes", "on"}


def whisper_download_root() -> Path:
    bundled = models_dir() / "whisper"
    if bundled.is_dir() and not whisper_download_allowed():
        return bundled
    return Path(os.getenv("AI_DATA_DIR", "/data")).expanduser() / "models" / "whisper"


def decode_upload(payload: dict[str, Any], max_bytes: int, key: str = "content_base64") -> bytes:
    encoded = payload.get(key)
    if not isinstance(encoded, str):
        raise ValueError(f"{key} must be a base64 string.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError(f"{key} is invalid.") from exc
    if not raw:
        raise ValueError("Uploaded content is empty.")
    if len(raw) > max_bytes:
        raise ValueError(f"Uploaded content exceeds the {max_bytes}-byte limit.")
    return raw


def upload_suffix(payload: dict[str, Any], allowed: set[str] | frozenset[str]) -> str:
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename.strip() or len(filename) > 255:
        raise ValueError("filename must be a non-empty string up to 255 characters.")
    suffix = Path(filename.replace("\\", "/")).suffix.casefold()
    if suffix not in allowed:
        raise ValueError(f"Unsupported file type; allowed: {', '.join(sorted(allowed))}.")
    return suffix
