"""
Application configuration persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any

from src.core.models import JobPriority
from src.utils.paths import get_config_path


@dataclass
class AppConfig:
    download_dir: str = "~/Music/MiniDownloader"
    use_smart_folders: bool = True
    organize_by_source: bool = True
    organize_by_date: bool = False
    organize_by_format: bool = False
    date_folder_format: str = "%Y/%m"

    max_concurrent_downloads: int = 3
    concurrent_fragments: int = 4
    speed_limit_kbps: int = 0

    max_retries: int = 2
    retry_backoff_s: int = 5
    enable_resume: bool = True
    auto_retry: bool = True

    yt_cookies_file: str = ""
    yt_cookies_from_browser: str = ""

    clipboard_monitor: bool = False
    watch_folder_enabled: bool = False
    watch_folder_path: str = ""
    watch_poll_interval_s: int = 5

    schedule_enabled: bool = False
    schedule_time: str = ""

    notifications_enabled: bool = True
    tray_enabled: bool = False
    background_mode: bool = True

    default_priority: JobPriority = JobPriority.NORMAL
    ui_scale: float = 1.0
    high_contrast: bool = False
    appearance_mode: str = "dark"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["default_priority"] = self.default_priority.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        cfg = cls()
        for key, value in data.items():
            if not hasattr(cfg, key):
                continue
            if key == "default_priority":
                try:
                    value = JobPriority(value)
                except Exception:
                    value = JobPriority.NORMAL
            setattr(cfg, key, value)
        return cfg


def load_config() -> AppConfig:
    path = get_config_path()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig.from_dict(data)
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    path = get_config_path()
    path.write_text(json.dumps(cfg.to_dict(), indent=2), encoding="utf-8")
