"""
config.py — Configuration manager for MeetAssist.
Handles loading/saving config.json from ~/.meetassist/config.json.
"""

import json
import os
from pathlib import Path

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
    "overlay_opacity": 0.92,
    "overlay_font_size": 14,
    "overlay_width": 480,
    "overlay_height": 320,
    "overlay_x": 40,
    "overlay_y": 40,
    "model": "gpt-4o",
}


def ensure_app_dir() -> None:
    """Create ~/.meetassist if it doesn't exist."""
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load config from disk; fill in missing keys from defaults."""
    ensure_app_dir()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            # Fill in any missing keys from defaults
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except (json.JSONDecodeError, IOError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    """Persist config to disk."""
    ensure_app_dir()
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def is_first_run(cfg: dict) -> bool:
    """Returns True if the API key hasn't been set yet."""
    return not cfg.get("openai_api_key", "").strip()
