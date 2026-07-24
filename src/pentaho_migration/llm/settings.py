"""Persisted LLM settings for the expression-translation stage.

Stored as JSON under config/ (gitignored) — override the directory with
the PENTAHO_MIGRATION_CONFIG_DIR environment variable (used by tests).
"""

import os
from pathlib import Path

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]


class LLMSettings(BaseModel):
    provider: str = "ollama"          # ollama | anthropic | none
    base_url: str = "http://127.0.0.1:11434"
    model: str | None = None
    env: dict[str, str] = {}          # applied Ollama tuning, e.g. OLLAMA_FLASH_ATTENTION


def _settings_path() -> Path:
    config_dir = Path(os.environ.get("PENTAHO_MIGRATION_CONFIG_DIR", REPO_ROOT / "config"))
    return config_dir / "settings.json"


def load_settings() -> LLMSettings:
    path = _settings_path()
    if path.exists():
        return LLMSettings.model_validate_json(path.read_text(encoding="utf-8"))
    return LLMSettings()


def save_settings(settings: LLMSettings) -> Path:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    return path
