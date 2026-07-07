"""
yt-dlp configuration helpers.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.core.config import AppConfig, load_config

logger = logging.getLogger(__name__)


def apply_yt_dlp_cookies(ydl_opts: dict[str, Any], cfg: AppConfig | None = None) -> dict[str, Any]:
    """Apply cookie settings and anti-rate-limit delays to yt-dlp options.
    
    # ponytail: let yt-dlp natively handle cookie validation and browser databases without custom parsers or OS auto-detection.
    """
    cfg = cfg or load_config()

    # Add anti-rate-limit delays (to avoid YouTube's 429 Too Many Requests)
    ydl_opts.setdefault("sleep_interval_requests", 0.5)
    ydl_opts.setdefault("sleep_interval", 0.0)
    ydl_opts.setdefault("max_sleep_interval", 1.0)

    # Enable EJS challenge solver for YouTube signature decryption (requires deno)
    ydl_opts.setdefault("remote_components", {"ejs:github": True})

    # ponytail: default to robust YouTube player clients (android, ios, web, web_music) to prevent HTTP 403 Forbidden
    ydl_opts.setdefault("extractor_args", {"youtube": {"player_client": ["android", "ios", "web", "web_music"]}})

    cookies_file = (cfg.yt_cookies_file or "").strip()
    cookies_from_browser = (cfg.yt_cookies_from_browser or "").strip()

    if cookies_file:
        expanded = os.path.expanduser(os.path.expandvars(cookies_file))
        if os.path.exists(expanded):
            ydl_opts["cookiefile"] = expanded
        else:
            logger.warning("yt-dlp cookie file not found: %s", expanded)
    elif cookies_from_browser:
        parts = [p.strip() for p in cookies_from_browser.split(":") if p.strip()]
        if parts:
            ydl_opts["cookiesfrombrowser"] = tuple(parts)

    return ydl_opts

