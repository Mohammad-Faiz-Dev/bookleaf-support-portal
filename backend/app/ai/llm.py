"""Thin LLM client for any OpenAI-compatible /chat/completions endpoint.

Kept provider-agnostic on purpose: swapping to another vendor (or a local model) is a
config change (AI_BASE_URL / AI_MODEL), not a code change. Raises LLMUnavailable on
missing key, timeouts, rate limits or bad responses so callers can degrade gracefully.
"""
import logging
import time

import httpx

from ..config import get_settings

log = logging.getLogger("bookleaf.ai")


class LLMUnavailable(Exception):
    pass


class LLMClient:
    def __init__(self, settings=None, transport: httpx.BaseTransport | None = None):
        self.s = settings or get_settings()
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.s.ai_api_key)

    def chat(self, system: str, user: str, *, max_tokens: int, temperature: float = 0.3,
             json_mode: bool = False, retries: int = 1) -> str:
        if not self.enabled:
            raise LLMUnavailable("No AI API key configured")
        body = {
            "model": self.s.ai_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.s.ai_api_key}"}
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=self.s.ai_timeout_s, transport=self._transport) as c:
                    r = c.post(f"{self.s.ai_base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
                if r.status_code == 429 or r.status_code >= 500:
                    raise LLMUnavailable(f"AI provider returned {r.status_code}")
                r.raise_for_status()
                data = r.json()
                usage = data.get("usage") or {}
                log.info("llm call ok model=%s prompt_tokens=%s completion_tokens=%s",
                         self.s.ai_model, usage.get("prompt_tokens"), usage.get("completion_tokens"))
                return data["choices"][0]["message"]["content"].strip()
            except (httpx.HTTPError, LLMUnavailable, KeyError, ValueError) as e:
                last_err = e
                log.warning("llm call failed (attempt %s): %s", attempt + 1, e)
                if attempt < retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise LLMUnavailable(str(last_err))
