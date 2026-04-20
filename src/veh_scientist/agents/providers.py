"""Minimal HTTP providers for remote LLM-backed dashboard agents."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from veh_scientist.agents.config import AgentConfig


class ProviderError(RuntimeError):
    """Raised when a provider request fails."""


def generate_text(
    config: AgentConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float = 20.0,
    max_tokens: int = 320,
) -> str:
    """Generate a short text completion using the configured provider."""

    normalized = config.normalized()
    if not normalized.has_credentials():
        raise ProviderError("Missing base URL, API key, or model name.")

    if normalized.provider == "openai":
        return _openai_generate(
            normalized,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    if normalized.provider == "anthropic":
        return _anthropic_generate(
            normalized,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    if normalized.provider == "gemini":
        return _gemini_generate(
            normalized,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    raise ProviderError(f"Unsupported provider: {normalized.provider}")


def test_connection(config: AgentConfig) -> str:
    """Run a lightweight connection test."""

    return generate_text(
        config,
        system_prompt="Reply in one short sentence.",
        user_prompt="Return the exact text: connection ok",
        timeout_seconds=12.0,
    )


def _http_post_json(
    url: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    request = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {exc.code}: {details}") from exc
    except URLError as exc:
        raise ProviderError(f"Network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderError("Request timed out.") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider returned non-JSON content.") from exc


def _openai_generate(
    config: AgentConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> str:
    url = _openai_url(config.base_url)
    body = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if "dashscope.aliyuncs.com" in config.base_url and config.model_name.lower().startswith("qwen"):
        body["enable_thinking"] = False
    payload = _http_post_json(
        url,
        body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        timeout_seconds=timeout_seconds,
    )
    choices = payload.get("choices") or []
    if not choices:
        raise ProviderError("Provider returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
    raise ProviderError("Provider returned an unsupported content shape.")


def _anthropic_generate(
    config: AgentConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> str:
    url = _anthropic_url(config.base_url)
    payload = _http_post_json(
        url,
        {
            "model": config.model_name,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        headers={
            "Content-Type": "application/json",
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
        },
        timeout_seconds=timeout_seconds,
    )
    content = payload.get("content") or []
    texts = [part.get("text", "") for part in content if isinstance(part, dict)]
    if not texts:
        raise ProviderError("Provider returned no content blocks.")
    return "".join(texts).strip()


def _gemini_generate(
    config: AgentConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_seconds: float,
    max_tokens: int,
) -> str:
    url = _gemini_url(config.base_url, config.model_name, config.api_key)
    payload = _http_post_json(
        url,
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens,
            },
        },
        headers={"Content-Type": "application/json"},
        timeout_seconds=timeout_seconds,
    )
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ProviderError("Provider returned no candidates.")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    if not texts:
        raise ProviderError("Provider returned no text parts.")
    return "".join(texts).strip()


def _openai_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return f"{trimmed}/chat/completions"
    if trimmed.endswith("/v1/"):
        return f"{trimmed}chat/completions"
    return f"{trimmed}/chat/completions"


def _anthropic_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/messages"):
        return trimmed
    return f"{trimmed}/messages"


def _gemini_url(base_url: str, model_name: str, api_key: str) -> str:
    trimmed = base_url.rstrip("/")
    if ":generateContent" in trimmed:
        separator = "&" if "?" in trimmed else "?"
        return f"{trimmed}{separator}{urlencode({'key': api_key})}"
    if "/models/" in trimmed:
        return f"{trimmed}:generateContent?{urlencode({'key': api_key})}"

    parsed = urlparse(trimmed)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1beta") or path.endswith("/v1"):
        return f"{trimmed}/models/{model_name}:generateContent?{urlencode({'key': api_key})}"
    return f"{trimmed}/models/{model_name}:generateContent?{urlencode({'key': api_key})}"
