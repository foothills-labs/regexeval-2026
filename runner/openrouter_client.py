"""Minimal pinned OpenRouter client: one chat completion, fully logged.

Every call records the request config actually sent (including the
provider pin) and the provider/quantization OpenRouter says actually
served it, plus usage and cost. A response missing a resolved provider
is a failed request, not a prediction.
"""
from __future__ import annotations

import http.client
import json
import re
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

API_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class CallResult:
    ok: bool
    status: str  # "ok" | "http_error" | "parse_failure" | "no_provider"
    model_requested: str
    provider_requested: dict
    provider_resolved: str | None
    model_resolved: str | None
    content: str | None
    usage: dict = field(default_factory=dict)
    cost_usd: float | None = None
    latency_s: float = 0.0
    generation_id: str | None = None
    raw_response: dict | None = None
    error: str | None = None


def call(
    model: str,
    provider: dict,
    prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 300,
    reasoning: dict | None = None,
    api_key: str | None = None,
    max_retries: int = 5,
    timeout: float = 120.0,
) -> CallResult:
    api_key = api_key or os.environ["OPENROUTER_KEY"]
    body = {
        "model": model,
        "provider": provider,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate a natural-language description into a single "
                    "Python `re`-compatible regular expression. Reply with ONLY "
                    "the pattern in one fenced code block, no explanation."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    # Omitted rather than sent as null when unset. Several current models
    # reject `temperature` outright, and under require_parameters=true that
    # is a hard 404 -- so the sweep does not send it at all and takes each
    # model's default sampling. Diversity across k was verified empirically.
    if temperature is not None:
        body["temperature"] = temperature
    if reasoning is not None:
        body["reasoning"] = reasoning
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    delay = 2.0
    last_err = None
    for attempt in range(max_retries):
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read())
            latency = time.monotonic() - t0
            return _parse_success(model, provider, raw, latency)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            latency = time.monotonic() - t0
            if e.code == 429 or 500 <= e.code < 600:
                last_err = f"HTTP {e.code}: {body_text[:300]}"
                time.sleep(delay)
                delay *= 2
                continue
            return CallResult(
                ok=False,
                status="http_error",
                model_requested=model,
                provider_requested=provider,
                provider_resolved=None,
                model_resolved=None,
                content=None,
                latency_s=latency,
                error=f"HTTP {e.code}: {body_text[:500]}",
            )
        except (http.client.HTTPException, OSError, json.JSONDecodeError) as e:
            # Everything transport-level, not just urllib's own wrappers.
            # http.client.IncompleteRead -- a response body that stops early --
            # is an HTTPException and not a URLError, so it escaped an earlier
            # version of this handler and killed three collection processes
            # several hours into a sweep. urllib.error.URLError is an OSError
            # subclass, so it is still covered here.
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(delay)
            delay *= 2
            continue

    return CallResult(
        ok=False,
        status="http_error",
        model_requested=model,
        provider_requested=provider,
        provider_resolved=None,
        model_resolved=None,
        content=None,
        error=f"exhausted retries: {last_err}",
    )


def _parse_success(model: str, provider: dict, raw: dict, latency: float) -> CallResult:
    resolved_provider = raw.get("provider")
    resolved_model = raw.get("model")
    usage = raw.get("usage", {}) or {}
    cost = usage.get("cost")
    gen_id = raw.get("id")

    if not resolved_provider:
        return CallResult(
            ok=False,
            status="no_provider",
            model_requested=model,
            provider_requested=provider,
            provider_resolved=None,
            model_resolved=resolved_model,
            content=None,
            usage=usage,
            cost_usd=cost,
            latency_s=latency,
            generation_id=gen_id,
            raw_response=raw,
            error="response had no resolved 'provider' field",
        )

    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    # A 200 with no text is not an answer. This is how a reasoning model
    # that spent its whole budget thinking presents itself, and scoring it
    # as an empty pattern would look like a model that answered badly.
    if content is None or not content.strip():
        return CallResult(
            ok=False,
            status="parse_failure",
            model_requested=model,
            provider_requested=provider,
            provider_resolved=resolved_provider,
            model_resolved=resolved_model,
            content=None,
            usage=usage,
            cost_usd=cost,
            latency_s=latency,
            generation_id=gen_id,
            raw_response=raw,
            error=(
                "empty content: completion_tokens="
                f"{usage.get('completion_tokens')}, reasoning_tokens="
                f"{(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')}, "
                f"finish_reason={(raw.get('choices') or [{}])[0].get('finish_reason')!r}"
            ),
        )

    return CallResult(
        ok=True,
        status="ok",
        model_requested=model,
        provider_requested=provider,
        provider_resolved=resolved_provider,
        model_resolved=resolved_model,
        content=content,
        usage=usage,
        cost_usd=cost,
        latency_s=latency,
        generation_id=gen_id,
        raw_response=raw,
    )


def extract_pattern(content: str) -> str | None:
    """Strict extraction: last fenced code block, else the whole trimmed reply.

    Deliberately does no unwrapping -- see `normalize_pattern`. Keeping the
    two apart is what lets the leaderboard report a strict and a normalized
    score from the same committed responses.
    """
    if content is None:
        return None
    text = content.strip()
    if "```" in text:
        parts = text.split("```")
        # parts alternate: outside, inside, outside, inside, ...
        fenced = [parts[i] for i in range(1, len(parts), 2)]
        if fenced:
            block = fenced[-1]
            lines = block.splitlines()
            if lines and lines[0].strip().isalpha() and len(lines[0].strip()) < 20:
                lines = lines[1:]  # drop a language tag line, e.g. "regex"
            return "\n".join(lines).strip()
    return text


_WRAPPERS = [
    # Python raw/plain string literals: r'...', r"...", '...', "..."
    re.compile(r"^[rubfRUBF]{0,2}'(.*)'$", re.S),
    re.compile(r'^[rubfRUBF]{0,2}"(.*)"$', re.S),
    # inline-code backticks
    re.compile(r"^`(.*)`$", re.S),
    # JS-style /pattern/flags
    re.compile(r"^/(.*)/[gimsuxy]*$", re.S),
]


def normalize_pattern(pattern: str | None) -> tuple[str | None, list[str]]:
    """Strip host-language quoting a model wrapped around the pattern.

    Returns (normalized, notes). A model answering `r'\\d+$'` meant the
    pattern `\\d+$`; scoring the literal costs it the task for a reason
    that has nothing to do with regex ability. Every strip is recorded so
    the normalized score is auditable against the raw response.
    """
    if pattern is None:
        return None, []
    notes: list[str] = []
    text = pattern.strip()
    for _ in range(3):  # e.g. a backticked raw string
        for rx in _WRAPPERS:
            m = rx.fullmatch(text)
            if m and m.group(1):
                notes.append(f"stripped wrapper: {text[:12]!r} -> {m.group(1)[:12]!r}")
                text = m.group(1).strip()
                break
        else:
            break
    return text, notes
