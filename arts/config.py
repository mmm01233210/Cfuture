"""Configuration loading: merges ``config.yaml`` with environment / ``.env``."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


class Config:
    """Thin wrapper over the parsed YAML with dotted-path access and env secrets."""

    def __init__(self, data: dict[str, Any]):
        self._d = data

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Config":
        load_dotenv(REPO_ROOT / ".env")  # no-op if the file is absent
        cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
        data: dict[str, Any] = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        cfg = cls(data)
        cfg._apply_env_overrides()
        return cfg

    # -- access ----------------------------------------------------------- #
    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self._d
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def __getitem__(self, key: str) -> Any:
        return self._d[key]

    @property
    def data(self) -> dict[str, Any]:
        return self._d

    # -- convenience ------------------------------------------------------ #
    @property
    def fields(self) -> list[str]:
        return list(self.get("fields", ["ai"]))

    @property
    def output_dir(self) -> Path:
        return REPO_ROOT / self.get("output_dir", "output")

    @property
    def score_threshold(self) -> int:
        return int(self.get("scoring.threshold", 75))

    def font_path(self, weight: str = "regular") -> str:
        rel = self.get(f"fonts.{weight}", self.get("fonts.regular", "assets/fonts/Tajawal-Regular.ttf"))
        p = Path(rel)
        return str(p if p.is_absolute() else REPO_ROOT / rel)

    # -- secrets (env only) ---------------------------------------------- #
    @property
    def anthropic_api_key(self) -> str | None:
        return os.getenv("ANTHROPIC_API_KEY")

    @property
    def gemini_api_key(self) -> str | None:
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    @property
    def llm_provider(self) -> str:
        # a provider only takes effect when its key is actually present
        prov = str(self.get("llm.provider", "anthropic")).lower()
        if prov == "anthropic" and not self.anthropic_api_key:
            return "template"
        if prov == "gemini" and not self.gemini_api_key:
            return "template"
        return prov

    @property
    def tiktok_token(self) -> str | None:
        return os.getenv("TIKTOK_ACCESS_TOKEN")

    # -- env overrides ---------------------------------------------------- #
    def _apply_env_overrides(self) -> None:
        """Allow a few high-value settings to be overridden from the env."""
        fields_env = os.getenv("FIELDS")
        if fields_env:
            self._d["fields"] = [f.strip() for f in fields_env.split(",") if f.strip()]
        model_env = os.getenv("LLM_MODEL")
        if model_env:
            self._d.setdefault("llm", {})["model"] = model_env
        voice_env = os.getenv("TTS_VOICE")
        if voice_env:
            self._d.setdefault("voiceover", {})["voice"] = voice_env
