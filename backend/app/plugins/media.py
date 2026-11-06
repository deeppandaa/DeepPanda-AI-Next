from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

from app.plugins.contracts import PluginManifest
from app.plugins.gateway import PluginGateway
from app.plugins.local_models import (
    decode_upload,
    image_model_path,
    upload_suffix,
    video_model_path,
)
from app.plugins.worker_lifecycle import (
    drain_registered_workers,
    persist_cancellation,
    run_thread,
    start_worker,
)

logger = logging.getLogger(__name__)


class MediaApprovalRequired(Exception):
    pass


class MediaUnavailableError(Exception):
    pass


class MediaPlugin:
    manifest = PluginManifest(
        plugin_id="media",
        display_name="Local Media",
        description="Yerel görsel/video üretimi, onaylı düzenleme ve FFmpeg tabanlı medya analizi.",
        actions=("status", "generate_image", "start_video", "edit_image", "edit_video", "analyze", "resume_job"),
    )

    image_suffixes: ClassVar[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})
    video_suffixes: ClassVar[frozenset[str]] = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi"})
    audio_suffixes: ClassVar[frozenset[str]] = frozenset({".wav", ".mp3", ".m4a", ".ogg", ".flac"})
    max_image_bytes: ClassVar[int] = 20_000_000
    max_media_bytes: ClassVar[int] = 300_000_000
    max_prompt_chars: ClassVar[int] = 2_000
    analysis_frames: ClassVar[int] = 12

    def __init__(self, gateway: PluginGateway) -> None:
        self.gateway = gateway
        self._image_pipeline: Any = None
        self._video_pipeline: Any = None
        self._pipeline_lock = threading.Lock()
        self._workers: set[asyncio.Task[None]] = set()
        self.worker_id = f"media-{uuid.uuid4().hex[:12]}"

    async def drain_workers(self) -> None:
        await drain_registered_workers(self._workers)

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "status": self._status,
            "generate_image": self._generate_image,
            "start_video": self._start_video,
            "resume_job": self._resume_job,
            "edit_image": self._edit_image,
            "edit_video": self._edit_video,
            "analyze": self._analyze,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unsupported media action: {action}")
        return await handler(payload)

    async def _status(self, _: dict[str, Any]) -> dict[str, Any]:
        diffusers_installed = importlib.util.find_spec("diffusers") is not None and importlib.util.find_spec("torch") is not None
        ffmpeg = shutil.which("ffmpeg") is not None
        image_model = image_model_path()
        video_model = video_model_path()
        gpu = False
        gpu_error: str | None = None
        if diffusers_installed:
            try:
                import torch

                gpu = bool(torch.cuda.is_available())
            except (ImportError, OSError, RuntimeError) as exc:
                logger.exception("Could not query media CUDA availability.")
                gpu_error = f"{type(exc).__name__}: {exc}"[:500]
        return {
            "ffmpeg": ffmpeg,
            "pillow": importlib.util.find_spec("PIL") is not None,
            "diffusers_installed": diffusers_installed,
            "gpu": gpu,
            "gpu_error": gpu_error,
            "image_model": {"path": str(image_model), "present": image_model.is_dir()},
            "video_model": {"path": str(video_model), "present": video_model.is_dir()},
            "image_generation": diffusers_installed and image_model.is_dir(),
            "video_generation": diffusers_installed and ffmpeg and (video_model.is_dir() or image_model.is_dir()),
            "image_editing": importlib.util.find_spec("PIL") is not None,
            "video_editing": ffmpeg,
        }

    async def _generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Generating an image")
        prompt = self._prompt(payload)
        steps = self._int(payload.get("steps", 8), "steps", 1, 30)
        width = self._int(payload.get("width", 512), "width", 128, 768) // 8 * 8
        height = self._int(payload.get("height", 512), "height", 128, 768) // 8 * 8
        image = await run_thread(partial(self._render_image, prompt, steps, width, height), logger)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return await self._store(
            buffer.getvalue(), "image", "gorsel.png", "image/png",
            {"prompt": prompt, "steps": steps, "width": width, "height": height, "model": image_model_path().name},
        )

    def _render_image(self, prompt: str, steps: int, width: int, height: int) -> Any:
        model = image_model_path()
        if not model.is_dir():
            raise MediaUnavailableError(f"Image model was not found: {model}")
        try:
            import torch
            from diffusers import StableDiffusionPipeline
        except ImportError as exc:
            raise MediaUnavailableError("torch and diffusers are required for image generation.") from exc
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        with self._pipeline_lock:
            if self._image_pipeline is None:
                self._image_pipeline = StableDiffusionPipeline.from_pretrained(
                    str(model), local_files_only=True, torch_dtype=dtype, safety_checker=None,
                ).to(device)
            return self._image_pipeline(prompt, num_inference_steps=steps, guidance_scale=0.0, width=width, height=height).images[0]

    async def _start_video(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Generating a video")
        prompt = self._prompt(payload)
        duration = self._int(payload.get("duration_seconds", 4), "duration_seconds", 1, 10)
        if shutil.which("ffmpeg") is None:
            raise MediaUnavailableError("FFmpeg is required for video generation.")
        job = await self.gateway.invoke(
            "jobs", "create", {"approved": True, "kind": "media_video", "input": {"prompt": prompt, "duration_seconds": duration}},
        )
        return await self._resume_job({"approved": True, "job_id": job["job_id"]})

    async def _resume_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Resuming a video job")
        job = (await self.gateway.invoke("jobs", "get", {"job_id": payload.get("job_id")}))["job"]
        if job["kind"] != "media_video" or job["status"] != "queued":
            raise ValueError("Only queued video jobs can be resumed.")
        prompt = self._prompt(job["input"])
        duration = self._int(job["input"].get("duration_seconds", 4), "duration_seconds", 1, 10)
        await self.gateway.invoke("jobs", "claim", {"job_id": job["job_id"], "worker_id": self.worker_id})
        start_worker(
            partial(self._video_worker, job["job_id"], prompt, duration, claimed=True),
            self._workers, self.gateway, {"job_id": job["job_id"], "worker_id": self.worker_id},
            logger, f"media-video-{job['job_id']}",
        )
        return {"job_id": job["job_id"], "status": "running"}

    async def _video_worker(self, job_id: str, prompt: str, duration: int, claimed: bool = False) -> None:
        worker = {"job_id": job_id, "worker_id": self.worker_id}
        staged: Path | None = None
        try:
            if not claimed:
                await self.gateway.invoke("jobs", "claim", worker)
            update = await self.gateway.invoke("jobs", "progress", {**worker, "progress": 10, "message": "Video modeli hazırlanıyor."})
            if update["status"] == "cancelled":
                return
            staging_dir = Path((await self.gateway.invoke("assets", "staging_dir", {}))["path"])
            staged = await run_thread(
                partial(self._render_video, prompt, duration, staging_dir), logger, self._remove_staged_output,
            )
            update = await self.gateway.invoke("jobs", "progress", {**worker, "progress": 90, "message": "Video kaydediliyor."})
            if update["status"] == "cancelled":
                return
            asset = await self.gateway.invoke(
                "assets", "store",
                {
                    "approved": True, "kind": "video", "filename": "video.mp4", "media_type": "video/mp4",
                    "source": "media", "staged_path": str(staged),
                    "metadata": {"prompt": prompt, "duration_seconds": duration, "job_id": job_id},
                },
            )
            await self.gateway.invoke("jobs", "complete", {**worker, "result": {"asset_id": asset["asset_id"], "download_url": asset["download_url"]}})
        except asyncio.CancelledError:
            await persist_cancellation(self.gateway, worker, logger)
            raise
        except Exception as exc:
            try:
                await self.gateway.invoke("jobs", "fail", {**worker, "error": str(exc)[:2_000] or exc.__class__.__name__})
            except Exception:
                logger.exception("Could not persist media job failure for %s.", job_id)
        finally:
            if staged is not None:
                self._remove_staged_output(staged)

    @staticmethod
    def _remove_staged_output(output: Path) -> None:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove staged media output: %s.", output)

    @contextmanager
    def _staged_output(self, staging: Path, suffix: str) -> Iterator[Path]:
        output = staging / f"{uuid.uuid4().hex}.{suffix}"
        completed = False
        try:
            yield output
            completed = True
        finally:
            if not completed:
                self._remove_staged_output(output)

    def _render_video(self, prompt: str, duration: int, staging: Path) -> Path:
        try:
            import torch
        except ImportError as exc:
            raise MediaUnavailableError("torch and diffusers are required for video generation.") from exc
        with self._staged_output(staging, "mp4") as output, tempfile.TemporaryDirectory(prefix="deeppanda-video-") as directory:
            source = Path(directory) / "source.mp4"
            video_model = video_model_path()
            if video_model.is_dir():
                import imageio.v2 as imageio
                from diffusers import TextToVideoSDPipeline

                device = "cuda" if torch.cuda.is_available() else "cpu"
                dtype = torch.float16 if device == "cuda" else torch.float32
                with self._pipeline_lock:
                    if self._video_pipeline is None:
                        self._video_pipeline = TextToVideoSDPipeline.from_pretrained(str(video_model), local_files_only=True, torch_dtype=dtype)
                        if device == "cuda":
                            self._video_pipeline.enable_model_cpu_offload()
                        else:
                            self._video_pipeline.to(device)
                    frames = self._video_pipeline(
                        prompt, height=256, width=256, num_frames=max(8, min(16, duration * 8)), num_inference_steps=20,
                    ).frames[0]
                imageio.mimsave(source, frames, fps=8, codec="libx264")
            else:
                frame = Path(directory) / "frame.png"
                self._render_image(prompt, 4, 512, 512).save(frame)
                self._ffmpeg([
                    "-loop", "1", "-i", str(frame),
                    "-vf", f"zoompan=z='min(zoom+0.0015,1.12)':d={duration * 24}:s=512x512:fps=24",
                    "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
                ])
            self._ffmpeg([
                "-i", str(source), "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-r", "24", "-movflags", "+faststart", str(output),
            ])
        return output

    async def _edit_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Saving an edited image")
        upload_suffix(payload, self.image_suffixes)
        raw = decode_upload(payload, self.max_image_bytes)
        operation = payload.get("operation", "grayscale")
        if operation not in {"grayscale", "rotate", "resize", "flip"}:
            raise ValueError("operation must be grayscale, rotate, resize or flip.")
        value = payload.get("value", 0)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("value must be an integer.")
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise MediaUnavailableError("Pillow is required for image editing.") from exc
        try:
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > 40_000_000:
                raise ValueError("Image exceeds the pixel limit.")
            image = image.convert("RGBA")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Image could not be decoded.") from exc
        if operation == "grayscale":
            image = image.convert("L").convert("RGBA")
        elif operation == "rotate":
            image = image.rotate(-(value % 360), expand=True)
        elif operation == "flip":
            image = ImageOps.mirror(image)
        else:
            size = max(16, min(value or 512, 4096))
            ratio = size / max(image.width, image.height)
            image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return await self._store(buffer.getvalue(), "image", "duzenlenen.png", "image/png", {"operation": operation, "value": value, "source_filename": payload["filename"]})

    async def _edit_video(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_approval(payload, "Saving an edited video")
        suffix = upload_suffix(payload, self.video_suffixes)
        raw = decode_upload(payload, self.max_media_bytes)
        start = self._number(payload.get("start_seconds", 0), "start_seconds", 0, 86_400)
        duration = self._number(payload.get("duration_seconds", 10), "duration_seconds", 0.1, 3_600)
        output_format = payload.get("output_format", "mp4")
        if output_format not in {"mp4", "webm"}:
            raise ValueError("output_format must be mp4 or webm.")
        staging_dir = Path((await self.gateway.invoke("assets", "staging_dir", {}))["path"])
        staged = await run_thread(
            partial(self._trim_video, raw, suffix, start, duration, output_format, staging_dir),
            logger, self._remove_staged_output,
        )
        try:
            return await self.gateway.invoke(
                "assets", "store",
                {
                    "approved": True, "kind": "video", "filename": f"kesit.{output_format}", "media_type": f"video/{output_format}",
                    "source": "media", "staged_path": str(staged),
                    "metadata": {"start_seconds": start, "duration_seconds": duration, "source_filename": payload["filename"]},
                },
            )
        finally:
            self._remove_staged_output(staged)

    def _trim_video(self, raw: bytes, suffix: str, start: float, duration: float, output_format: str, staging: Path) -> Path:
        codec = ["-c:v", "libvpx-vp9", "-c:a", "libopus"] if output_format == "webm" else ["-c:v", "libx264", "-c:a", "aac"]
        with self._staged_output(staging, output_format) as output, tempfile.TemporaryDirectory(prefix="deeppanda-trim-") as directory:
            source = Path(directory) / f"input{suffix}"
            source.write_bytes(raw)
            self._ffmpeg(["-ss", str(start), "-i", str(source), "-t", str(duration), *codec, str(output)])
        return output

    async def _analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        suffix = upload_suffix(payload, self.video_suffixes | self.audio_suffixes)
        raw = decode_upload(payload, self.max_media_bytes)
        transcribe = payload.get("transcribe", True)
        vision = payload.get("vision", False)
        if not isinstance(transcribe, bool) or not isinstance(vision, bool):
            raise TypeError("transcribe and vision must be booleans.")
        frames = await run_thread(partial(self._sample_frames, raw, suffix), logger) if suffix in self.video_suffixes else []
        result: dict[str, Any] = {
            "filename": payload["filename"],
            "frame_count": len(frames),
            "frames": [{"timestamp_seconds": index * 10} for index in range(len(frames))],
            "transcript": "",
            "transcript_status": "skipped",
            "vision_observations": [],
        }
        if transcribe:
            try:
                transcript = await self.gateway.invoke(
                    "speech", "transcribe", {"filename": payload["filename"], "content_base64": payload["content_base64"]},
                )
                result["transcript"] = transcript["transcript"]
                result["transcript_status"] = "completed"
            except Exception as exc:
                result["transcript_status"] = f"unavailable: {str(exc)[:300]}"
        if vision and frames:
            model = payload.get("model") or os.getenv("OLLAMA_VISION_MODEL", "") or None
            for index, frame in enumerate(frames[:3]):
                try:
                    response = await self.gateway.invoke(
                        "ollama", "chat",
                        {
                            "message": "Bu video karesini kanıta dayalı ve kısa analiz et. Görünen nesneleri, metni ve belirsizlikleri belirt.",
                            "model": model,
                            "images": [base64.b64encode(frame).decode("ascii")],
                            "messages": [],
                        },
                    )
                    message = response.get("message") if isinstance(response, dict) else None
                    content = message.get("content") if isinstance(message, dict) else None
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError("Vision provider returned no text content.")
                    result["vision_observations"].append({"timestamp_seconds": index * 10, "content": content[:4_000]})
                except Exception as exc:
                    result["vision_observations"].append({"timestamp_seconds": index * 10, "error": str(exc)[:300]})
        return result

    def _sample_frames(self, raw: bytes, suffix: str) -> list[bytes]:
        with tempfile.TemporaryDirectory(prefix="deeppanda-frames-") as directory:
            source = Path(directory) / f"input{suffix}"
            source.write_bytes(raw)
            pattern = Path(directory) / "frame-%03d.jpg"
            self._ffmpeg(["-i", str(source), "-vf", "fps=1/10,scale=640:-2", "-frames:v", str(self.analysis_frames), str(pattern)])
            paths = sorted(Path(directory).glob("frame-*.jpg"))
            if not paths:
                self._ffmpeg(["-i", str(source), "-frames:v", "1", str(pattern)])
                paths = sorted(Path(directory).glob("frame-*.jpg"))
            return [path.read_bytes() for path in paths]

    @staticmethod
    def _ffmpeg(arguments: list[str]) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise MediaUnavailableError("FFmpeg was not found.")
        try:
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", *arguments], check=True, capture_output=True, timeout=900, shell=False)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", "replace")[-500:] if exc.stderr else ""
            raise ValueError(f"FFmpeg failed: {detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("FFmpeg timed out.") from exc

    async def _store(self, data: bytes, kind: str, filename: str, media_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return await self.gateway.invoke(
            "assets", "store",
            {
                "approved": True, "kind": kind, "filename": filename, "media_type": media_type, "source": "media",
                "metadata": metadata, "content_base64": base64.b64encode(data).decode("ascii"),
            },
        )

    @staticmethod
    def _require_approval(payload: dict[str, Any], action: str) -> None:
        if payload.get("approved") is not True:
            raise MediaApprovalRequired(f"{action} requires approved=true.")

    def _prompt(self, payload: dict[str, Any]) -> str:
        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.max_prompt_chars:
            raise ValueError(f"prompt must be a non-empty string up to {self.max_prompt_chars} characters.")
        return prompt.strip()

    @staticmethod
    def _int(value: Any, key: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{key} must be an integer.")
        return max(minimum, min(value, maximum))

    @staticmethod
    def _number(value: Any, key: str, minimum: float, maximum: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{key} must be a number.")
        return float(max(minimum, min(value, maximum)))
