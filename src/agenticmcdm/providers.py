"""Provider adapters.

Three request shapes cover the five services in the registry: an OpenAI-compatible chat
endpoint, the Anthropic Messages endpoint, and the Google generateContent endpoint. Each
adapter is thin on purpose. It sends the prompt, returns the raw bytes and the extracted
text, and records what the provider reported back.

Two rules the protocol imposes on every adapter:

- **No decoding parameters are sent unless the registry asks for them.** The study measures
  the deployed service at its documented default, so silently sending `temperature=0` would
  change the object of study.
- **Nothing is enabled beyond plain text generation.** No tools, no web access, no memory,
  no provider-native JSON enforcement, because enforced-schema availability differs between
  providers and would make the validity rate incomparable.

Credentials come from environment variables and are never written to disk or to the ledger.

VERIFY BEFORE THE RUN: endpoint paths, header names and response shapes below reflect the
public APIs as the authors understood them when this file was written. Provider APIs change.
Run `python -m agenticmcdm.providers --smoke` against each configured provider and confirm
the response parses before spending the collection budget.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_TIMEOUT = 180


class TransportError(RuntimeError):
    """No model output was produced. Retryable once inside the same scheduled slot."""


@dataclass
class Reply:
    """One physical API response."""

    text: str
    raw: bytes
    status: int
    latency_ms: int
    provider_request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    reported_model: str | None


def _post(url: str, headers: dict[str, str], body: dict, timeout: int) -> tuple[bytes, int, dict]:
    payload = json.dumps(body).encode()
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return raw, int((time.monotonic() - started) * 1000), dict(response.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500].decode("utf-8", "replace")
        raise TransportError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportError(f"transport failure calling {url}: {exc}") from exc


def _setting(settings: dict, name: str, default: str) -> str:
    """Read a registry setting, treating an empty CSV cell as absent rather than as a value."""
    return (settings.get(name) or "").strip() or default


def _key(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise TransportError(
            f"environment variable {env_name} is not set; credentials are never committed"
        )
    return value


def _decoding(settings: dict) -> dict:
    """Only the decoding parameters the registry explicitly requests."""
    out = {}
    for key in ("temperature", "top_p", "seed", "max_output_tokens"):
        value = settings.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, str):
            value = float(value) if "." in value else int(value)
        out[key] = value
    return out


def call_openai_compatible(
    model: str, system: str, user: str, settings: dict, timeout: int = DEFAULT_TIMEOUT
) -> Reply:
    """OpenAI-style chat completions. Also serves xAI, Moonshot and other compatible hosts."""
    base = _setting(settings, "base_url", "https://api.openai.com/v1").rstrip("/")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    decoding = _decoding(settings)
    if "max_output_tokens" in decoding:
        body["max_tokens"] = decoding.pop("max_output_tokens")
    body.update(decoding)

    raw, latency, headers = _post(
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {_key(_setting(settings, "key_env", ""))}",
         "Content-Type": "application/json"},
        body, timeout,
    )
    data = json.loads(raw)
    usage = data.get("usage") or {}
    return Reply(
        text=data["choices"][0]["message"]["content"],
        raw=raw, status=200, latency_ms=latency,
        provider_request_id=headers.get("x-request-id") or data.get("id"),
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        reported_model=data.get("model"),
    )


def call_anthropic(
    model: str, system: str, user: str, settings: dict, timeout: int = DEFAULT_TIMEOUT
) -> Reply:
    """Anthropic Messages endpoint. `max_tokens` is required by this API."""
    decoding = _decoding(settings)
    body = {
        "model": model,
        "max_tokens": decoding.pop("max_output_tokens", 4096),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    body.update({k: v for k, v in decoding.items() if k in ("temperature", "top_p")})

    raw, latency, headers = _post(
        _setting(settings, "base_url", "https://api.anthropic.com/v1").rstrip("/") + "/messages",
        {"x-api-key": _key(settings["key_env"]),
         "anthropic-version": _setting(settings, "api_version", "2023-06-01"),
         "Content-Type": "application/json"},
        body, timeout,
    )
    data = json.loads(raw)
    text = "".join(block.get("text", "") for block in data.get("content", []))
    usage = data.get("usage") or {}
    return Reply(
        text=text, raw=raw, status=200, latency_ms=latency,
        provider_request_id=headers.get("request-id") or data.get("id"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        reported_model=data.get("model"),
    )


def call_google(
    model: str, system: str, user: str, settings: dict, timeout: int = DEFAULT_TIMEOUT
) -> Reply:
    """Google generateContent endpoint."""
    base = _setting(
        settings, "base_url", "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    body: dict = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
    }
    decoding = _decoding(settings)
    config = {}
    if "temperature" in decoding:
        config["temperature"] = decoding["temperature"]
    if "top_p" in decoding:
        config["topP"] = decoding["top_p"]
    if "max_output_tokens" in decoding:
        config["maxOutputTokens"] = decoding["max_output_tokens"]
    if config:
        body["generationConfig"] = config

    raw, latency, headers = _post(
        f"{base}/models/{model}:generateContent",
        {"x-goog-api-key": _key(settings["key_env"]), "Content-Type": "application/json"},
        body, timeout,
    )
    data = json.loads(raw)
    candidates = data.get("candidates") or []
    if not candidates:
        raise TransportError(f"no candidate returned: {raw[:300]!r}")
    parts = candidates[0].get("content", {}).get("parts", [])
    usage = data.get("usageMetadata") or {}
    return Reply(
        text="".join(part.get("text", "") for part in parts),
        raw=raw, status=200, latency_ms=latency,
        provider_request_id=headers.get("x-request-id"),
        input_tokens=usage.get("promptTokenCount"),
        output_tokens=usage.get("candidatesTokenCount"),
        reported_model=candidates[0].get("modelVersion") or model,
    )


ADAPTERS = {
    "openai_compatible": call_openai_compatible,
    "anthropic": call_anthropic,
    "google": call_google,
}


def call(adapter: str, model: str, system: str, user: str, settings: dict) -> Reply:
    """Dispatch to the adapter named in the registry row."""
    adapter = (adapter or "").strip() or "openai_compatible"
    if adapter not in ADAPTERS:
        raise TransportError(f"unknown adapter {adapter!r}; known: {sorted(ADAPTERS)}")
    return ADAPTERS[adapter](model, system, user, settings)
