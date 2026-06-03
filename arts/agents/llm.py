"""LLM wrapper used by the reasoning agents — supports Claude or Gemini.

Pick the provider in ``config.yaml`` (``llm.provider``):
  * ``anthropic`` — Claude (key: ANTHROPIC_API_KEY)
  * ``gemini``    — Google Gemini (key: GEMINI_API_KEY or GOOGLE_API_KEY)
  * ``template``  — no model; agents use their offline template fallback

Graceful degradation: if the chosen provider has no key, the wrapper reports
``available == False`` and every agent falls back to template mode, so the whole
pipeline still runs end-to-end offline.

Both providers expose the same ``complete_text`` / ``complete_json`` interface so
the agents don't care which model is behind them.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..config import Config
from ..utils import get_logger

log = get_logger("llm")

# Claude models that accept adaptive thinking; conservative to avoid 400s.
_ADAPTIVE_THINKING_MODELS = ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")
_GEMINI_DEFAULT = "gemini-2.0-flash"


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.provider = cfg.llm_provider
        self.model: str = cfg.get("llm.model", "claude-opus-4-8")
        self.max_tokens: int = int(cfg.get("llm.max_tokens", 4000))
        self.use_thinking: bool = bool(cfg.get("llm.thinking", True))
        self._client = None
        self._gemini_key: Optional[str] = None
        self._available = False

        if self.provider == "anthropic":
            try:
                import anthropic

                self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
                self._available = True
                log.info("LLM ready: Anthropic %s (thinking=%s)", self.model, self.use_thinking)
            except Exception as e:  # pragma: no cover
                log.warning("Anthropic client unavailable (%s) — using template mode", e)
        elif self.provider == "gemini":
            self._gemini_key = cfg.gemini_api_key
            if "gemini" not in self.model.lower():
                self.model = cfg.get("llm.gemini_model", _GEMINI_DEFAULT)
            self._available = bool(self._gemini_key)
            log.info("LLM ready: Gemini %s", self.model) if self._available else \
                log.info("No Gemini key — running in template mode")
        else:
            log.info("No LLM key — running in template mode")

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------ #
    def _thinking_param(self) -> Optional[dict]:
        if self.use_thinking and self.model in _ADAPTIVE_THINKING_MODELS:
            return {"type": "adaptive"}
        return None

    def _anthropic(self, system: str, user: str, max_tokens: int, allow_thinking: bool) -> str:
        import anthropic

        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user}],
        }
        thinking = self._thinking_param() if allow_thinking else None
        if thinking:
            kwargs["thinking"] = thinking
        try:
            resp = self._client.messages.create(**kwargs)
        except anthropic.BadRequestError as e:
            if thinking:
                log.warning("BadRequest with thinking (%s); retrying without it", e)
                kwargs.pop("thinking", None)
                resp = self._client.messages.create(**kwargs)
            else:
                raise
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    def _gemini(self, system: str, user: str, max_tokens: int, json_mode: bool) -> str:
        import requests

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        gen_cfg: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": 0.8}
        if json_mode:
            gen_cfg["responseMimeType"] = "application/json"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen_cfg,
        }
        r = requests.post(url, params={"key": self._gemini_key}, json=body, timeout=120)
        r.raise_for_status()
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts).strip()

    def _call(self, system: str, user: str, max_tokens: int, allow_thinking: bool, json_mode: bool) -> str:
        if self.provider == "gemini":
            return self._gemini(system, user, max_tokens, json_mode)
        return self._anthropic(system, user, max_tokens, allow_thinking)

    # ------------------------------------------------------------------ #
    def complete_text(self, system: str, user: str, max_tokens: Optional[int] = None,
                      allow_thinking: bool = False) -> str:
        return self._call(system, user, max_tokens or self.max_tokens, allow_thinking, json_mode=False)

    def complete_json(self, system: str, user: str, max_tokens: Optional[int] = None,
                      allow_thinking: bool = True) -> dict:
        """Call the model and parse a single JSON object from its reply."""
        sys = system.rstrip() + (
            "\n\nReturn ONLY a single valid JSON object. No markdown fences, no prose "
            "before or after the JSON."
        )
        raw = self._call(sys, user, max_tokens or self.max_tokens, allow_thinking, json_mode=True)
        return _extract_json(raw)


# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict:
    """Best-effort extraction of one JSON object from a model reply."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"Could not parse JSON from model reply: {text[:200]!r}")
