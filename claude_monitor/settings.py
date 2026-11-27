"""Settings persistence for Claude Token Monitor."""

import json
import os

CONFIG_DIR = os.path.expanduser("~/.config/claude-token-monitor")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "token_limit": 200_000,
    "alert_threshold": 80,
    "refresh_interval_ms": 10_000,
    "dark_mode": True,
    "always_on_top": False,
}


def load() -> dict:
    settings = dict(DEFAULTS)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                stored = json.load(f)
            settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except (OSError, json.JSONDecodeError):
        pass
    return settings


def save(settings: dict):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {k: settings[k] for k in DEFAULTS if k in settings}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass
