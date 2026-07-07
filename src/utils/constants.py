"""
Constants and regex patterns for URL identification and platform detection.
"""

import re
from src.core.models import Platform

# ---------------------------------------------------------------------------
# URL regex patterns for each supported platform
# ---------------------------------------------------------------------------

PLATFORM_PATTERNS: dict[Platform, re.Pattern] = {
    Platform.SPOTIFY: re.compile(
        r"https?://(?:open\.)?spotify\.com/"
        r"(?:intl-[a-z]{2}/)?"
        r"(track|album|playlist)/([a-zA-Z0-9]+)",
        re.IGNORECASE,
    ),
    Platform.APPLE_MUSIC: re.compile(
        r"https?://music\.apple\.com/"
        r"([a-z]{2})/"
        r"(album|playlist|song)/"
        r"[^/]+/"
        r"(\d+)"
        r"(?:\?i=(\d+))?",
        re.IGNORECASE,
    ),
    Platform.TIDAL: re.compile(
        r"https?://(?:listen\.)?tidal\.com/"
        r"(?:browse/)?"
        r"(track|album|playlist)/(\d+|[a-f0-9-]+)",
        re.IGNORECASE,
    ),
    Platform.DEEZER: re.compile(
        r"https?://(?:www\.)?deezer\.com/"
        r"(?:[a-z]{2}/)?"
        r"(track|album|playlist)/(\d+)",
        re.IGNORECASE,
    ),
    Platform.AMAZON_MUSIC: re.compile(
        r"https?://music\.amazon\."
        r"(?:com|co\.\w+|de|fr|it|es)/"
        r"(albums|tracks|playlists)/"
        r"([A-Za-z0-9]+)",
        re.IGNORECASE,
    ),
    Platform.SOUNDCLOUD: re.compile(
        r"https?://(?:www\.|m\.)?soundcloud\.com/"
        r"([a-zA-Z0-9_-]+)/"
        r"(sets/)?"
        r"([a-zA-Z0-9_-]+)",
        re.IGNORECASE,
    ),
    Platform.YOUTUBE: re.compile(
        r"https?://(?:www\.|music\.)?(?:youtube\.com|youtu\.be)",
        re.IGNORECASE,
    ),
}

# ---------------------------------------------------------------------------
# Duration tolerance for search matching (in seconds)
# ---------------------------------------------------------------------------

DURATION_TOLERANCE_S = 5

# ---------------------------------------------------------------------------
# Default concurrent download workers
# ---------------------------------------------------------------------------

MAX_CONCURRENT_DOWNLOADS = 3

# ---------------------------------------------------------------------------
# File extension mappings
# ---------------------------------------------------------------------------

FORMAT_EXTENSIONS = {
    "flac": ".flac",
    "alac": ".m4a",
    "mp3": ".mp3",
}

# ---------------------------------------------------------------------------
# Utility: detect platform from URL
# ---------------------------------------------------------------------------


def detect_platform(url: str) -> tuple[Platform, re.Match | None]:
    """
    Identify which music platform a URL belongs to.

    Returns:
        Tuple of (Platform enum, regex Match object or None).
    """
    for platform, pattern in PLATFORM_PATTERNS.items():
        match = pattern.search(url)
        if match:
            return platform, match
    return Platform.UNKNOWN, None


def is_collection_url(url: str) -> bool:
    """
    Check if a URL points to a playlist or album (i.e., multiple tracks)
    rather than a single track.
    """
    platform, match = detect_platform(url)
    if match is None:
        return False

    # Group 1 in all patterns is the resource type (track/album/playlist)
    resource_type = match.group(1).lower()

    # Spotify, Tidal, Deezer: group(1) is "track", "album", or "playlist"
    if platform in (Platform.SPOTIFY, Platform.TIDAL, Platform.DEEZER):
        return resource_type in ("album", "playlist")

    # Apple Music: group(2) is "album", "playlist", or "song"
    if platform == Platform.APPLE_MUSIC:
        resource_type = match.group(2).lower()
        return resource_type in ("album", "playlist")

    # Amazon Music: group(1) is "albums", "tracks", or "playlists"
    if platform == Platform.AMAZON_MUSIC:
        return resource_type in ("albums", "playlists")

    # SoundCloud: group(2) is "sets/" if it's a playlist
    if platform == Platform.SOUNDCLOUD:
        return match.group(2) == "sets/"

    # YouTube: check if "list=" is present but not a single watch video (or just default to playlist if list= is present)
    if platform == Platform.YOUTUBE:
        return "list=" in url and "watch?v=" not in url

    return False

