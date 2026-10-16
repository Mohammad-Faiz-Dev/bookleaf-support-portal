"""Thin LLM client: Google Gemini (generateContent REST, JSON output) or any OpenAI-compatible
/chat/completions endpoint, chosen by config (GEMINI_API_KEY / OPENAI_API_KEY).

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
        gemini = getattr(self.s, "ai_provider", "openai") == "gemini"
        if gemini:
            gen = {"maxOutputTokens": max(max_tokens, 64) * 8, "temperature": temperature,
                   # gemini-2.5-flash "thinks" by default; disable it for fast, short outputs
                   "thinkingConfig": {"thinkingBudget": 0}}
            if json_mode:
                gen["responseMimeType"] = "application/json"
            body = {"systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen}
            models = [self.s.ai_model] + list(getattr(self.s, "ai_fallback_models", []))
            headers = {"x-goog-api-key": self.s.ai_api_key}
        else:
            body = {
                "model": self.s.ai_model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            models = [self.s.ai_model]
            headers = {"Authorization": f"Bearer {self.s.ai_api_key}"}
        last_err: Exception | None = None
        attempts = [(m, a) for m in models for a in range(retries + 1)]
        for i, (model, attempt) in enumerate(attempts):
            if gemini:
                url = f"{self.s.ai_base_url.rstrip('/')}/models/{model}:generateContent"
            else:
                url = f"{self.s.ai_base_url.rstrip('/')}/chat/completions"
            try:
                with httpx.Client(timeout=self.s.ai_timeout_s, transport=self._transport) as c:
                    r = c.post(url, json=body, headers=headers)
                if r.status_code in (404, 429) or r.status_code >= 500:
                    raise LLMUnavailable(f"AI provider returned {r.status_code}")
                r.raise_for_status()
                data = r.json()
                if gemini:
                    usage = data.get("usageMetadata") or {}
                    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
                    pt, ct = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
                else:
                    usage = data.get("usage") or {}
                    text = data["choices"][0]["message"]["content"]
                    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
                log.info("llm call ok model=%s prompt_tokens=%s completion_tokens=%s", model, pt, ct)
                if not text.strip():
                    raise ValueError("empty AI response")
                return text.strip()
            except (httpx.HTTPError, LLMUnavailable, KeyError, IndexError, ValueError) as e:
                last_err = e
                log.warning("llm call failed (model %s attempt %s): %s", model, attempt + 1, e)
                if i + 1 < len(attempts) and attempts[i + 1][0] == model:
                    time.sleep(0.5 * (2 ** attempt))
        raise LLMUnavailable(str(last_err))
