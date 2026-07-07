"""
Filesystem paths for MiniDownloader data and config.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "MiniDownloader"


def get_app_data_dir() -> Path:
    base = os.getenv("APPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"


def get_history_path() -> Path:
    return get_app_data_dir() / "history.json"


def get_queue_path() -> Path:
    return get_app_data_dir() / "queue.json"
