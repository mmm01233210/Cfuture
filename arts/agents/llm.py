"""Thin Claude (Anthropic) wrapper used by the reasoning agents.

Design goals:
  * One place that talks to the model, so every agent shares caching / retry /
    parsing behaviour.
  * Graceful degradation: when no ``ANTHROPIC_API_KEY`` is set the wrapper
    reports ``available == False`` and each agent falls back to template mode,
    so the whole pipeline still runs end-to-end offline.

Notes on the request shape (Claude Opus 4.8 / Sonnet 4.6):
  * Stable, reusable instructions go in ``system`` with ``cache_control`` so
    repeated runs can hit the prompt cache; the volatile paper text goes in the
    user turn after it.
  * Adaptive thinking is used for the quality-sensitive reasoning steps.
  * ``temperature`` / ``budget_tokens`` are intentionally never sent — both are
    removed on Opus 4.8/4.7 and would 400.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..config import Config
from ..utils import get_logger

log = get_logger("llm")

# Models that accept adaptive thinking; keep conservative to avoid 400s.
_ADAPTIVE_THINKING_MODELS = ("claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6")


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.model: str = cfg.get("llm.model", "claude-opus-4-8")
        self.max_tokens: int = int(cfg.get("llm.max_tokens", 2200))
        self.use_thinking: bool = bool(cfg.get("llm.thinking", True))
        self._client = None
        self._available = False
        if cfg.llm_provider == "anthropic" and cfg.anthropic_api_key:
            try:
                import anthropic

                self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
                self._available = True
                log.info("LLM ready: Anthropic %s (thinking=%s)", self.model, self.use_thinking)
            except Exception as e:  # pragma: no cover - import/runtime guard
                log.warning("Anthropic client unavailable (%s) — using template mode", e)
        else:
            log.info("No ANTHROPIC_API_KEY — running in template mode")

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------ #
    def _thinking_param(self) -> Optional[dict]:
        if self.use_thinking and self.model in _ADAPTIVE_THINKING_MODELS:
            return {"type": "adaptive"}
        return None

    def _call(self, system: str, user: str, max_tokens: int, allow_thinking: bool) -> str:
        """Single Messages API call, returning the concatenated text output."""
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
            # Most likely an unsupported thinking/effort param for this model.
            if thinking:
                log.warning("BadRequest with thinking (%s); retrying without it", e)
                kwargs.pop("thinking", None)
                resp = self._client.messages.create(**kwargs)
            else:
                raise
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    # ------------------------------------------------------------------ #
    def complete_text(self, system: str, user: str, max_tokens: Optional[int] = None,
                      allow_thinking: bool = False) -> str:
        return self._call(system, user, max_tokens or self.max_tokens, allow_thinking)

    def complete_json(self, system: str, user: str, max_tokens: Optional[int] = None,
                      allow_thinking: bool = True) -> dict:
        """Call the model and parse a single JSON object from its reply."""
        sys = system.rstrip() + (
            "\n\nReturn ONLY a single valid JSON object. No markdown fences, no prose "
            "before or after the JSON."
        )
        raw = self._call(sys, user, max_tokens or self.max_tokens, allow_thinking)
        return _extract_json(raw)


# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict:
    """Best-effort extraction of one JSON object from a model reply."""
    text = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} span.
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
