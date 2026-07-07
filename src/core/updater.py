"""
Update checking logic for MiniDownloader.
Queries GitHub Releases API to check if a newer release is available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
import requests

from src.version import __version__

logger = logging.getLogger(__name__)

GITHUB_RELEASES_API = "https://api.github.com/repos/snaffey/MiniDownloader/releases/latest"


@dataclass
class UpdateInfo:
    available: bool
    latest_version: str
    release_notes: str
    url: str


def _parse_version(ver_str: str) -> tuple[int, ...]:
    """Parse a semver string like 'v1.2.3' or '1.2.3' into a comparable tuple of integers."""
    clean = ver_str.strip().lstrip("v")
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            # If there are prerelease tags like '-beta', strip non-digits
            digits = "".join(c for c in p if c.isdigit())
            parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_updates(current_version: Optional[str] = None, timeout: int = 5) -> UpdateInfo:
    """
    Check GitHub latest release against current version.
    Returns UpdateInfo indicating whether a newer version is available.
    """
    if current_version is None:
        current_version = __version__

    try:
        headers = {"User-Agent": f"MiniDownloader/{current_version}"}
        resp = requests.get(GITHUB_RELEASES_API, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("GitHub Releases API returned status code %s", resp.status_code)
            return UpdateInfo(
                available=False,
                latest_version=current_version,
                release_notes="",
                url="https://github.com/snaffey/MiniDownloader/releases",
            )

        data = resp.json()
        tag_name = data.get("tag_name", "")
        body = data.get("body", "")
        html_url = data.get("html_url", "https://github.com/snaffey/MiniDownloader/releases")

        if not tag_name:
            return UpdateInfo(
                available=False,
                latest_version=current_version,
                release_notes="",
                url=html_url,
            )

        latest_tuple = _parse_version(tag_name)
        current_tuple = _parse_version(current_version)

        # Pad tuples if lengths differ (e.g., 1.0 vs 1.0.1)
        max_len = max(len(latest_tuple), len(current_tuple))
        latest_tuple += (0,) * (max_len - len(latest_tuple))
        current_tuple += (0,) * (max_len - len(current_tuple))

        available = latest_tuple > current_tuple
        if available:
            logger.info("New update detected: %s (current: %s)", tag_name, current_version)

        return UpdateInfo(
            available=available,
            latest_version=tag_name,
            release_notes=body,
            url=html_url,
        )

    except requests.RequestException as e:
        logger.debug("Network error while checking for updates: %s", e)
        return UpdateInfo(
            available=False,
            latest_version=current_version,
            release_notes="",
            url="https://github.com/snaffey/MiniDownloader/releases",
        )
    except Exception as e:
        logger.error("Unexpected error checking for updates: %s", e)
        return UpdateInfo(
            available=False,
            latest_version=current_version,
            release_notes="",
            url="https://github.com/snaffey/MiniDownloader/releases",
        )
