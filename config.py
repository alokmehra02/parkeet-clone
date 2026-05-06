"""
config.py — Configuration manager for MeetAssist.

Priority order for values:
  1. Environment variables (from .env or shell export)
  2. ~/.meetassist/config.json
  3. Built-in defaults
"""

import json
import os
from pathlib import Path

# Load .env from the project directory (if python-dotenv is installed)
try:
    from dotenv import load_dotenv as _load_dotenv
    # Walk up from this file's dir to find .env
    _env_file = Path(__file__).resolve().parent / ".env"
    _load_dotenv(dotenv_path=_env_file, override=False)  # don't overwrite existing shell vars
except ImportError:
    pass  # python-dotenv is optional; .env file will be silently ignored

APP_DIR = Path.home() / ".meetassist"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "sessions.db"

DEFAULT_CONFIG = {
    "openai_api_key": "",
    "transcription_engine": "whisper-api",   # "whisper-api" | "faster-whisper"
    "hotkey_toggle": "ctrl+shift+h",
    "hotkey_ask": "ctrl+shift+a",
    "hotkey_clear": "ctrl+shift+c",
    "hotkey_quit": "ctrl+shift+q",
    "overlay_opacity": 0.75,
    "overlay_font_size": 14,
    "overlay_width": 480,
    "overlay_height": 340,
    "overlay_x": 40,
    "overlay_y": 40,
    "model": "gpt-4o",
}


def ensure_app_dir() -> None:
    """Create ~/.meetassist if it doesn't exist."""
    APP_DIR.mkdir(parents=True, exist_ok=True)


# Mapping from environment variable names → config dict keys
_ENV_MAP = {
    "OPENAI_API_KEY":           "openai_api_key",
    "MEETASSIST_MODEL":         "model",
    "MEETASSIST_ENGINE":        "transcription_engine",
    "MEETASSIST_OPACITY":       "overlay_opacity",
    "MEETASSIST_FONT_SIZE":     "overlay_font_size",
    "MEETASSIST_HOTKEY_TOGGLE": "hotkey_toggle",
    "MEETASSIST_HOTKEY_ASK":    "hotkey_ask",
    "MEETASSIST_HOTKEY_CLEAR":  "hotkey_clear",
    "MEETASSIST_HOTKEY_QUIT":   "hotkey_quit",
}


def _apply_env_overrides(cfg: dict) -> dict:
    """Overlay environment variable values on top of the loaded config dict."""
    for env_var, cfg_key in _ENV_MAP.items():
        val = os.environ.get(env_var)
        if val is not None:
            # Cast numeric fields
            if cfg_key in ("overlay_opacity",):
                try:
                    val = float(val)
                except ValueError:
                    pass
            elif cfg_key in ("overlay_font_size", "overlay_width", "overlay_height"):
                try:
                    val = int(val)
                except ValueError:
                    pass
            cfg[cfg_key] = val
    return cfg


def load_config() -> dict:
    """Load config from disk, then apply env-var overrides."""
    ensure_app_dir()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            # Fill in any missing keys from defaults
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return _apply_env_overrides(data)
        except (json.JSONDecodeError, IOError):
            pass
    return _apply_env_overrides(dict(DEFAULT_CONFIG))


def save_config(cfg: dict) -> None:
    """Persist config to disk."""
    ensure_app_dir()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def is_first_run(cfg: dict) -> bool:
    """Returns True if the API key hasn't been set yet."""
    return not cfg.get("openai_api_key", "").strip()
