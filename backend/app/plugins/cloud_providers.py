from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from app.plugins.contracts import PluginManifest


class CloudProviderError(Exception):
    pass


class CloudProviderAuthRequired(CloudProviderError):
    def __init__(self, provider: CloudProvider) -> None:
        super().__init__(f"{provider.name} için oturum açılmamış.")
        self.provider = provider


@dataclass(frozen=True)
class CloudProvider:
    provider_id: str
    name: str
    base_url: str
    default_model: str
    key_url: str
    signup_url: str
    free_tier: bool
    aliases: tuple[str, ...] = ()
    extra_headers: dict[str, str] = field(default_factory=dict)
    key_header: str | None = None

    @property
    def env_prefix(self) -> str:
        return self.provider_id.upper().replace("-", "_")


PROVIDERS: dict[str, CloudProvider] = {
    provider.provider_id: provider
    for provider in (
        CloudProvider(
            "gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-3.5-flash", "https://aistudio.google.com/apikey", "https://aistudio.google.com/",
            True, ("gemini", "google"),
        ),
        CloudProvider(
            "kimi", "Moonshot Kimi", "https://api.moonshot.ai/v1", "kimi-k2-turbo-preview",
            "https://platform.moonshot.ai/console/api-keys", "https://platform.moonshot.ai/",
            True, ("kimi", "moonshot"),
        ),
        CloudProvider(
            "openai", "OpenAI GPT", "https://api.openai.com/v1", "gpt-5.6-luna",
            "https://platform.openai.com/api-keys", "https://platform.openai.com/signup",
            False, ("gpt", "openai", "chatgpt"),
        ),
        CloudProvider(
            "anthropic", "Anthropic Claude", "https://api.anthropic.com/v1", "claude-sonnet-5",
            "https://console.anthropic.com/settings/keys", "https://console.anthropic.com/",
            False, ("claude", "anthropic"),
            extra_headers={"anthropic-version": "2023-06-01"}, key_header="x-api-key",
        ),
        CloudProvider(
            "groq", "Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile",
            "https://console.groq.com/keys", "https://console.groq.com/", True, ("groq",),
        ),
        CloudProvider(
            "openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "openrouter/auto",
            "https://openrouter.ai/settings/keys", "https://openrouter.ai/", True, ("openrouter",),
        ),
        CloudProvider(
            "deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat",
            "https://platform.deepseek.com/api_keys", "https://platform.deepseek.com/",
            False, ("deepseek",),
        ),
        CloudProvider(
            "mistral", "Mistral", "https://api.mistral.ai/v1", "mistral-small-latest",
            "https://console.mistral.ai/api-keys", "https://console.mistral.ai/", True,
            ("mistral", "codestral"),
        ),
        CloudProvider(
            "xai", "xAI Grok", "https://api.x.ai/v1", "grok-4.5",
            "https://console.x.ai/", "https://console.x.ai/", False, ("grok", "xai"),
        ),
        CloudProvider(
            "cerebras", "Cerebras", "https://api.cerebras.ai/v1", "llama-3.3-70b",
            "https://cloud.cerebras.ai/", "https://cloud.cerebras.ai/", True, ("cerebras",),
        ),
        CloudProvider(
            "github", "GitHub Models", "https://models.github.ai/inference", "openai/gpt-4.1-mini",
            "https://github.com/settings/personal-access-tokens", "https://github.com/marketplace/models",
            True, ("github models", "github"),
        ),
        CloudProvider(
            "huggingface", "Hugging Face", "https://router.huggingface.co/v1", "openai/gpt-oss-120b",
            "https://huggingface.co/settings/tokens", "https://huggingface.co/join", True,
            ("huggingface", "hugging face"),
        ),
        CloudProvider(
            "together", "Together AI", "https://api.together.ai/v1",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free", "https://api.together.ai/settings/api-keys",
            "https://api.together.ai/", True, ("together",),
        ),
    )
}

CONSULT_TASKS: dict[str, str] = {
    "info": "Soruyu doğru, kısa ve kaynağı belirsiz noktaları belirterek yanıtla.",
    "code": "İstenen kodu eksiksiz, çalışır ve açıklamalı olarak yaz. Varsayımları belirt.",
    "review": (
        "Verilen kodu veya önceki yanıtı revize et: hataları, eksikleri ve iyileştirmeleri "
        "önem sırasıyla yaz, ardından düzeltilmiş sürümü ver."
    ),
    "debug": (
        "Hatanın kök nedenini bul. Önce olası nedeni ve kanıtını açıkla, sonra en küçük düzeltmeyi "
        "ve doğrulama adımını ver. Emin değilsen bunu açıkça söyle."
    ),
}

_ASK_VERBS = r"(sor|soralım|danış|danis|kullan|gönder|gonder|ask|ile\s+(cevapla|yanıtla|yanitla))"
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._\-:/+=]{16,512}$")
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._\-:/@]{1,200}$")
MAX_CONSULT_PROVIDERS = 6


