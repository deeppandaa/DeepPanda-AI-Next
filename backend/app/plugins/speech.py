from __future__ import annotations

import base64
import importlib.util
import logging
import shutil
import subprocess
import tempfile
import threading
import wave
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.local_models import (
    decode_upload,
    piper_model_path,
    upload_suffix,
    whisper_download_allowed,
    whisper_download_root,
    whisper_model,
)
from app.plugins.worker_lifecycle import run_thread

logger = logging.getLogger(__name__)


class SpeechApprovalRequired(Exception):
    pass


class SpeechUnavailableError(Exception):
    pass


class SpeechPlugin:
    manifest = PluginManifest(
        plugin_id="speech",
        display_name="Local Speech",
        description="Yerel Piper TTS ve faster-whisper konuşma tanıma (opsiyonel bağımlılıklar).",
        actions=("status", "synthesize", "transcribe"),
    )

    audio_suffixes: ClassVar[frozenset[str]] = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mov", ".mkv"})
    max_text_chars: ClassVar[int] = 5_000
    max_audio_bytes: ClassVar[int] = 100_000_000
    max_transcript_chars: ClassVar[int] = 200_000

    def __init__(self, gateway: PluginGateway) -> None:
        self.gateway = gateway
        self._voice: Any = None
        self._voice_path: Path | None = None
        self._whisper: Any = None
        self._lock = threading.Lock()

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "status":
            return self.status()
        if action == "synthesize":
            return await self._synthesize(payload)
        if action == "transcribe":
            return await self._transcribe(payload)
        raise ValueError(f"Unsupported speech action: {action}")

    def status(self) -> dict[str, Any]:
        voice = piper_model_path()
        piper_installed = importlib.util.find_spec("piper") is not None
        whisper_installed = importlib.util.find_spec("faster_whisper") is not None
        return {
            "tts": {
                "available": piper_installed and voice.is_file(),
                "piper_installed": piper_installed,
                "voice_path": str(voice),
                "voice_present": voice.is_file(),
            },
            "stt": {
                "available": whisper_installed,
                "faster_whisper_installed": whisper_installed,
                "model": whisper_model(),
                "download_allowed": whisper_download_allowed(),
                "ffmpeg": shutil.which("ffmpeg") is not None,
            },
        }

    async def _synthesize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("approved") is not True:
            raise SpeechApprovalRequired("Saving synthesized speech requires approved=true.")
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > self.max_text_chars:
            raise ValueError(f"text must be a non-empty string up to {self.max_text_chars} characters.")
        audio = await run_thread(partial(self._render_wav, text.strip()), logger)
        return await self.gateway.invoke(
            "assets",
            "store",
            {
                "approved": True,
                "kind": "audio",
                "filename": "konusma.wav",
                "media_type": "audio/wav",
                "source": "speech",
                "metadata": {"text_length": len(text), "voice": piper_model_path().stem},
                "content_base64": base64.b64encode(audio).decode("ascii"),
            },
        )

    def _render_wav(self, text: str) -> bytes:
        voice_path = piper_model_path()
        if not voice_path.is_file():
            raise SpeechUnavailableError(f"Piper voice model was not found: {voice_path}")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise SpeechUnavailableError("piper-tts is not installed.") from exc
        with self._lock:
            if self._voice is None or self._voice_path != voice_path:
                self._voice = PiperVoice.load(str(voice_path))
                self._voice_path = voice_path
            with tempfile.TemporaryDirectory(prefix="deeppanda-tts-") as directory:
                output = Path(directory) / "speech.wav"
                with wave.open(str(output), "wb") as wav_file:
                    self._voice.synthesize_wav(text, wav_file)
                return output.read_bytes()

    async def _transcribe(self, payload: dict[str, Any]) -> dict[str, Any]:
        suffix = upload_suffix(payload, self.audio_suffixes)
        raw = decode_upload(payload, self.max_audio_bytes)
        language = payload.get("language")
        if language is not None and (not isinstance(language, str) or not language.isalpha() or len(language) > 5):
            raise ValueError("language must be a short ISO language code such as 'tr'.")
        return await run_thread(partial(self.transcribe_bytes, raw, suffix, language), logger)

    def transcribe_bytes(self, raw: bytes, suffix: str, language: str | None = None) -> dict[str, Any]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechUnavailableError("faster-whisper is not installed.") from exc
        with tempfile.TemporaryDirectory(prefix="deeppanda-stt-") as directory:
            source = Path(directory) / f"input{suffix}"
            source.write_bytes(raw)
            audio = source
            if suffix != ".wav":
                ffmpeg = shutil.which("ffmpeg")
                if ffmpeg is None:
                    raise SpeechUnavailableError("FFmpeg is required to decode non-WAV audio.")
                audio = Path(directory) / "audio.wav"
                try:
                    subprocess.run(
                        [ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                        check=True, capture_output=True, timeout=600, shell=False,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    raise ValueError("Audio could not be decoded by FFmpeg.") from exc
            with self._lock:
                if self._whisper is None:
                    self._whisper = WhisperModel(
                        whisper_model(),
                        device="cpu",
                        compute_type="int8",
                        download_root=str(whisper_download_root()),
                        local_files_only=not whisper_download_allowed(),
                    )
                segments, info = self._whisper.transcribe(str(audio), language=language or None)
                parts = []
                total = 0
                for segment in segments:
                    item = {"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip()}
                    total += len(item["text"]) + 1
                    if total > self.max_transcript_chars:
                        break
                    parts.append(item)
        return {
            "language": getattr(info, "language", language or ""),
            "duration_seconds": round(float(getattr(info, "duration", 0.0)), 2),
            "transcript": " ".join(item["text"] for item in parts),
            "segments": parts,
            "truncated": total > self.max_transcript_chars,
        }