def auth_prompt(provider: CloudProvider) -> dict[str, Any]:
    return {
        "status": "auth_required",
        "provider": provider.provider_id,
        "provider_name": provider.name,
        "key_url": provider.key_url,
        "signup_url": provider.signup_url,
        "free_tier": provider.free_tier,
        "question": (
            f"{provider.name} için oturum açılmamış, bu yüzden istek gönderilmedi. "
            f"{provider.name} hesabında oturum açıp API anahtarı alabilir misiniz?"
        ),
    }


def detect_requested_provider(message: str) -> str | None:
    """Return a provider only when the user explicitly asks to use it, e.g. "gemini'ye sor"."""
    text = message.casefold()
    for provider in PROVIDERS.values():
        for alias in provider.aliases:
            pattern = rf"\b{re.escape(alias)}\b[\w'’]*\s+(?:\w+\s+){{0,2}}{_ASK_VERBS}\b"
            if re.search(pattern, text):
                return provider.provider_id
    return None


class CloudProvidersPlugin:
    manifest = PluginManifest(
        plugin_id="cloud_providers",
        display_name="Bulut API sağlayıcıları",
        description=(
            "Gemini, Kimi, GPT, Claude ve diğer OpenAI uyumlu API'lere yalnızca kullanıcı "
            "açıkça seçtiğinde soru gönderir; oturum yoksa durur ve oturum açmaya yönlendirir."
        ),
        actions=("catalog", "save_key", "remove_key", "models", "chat", "consult"),
    )

    def __init__(
        self,
        store_path: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        data_dir = Path(os.getenv("AI_DATA_DIR", "/data"))
        self.store_path = store_path or data_dir / "cloud-providers.json"
        self.transport = transport
        self._lock = asyncio.Lock()

    def _read_store(self) -> dict[str, dict[str, str]]:
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise CloudProviderError("Bulut sağlayıcı ayar dosyası okunamadı.") from exc
        return data if isinstance(data, dict) else {}

    def _write_store(self, data: dict[str, dict[str, str]]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=self.store_path.parent, prefix=".cloud-providers-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.store_path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _provider(provider_id: Any) -> CloudProvider:
        if not isinstance(provider_id, str) or provider_id not in PROVIDERS:
            raise ValueError("Bilinmeyen bulut sağlayıcı.")
        return PROVIDERS[provider_id]

    def _credentials(self, provider: CloudProvider) -> tuple[str, str]:
        stored = self._read_store().get(provider.provider_id, {})
        key = os.getenv(f"{provider.env_prefix}_API_KEY") or stored.get("api_key", "")
        model = stored.get("model") or os.getenv(f"{provider.env_prefix}_MODEL") or provider.default_model
        return key, model

    def _headers(self, provider: CloudProvider, key: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {key}", **provider.extra_headers}
        if provider.key_header:
            headers[provider.key_header] = key
        return headers

    @staticmethod
    def auth_prompt(provider: CloudProvider) -> dict[str, Any]:
        return auth_prompt(provider)

    def _catalog_entry(self, provider: CloudProvider, store: dict[str, dict[str, str]]) -> dict[str, Any]:
        stored = store.get(provider.provider_id, {})
        env_key = bool(os.getenv(f"{provider.env_prefix}_API_KEY"))
        return {
            "id": provider.provider_id,
            "name": provider.name,
            "configured": env_key or bool(stored.get("api_key")),
            "key_source": "env" if env_key else ("ui" if stored.get("api_key") else None),
            "model": stored.get("model") or os.getenv(f"{provider.env_prefix}_MODEL") or provider.default_model,
            "free_tier": provider.free_tier,
            "key_url": provider.key_url,
            "signup_url": provider.signup_url,
        }

    async def invoke(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "catalog":
            store = self._read_store()
            return {
                "providers": [self._catalog_entry(provider, store) for provider in PROVIDERS.values()],
                "tasks": list(CONSULT_TASKS),
            }
        if action == "save_key":
            return await self._save_key(payload)
        if action == "remove_key":
            provider = self._provider(payload.get("provider"))
            async with self._lock:
                store = self._read_store()
                removed = store.pop(provider.provider_id, None) is not None
                self._write_store(store)
            return {"provider": provider.provider_id, "removed": removed}
        if action == "models":
            return await self._models(self._provider(payload.get("provider")))
        if action == "chat":
            return await self._chat(payload)
        if action == "consult":
            return await self._consult(payload)
        raise ValueError(f"Unsupported cloud provider action: {action}")

    async def _save_key(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider(payload.get("provider"))
        api_key = payload.get("api_key")
        if not isinstance(api_key, str) or not _KEY_PATTERN.fullmatch(api_key.strip()):
            raise ValueError("API anahtarı geçersiz görünüyor.")
        model = payload.get("model")
        if model is not None and (not isinstance(model, str) or not _MODEL_PATTERN.fullmatch(model)):
            raise ValueError("Model adı geçersiz.")
        async with self._lock:
            store = self._read_store()
            entry = {"api_key": api_key.strip()}
            if model:
                entry["model"] = model
            store[provider.provider_id] = entry
            self._write_store(store)
        return self._catalog_entry(provider, self._read_store())

    def _client(self, provider: CloudProvider, timeout: float = 120.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=provider.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=self.transport,
        )

    async def _models(self, provider: CloudProvider) -> dict[str, Any]:
        key, model = self._credentials(provider)
        if not key:
            return self.auth_prompt(provider)
        async with self._client(provider, 30.0) as client:
            response = await client.get("/models", headers=self._headers(provider, key))
        if response.status_code in {401, 403}:
            raise CloudProviderError(f"{provider.name} API anahtarı reddedildi.")
        response.raise_for_status()
        data = response.json()
        items = data.get("data") if isinstance(data, dict) else data
        names = sorted(
            {item["id"] for item in items or [] if isinstance(item, dict) and isinstance(item.get("id"), str)}
        )
        return {"provider": provider.provider_id, "default_model": model, "models": names[:500]}

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider(payload.get("provider"))
        key, default_model = self._credentials(provider)
        if not key:
            raise CloudProviderAuthRequired(provider)
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be non-empty text.")
        model = payload.get("model") or default_model
        if not isinstance(model, str) or not _MODEL_PATTERN.fullmatch(model):
            raise ValueError("Model adı geçersiz.")
        chat_messages: list[dict[str, str]] = []
        system_prompt = payload.get("system_prompt")
        if isinstance(system_prompt, str) and system_prompt.strip():
            chat_messages.append({"role": "system", "content": system_prompt})
        for item in payload.get("messages") or []:
            if (
                isinstance(item, dict)
                and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str)
            ):
                chat_messages.append({"role": item["role"], "content": item["content"]})
        chat_messages.append({"role": "user", "content": message})

        async with self._client(provider) as client:
            response = await client.post(
                "/chat/completions",
                headers=self._headers(provider, key),
                json={"model": model, "messages": chat_messages, "stream": False},
            )
        if response.status_code in {401, 403}:
            raise CloudProviderError(f"{provider.name} API anahtarı reddedildi; oturumu yenileyin.")
        if response.status_code == 429:
            raise CloudProviderError(f"{provider.name} kota/limit aşıldı (429).")
        if response.status_code >= 400:
            raise CloudProviderError(
                f"{provider.name} isteği başarısız oldu (HTTP {response.status_code}); model adı '{model}' "
                "bu sağlayıcıda geçerli olmayabilir."
            )
        try:
            result = response.json()
        except ValueError as exc:
            raise CloudProviderError(f"{provider.name} geçersiz JSON döndürdü.") from exc
        choices = result.get("choices") if isinstance(result, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else None
        reply = choice.get("message") if isinstance(choice, dict) else None
        content = reply.get("content") if isinstance(reply, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise CloudProviderError(f"{provider.name} metin yanıtı döndürmedi.")
        normalized: dict[str, Any] = {
            "model": f"{provider.provider_id}:{result.get('model', model)}",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
            "provider": provider.provider_id,
        }
        if isinstance(result.get("usage"), dict):
            normalized["usage"] = result["usage"]
        return normalized

    async def _consult(self, payload: dict[str, Any]) -> dict[str, Any]:
        providers = payload.get("providers")
        if (
            not isinstance(providers, list)
            or not providers
            or len(providers) > MAX_CONSULT_PROVIDERS
            or len(set(map(str, providers))) != len(providers)
        ):
            raise ValueError(f"1-{MAX_CONSULT_PROVIDERS} farklı sağlayıcı seçilmelidir.")
        resolved = [self._provider(item) for item in providers]
        task = payload.get("task", "info")
        if task not in CONSULT_TASKS:
            raise ValueError("Bilinmeyen danışma görevi.")
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 20_000:
            raise ValueError("Soru 1-20000 karakter olmalıdır.")
        previous = payload.get("previous_answer")
        if previous is not None and (not isinstance(previous, str) or len(previous) > 40_000):
            raise ValueError("previous_answer en fazla 40000 karakter olabilir.")
        prompt = message
        if previous and previous.strip():
            prompt = f"{message}\n\n--- Yerel modelin önceki yanıtı (incele/revize et) ---\n{previous}"
        system_prompt = (
            "Bir DeepPanda kullanıcısına ikinci görüş veriyorsun. Türkçe yanıt ver. "
            f"Görev: {CONSULT_TASKS[task]}"
        )

        async def ask(provider: CloudProvider) -> dict[str, Any]:
            try:
                result = await self._chat(
                    {"provider": provider.provider_id, "message": prompt, "system_prompt": system_prompt}
                )
            except CloudProviderAuthRequired:
                return self.auth_prompt(provider)
            except (CloudProviderError, httpx.HTTPError) as exc:
                return {
                    "status": "error",
                    "provider": provider.provider_id,
                    "provider_name": provider.name,
                    "error": str(exc) or type(exc).__name__,
                }
            return {
                "status": "ok",
                "provider": provider.provider_id,
                "provider_name": provider.name,
                "model": result["model"],
                "content": result["message"]["content"],
            }

        results = await asyncio.gather(*(ask(provider) for provider in resolved))
        return {"task": task, "results": list(results)}
