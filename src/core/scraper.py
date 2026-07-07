"""
Metadata scraper for multiple music platforms.

Extracts track metadata (title, artist, album, duration, artwork) from URLs
without requiring any API keys or user authentication.

Supported platforms:
- Spotify (via oEmbed API)
- Apple Music (via HTML meta tags)
- Tidal (via HTML meta tags)
- Deezer (via public API)
- Amazon Music (via HTML meta tags)
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from src.core.models import Platform, TrackInfo
from src.core.yt_dlp_config import apply_yt_dlp_cookies
from src.utils.constants import detect_platform

logger = logging.getLogger(__name__)

# Shared session for connection pooling
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
})

REQUEST_TIMEOUT = 15


def scrape_metadata(url: str) -> TrackInfo:
    """
    Extract track metadata from a music platform URL.

    Routes to the appropriate platform-specific scraper based on URL pattern.

    Args:
        url: A track URL from any supported platform.

    Returns:
        TrackInfo with as much metadata as could be extracted.

    Raises:
        ValueError: If the URL is not from a supported platform.
        ConnectionError: If the HTTP request fails.
    """
    # ponytail: removed unrequested plugin abstraction (YAGNI), using built-in scrapers directly
    platform, match = detect_platform(url)

    scrapers = {
        Platform.SPOTIFY: _scrape_spotify,
        Platform.APPLE_MUSIC: _scrape_apple_music,
        Platform.TIDAL: _scrape_tidal,
        Platform.DEEZER: _scrape_deezer,
        Platform.AMAZON_MUSIC: _scrape_amazon_music,
        Platform.SOUNDCLOUD: _scrape_soundcloud,
        Platform.YOUTUBE: _scrape_youtube,
    }

    scraper_func = scrapers.get(platform)
    if scraper_func is None:
        raise ValueError(
            f"Unsupported or unrecognized URL: {url}\n"
            f"Supported platforms: Spotify, Apple Music, Tidal, Deezer, Amazon Music"
        )

    track = scraper_func(url, match)
    track.source_url = url
    track.source_platform = platform

    logger.info("Scraped metadata: %s", track.display_name)
    return track


def scrape_playlist(url: str) -> list[TrackInfo]:
    """
    Extract metadata for every track in a playlist or album URL.

    Routes to the appropriate platform-specific playlist scraper.

    Args:
        url: A playlist or album URL from any supported platform.

    Returns:
        List of TrackInfo, one per track in the collection.

    Raises:
        ValueError: If the URL is not from a supported platform.
        ConnectionError: If the HTTP request fails.
    """
    # ponytail: removed unrequested plugin abstraction (YAGNI), using built-in scrapers directly
    platform, match = detect_platform(url)

    playlist_scrapers = {
        Platform.SPOTIFY: _scrape_spotify_collection,
        Platform.DEEZER: _scrape_deezer_collection,
        Platform.APPLE_MUSIC: _scrape_generic_collection,
        Platform.TIDAL: _scrape_generic_collection,
        Platform.AMAZON_MUSIC: _scrape_generic_collection,
        Platform.SOUNDCLOUD: _scrape_soundcloud_collection,
        Platform.YOUTUBE: _scrape_youtube_collection,
    }

    scraper_func = playlist_scrapers.get(platform)
    if scraper_func is None:
        raise ValueError(f"Unsupported platform for playlist: {url}")

    tracks = scraper_func(url, match, platform)

    # Tag each track with source info
    for track in tracks:
        track.source_platform = platform

    logger.info("Scraped playlist: %d tracks from %s", len(tracks), url)
    return tracks


# ---------------------------------------------------------------------------
# Platform-specific scrapers
# ---------------------------------------------------------------------------


def _scrape_spotify(url: str, match: re.Match | None) -> TrackInfo:
    """
    Scrape Spotify track metadata using HTML Open Graph meta tags.

    Spotify serves SSR pages with rich OG tags to non-browser user agents.
    The key data sources are:
    - og:title → Track name
    - og:description → "Artist · Album · Song · Year"
    - music:duration → Duration in seconds
    - og:image → High-res album art (640×640)
    - <title> → "Track Name - song and lyrics by Artist | Spotify"

    Falls back to the oEmbed API if HTML scraping fails.
    """
    # Use a simple user agent — Spotify serves SSR pages with OG tags
    # to non-browser UAs, but serves the SPA shell to Chrome-like UAs
    headers = {"User-Agent": "python-requests/2.31.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        og_title = _get_meta(soup, "og:title") or ""
        og_image = _get_meta(soup, "og:image") or ""
        og_desc = _get_meta(soup, "og:description") or ""

        # Duration in seconds from music:duration meta tag
        duration_s = None
        duration_raw = _get_meta(soup, "music:duration")
        if duration_raw:
            try:
                duration_s = float(duration_raw)
            except (ValueError, TypeError):
                pass

        # Parse og:description: "Rick Astley · Whenever You Need Somebody · Song · 1987"
        # Format is: "Artist · Album · Type · Year"
        artist = ""
        album = ""
        if "·" in og_desc:
            parts = [p.strip() for p in og_desc.split("·")]
            if len(parts) >= 1:
                artist = parts[0]
            if len(parts) >= 2:
                album = parts[1]

        # If og:description didn't have artist, try <title> tag
        # Format: "Track Name - song and lyrics by Artist | Spotify"
        if not artist:
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                title_str = title_tag.string
                by_match = re.search(r"by\s+(.+?)\s*\|", title_str)
                if by_match:
                    artist = by_match.group(1).strip()

        title = og_title if og_title else ""

        if title:
            return TrackInfo(
                title=title,
                artist=artist,
                album=album,
                duration_s=duration_s,
                thumbnail_url=og_image,
            )

    except requests.RequestException:
        logger.debug("HTML scrape failed for Spotify, trying oEmbed")

    # Fallback: oEmbed API
    return _scrape_spotify_oembed(url)


def _scrape_spotify_oembed(url: str) -> TrackInfo:
    """Fallback Spotify scraper using the public oEmbed endpoint."""
    oembed_url = f"https://open.spotify.com/oembed?url={quote(url, safe='')}"

    try:
        resp = _session.get(oembed_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to reach Spotify oEmbed API: {e}") from e

    raw_title = data.get("title", "")
    thumbnail = data.get("thumbnail_url", "")

    # Try to parse "Artist - Title" or just use the title as-is
    artist = ""
    title = raw_title
    if " - " in raw_title:
        parts = raw_title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    return TrackInfo(
        title=title,
        artist=artist,
        thumbnail_url=thumbnail,
    )


def _scrape_apple_music(url: str, match: re.Match | None) -> TrackInfo:
    """
    Scrape Apple Music track metadata from Open Graph meta tags.

    Apple Music pages include structured OG tags with title, description,
    and artwork URLs.
    """
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch Apple Music page: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    og_title = _get_meta(soup, "og:title") or ""
    og_desc = _get_meta(soup, "og:description") or ""
    og_image = _get_meta(soup, "og:image") or ""

    # OG title is usually "Song Name - Single" or "Song Name"
    title = og_title.replace(" - Single", "").replace(" - EP", "").strip()

    # Description often contains "Song · Artist · Album · Year"
    artist = ""
    album = ""
    duration_s = None

    if "·" in og_desc:
        parts = [p.strip() for p in og_desc.split("·")]
        if len(parts) >= 2:
            # Typically: "Song · Artist" or "Song · Artist · Album"
            artist = parts[1] if len(parts) > 1 else ""
            album = parts[2] if len(parts) > 2 else ""

    # Try to parse duration from page content
    duration_meta = _get_meta(soup, "music:duration")
    if duration_meta:
        try:
            duration_s = float(duration_meta)
        except (ValueError, TypeError):
            pass

    return TrackInfo(
        title=title,
        artist=artist,
        album=album,
        duration_s=duration_s,
        thumbnail_url=og_image,
    )


def _scrape_tidal(url: str, match: re.Match | None) -> TrackInfo:
    """
    Scrape Tidal track metadata from Open Graph meta tags.
    """
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch Tidal page: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    og_title = _get_meta(soup, "og:title") or ""
    og_desc = _get_meta(soup, "og:description") or ""
    og_image = _get_meta(soup, "og:image") or ""

    # Tidal OG title is often "Track Name by Artist"
    artist = ""
    title = og_title

    if " by " in og_title.lower():
        idx = og_title.lower().index(" by ")
        title = og_title[:idx].strip()
        artist = og_title[idx + 4:].strip()
    elif " - " in og_title:
        parts = og_title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    album = ""
    if og_desc:
        # Description sometimes references the album
        album_match = re.search(r"on\s+(?:the\s+)?album\s+(.+?)(?:\.|$)", og_desc, re.IGNORECASE)
        if album_match:
            album = album_match.group(1).strip()

    return TrackInfo(
        title=title,
        artist=artist,
        album=album,
        thumbnail_url=og_image,
    )


def _scrape_deezer(url: str, match: re.Match | None) -> TrackInfo:
    """
    Scrape Deezer track metadata via the public API.

    Deezer's public API (`api.deezer.com`) does not require authentication
    for basic track lookups.
    """
    if match is None:
        raise ValueError(f"Could not parse Deezer URL: {url}")

    resource_type = match.group(1)  # "track", "album", "playlist"
    resource_id = match.group(2)

    if resource_type != "track":
        # For albums/playlists, fall back to HTML scraping
        return _scrape_deezer_html(url)

    api_url = f"https://api.deezer.com/track/{resource_id}"

    try:
        resp = _session.get(api_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to reach Deezer API: {e}") from e

    if "error" in data:
        raise ValueError(f"Deezer API error: {data['error'].get('message', 'Unknown')}")

    return TrackInfo(
        title=data.get("title", ""),
        artist=data.get("artist", {}).get("name", ""),
        album=data.get("album", {}).get("title", ""),
        duration_s=data.get("duration"),
        thumbnail_url=data.get("album", {}).get("cover_xl")
        or data.get("album", {}).get("cover_big", ""),
    )


def _scrape_deezer_html(url: str) -> TrackInfo:
    """Fallback HTML scraper for Deezer albums/playlists."""
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch Deezer page: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")
    og_title = _get_meta(soup, "og:title") or ""
    og_image = _get_meta(soup, "og:image") or ""

    return TrackInfo(
        title=og_title,
        artist="",
        thumbnail_url=og_image,
    )


def _scrape_amazon_music(url: str, match: re.Match | None) -> TrackInfo:
    """
    Scrape Amazon Music track metadata from Open Graph meta tags.
    """
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch Amazon Music page: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    og_title = _get_meta(soup, "og:title") or ""
    og_desc = _get_meta(soup, "og:description") or ""
    og_image = _get_meta(soup, "og:image") or ""

    # Amazon Music titles can be "Song Name by Artist on Amazon Music"
    title = og_title
    artist = ""

    if " by " in og_title.lower():
        idx = og_title.lower().index(" by ")
        title = og_title[:idx].strip()
        remainder = og_title[idx + 4:]
        # Remove trailing " on Amazon Music" etc.
        artist = re.sub(r"\s+on\s+Amazon\s+Music.*$", "", remainder, flags=re.IGNORECASE).strip()

    return TrackInfo(
        title=title,
        artist=artist,
        thumbnail_url=og_image,
    )


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------


def _get_meta(soup: BeautifulSoup, property_name: str) -> Optional[str]:
    """Extract the content attribute from a <meta> tag by property or name."""
    tag = soup.find("meta", attrs={"property": property_name})
    if tag and tag.get("content"):
        return tag["content"]
    tag = soup.find("meta", attrs={"name": property_name})
    if tag and tag.get("content"):
        return tag["content"]
    return None


# ---------------------------------------------------------------------------
# Collection scrapers (playlists & albums)
# ---------------------------------------------------------------------------


def _find_value_in_dict(data, target_key: str):
    """
    Recursively search a nested dict/list for a key and return its value.
    Used to find the accessToken in the Spotify embed page JSON regardless
    of the exact nesting structure.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == target_key and isinstance(value, str) and value:
                return value
            result = _find_value_in_dict(value, target_key)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_value_in_dict(item, target_key)
            if result:
                return result
    return None


def _scrape_spotify_collection(
    url: str, match: re.Match | None, platform: Platform,
) -> list[TrackInfo]:
    """
    Scrape all tracks from a Spotify playlist or album.

    Uses a multi-tier approach to handle playlists of any size:

    Tier 1: Try the public Spotify API with an access token extracted from
            the embed page. This gives full metadata with pagination.
    Tier 2: Use the Spotify internal playlist API (spclient) to get ALL
            track URIs, then resolve metadata for each via the embed page
            data and individual track scraping.
    Tier 3: Fall back to embed-page-only tracks (~50) if all else fails.
    """
    import json as _json

    if match is None:
        raise ValueError(f"Could not parse Spotify collection URL: {url}")

    resource_type = match.group(1)  # "album" or "playlist"
    resource_id = match.group(2)

    # --- Step 1: Fetch embed page (always needed for token + initial tracks) ---
    embed_url = f"https://open.spotify.com/embed/{resource_type}/{resource_id}"

    try:
        resp = requests.get(
            embed_url,
            headers={"User-Agent": "python-requests/2.31.0"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch Spotify embed page: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    json_script = soup.find("script", {"type": "application/json"})
    if not json_script or not json_script.string:
        raise ValueError("Could not find track data in Spotify embed page")

    try:
        embed_data = _json.loads(json_script.string)
    except _json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Spotify embed JSON: {e}") from e

    # Parse embed tracks (up to ~50)
    entity = (embed_data.get("props", {}).get("pageProps", {}).get("state", {})
              .get("data", {}).get("entity", {}))
    track_list = entity.get("trackList", [])

    collection_name = entity.get("name", "")
    cover_art = ""
    cover_sources = entity.get("coverArt", {}).get("sources", [])
    if cover_sources:
        cover_art = cover_sources[0].get("url", "")

    embed_tracks = _parse_spotify_embed_tracks(
        track_list, collection_name, cover_art, resource_type,
    )

    # Extract access token from embed JSON
    access_token = _find_value_in_dict(embed_data, "accessToken")

    # --- Step 2 (Tier 1): Try the public Spotify API with pagination ---
    if access_token:
        try:
            api_tracks = _scrape_spotify_collection_api(
                resource_type, resource_id, access_token,
                collection_name, cover_art,
            )
            if api_tracks and len(api_tracks) >= len(embed_tracks):
                logger.info(
                    "Spotify API: fetched all %d tracks for %s/%s",
                    len(api_tracks), resource_type, resource_id,
                )
                return api_tracks
        except Exception as e:
            logger.debug("Spotify public API failed (may be rate-limited): %s", e)

    # --- Step 3 (Tier 2): Use spclient to get ALL track IDs, then resolve ---
    if access_token and resource_type == "playlist":
        try:
            spclient_tracks = _scrape_spotify_via_spclient(
                resource_id, access_token, embed_tracks,
                collection_name, cover_art,
            )
            if spclient_tracks and len(spclient_tracks) >= len(embed_tracks):
                logger.info(
                    "Spotify spclient: fetched all %d tracks for playlist/%s",
                    len(spclient_tracks), resource_id,
                )
                return spclient_tracks
        except Exception as e:
            logger.debug("Spotify spclient approach failed: %s", e)

    # --- Step 4 (Tier 3): Return embed tracks ---
    if not embed_tracks:
        raise ValueError(f"No tracks found in Spotify {resource_type}: {url}")

    if len(embed_tracks) >= 45:
        logger.warning(
            "Spotify: only %d tracks retrieved from embed page "
            "(playlist may have more — embed is limited to ~50 tracks)",
            len(embed_tracks),
        )

    return embed_tracks


def _scrape_spotify_via_spclient(
    playlist_id: str, token: str, embed_tracks: list[TrackInfo],
    collection_name: str, cover_art: str,
) -> list[TrackInfo]:
    """
    Use Spotify's internal spclient API to get ALL track URIs for a playlist,
    then resolve metadata for tracks not already in embed_tracks.

    The spclient playlist endpoint returns the full track list (all URIs)
    without pagination limits. Metadata is then resolved by scraping
    individual track HTML pages in parallel.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    # Fetch full playlist contents from spclient
    spclient_url = (
        f"https://spclient.wg.spotify.com/playlist/v2/playlist/{playlist_id}"
    )
    resp = requests.get(spclient_url, headers=hdrs, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    contents = data.get("contents", {})
    items = contents.get("items", [])

    if not items:
        return []

    # Extract all track IDs
    all_track_ids: list[str] = []
    for item in items:
        uri = item.get("uri", "")
        if uri.startswith("spotify:track:"):
            all_track_ids.append(uri.split(":")[-1])

    if not all_track_ids:
        return []

    logger.info(
        "Spotify spclient: found %d track IDs (embed had %d)",
        len(all_track_ids), len(embed_tracks),
    )

    # Build a lookup from track ID → TrackInfo from embed data
    embed_by_id: dict[str, TrackInfo] = {}
    for t in embed_tracks:
        if t.source_url:
            tid = t.source_url.rsplit("/", 1)[-1]
            if tid:
                embed_by_id[tid] = t

    # Identify which track IDs need metadata resolution
    missing_ids = [tid for tid in all_track_ids if tid not in embed_by_id]

    logger.info(
        "Spotify: %d tracks already have metadata, %d need scraping",
        len(embed_by_id), len(missing_ids),
    )

    # Scrape missing tracks in parallel via individual HTML pages
    resolved: dict[str, TrackInfo] = {}
    if missing_ids:
        def _scrape_single_track(track_id: str) -> tuple[str, TrackInfo | None]:
            """Scrape metadata for a single Spotify track via HTML page."""
            track_url = f"https://open.spotify.com/track/{track_id}"
            try:
                r = requests.get(
                    track_url,
                    headers={"User-Agent": "python-requests/2.31.0"},
                    timeout=REQUEST_TIMEOUT,
                )
                r.raise_for_status()
                s = BeautifulSoup(r.text, "html.parser")

                og_title = _get_meta(s, "og:title") or ""
                og_desc = _get_meta(s, "og:description") or ""
                og_image = _get_meta(s, "og:image") or ""

                # Parse duration
                duration_s = None
                dur_raw = _get_meta(s, "music:duration")
                if dur_raw:
                    try:
                        duration_s = float(dur_raw)
                    except (ValueError, TypeError):
                        pass

                # Parse artist/album from og:description
                # Format: "Artist · Album · Song · Year"
                artist = ""
                album = ""
                if "·" in og_desc:
                    parts = [p.strip() for p in og_desc.split("·")]
                    if len(parts) >= 1:
                        artist = parts[0]
                    if len(parts) >= 2:
                        album = parts[1]

                if og_title:
                    return track_id, TrackInfo(
                        title=og_title,
                        artist=artist,
                        album=album,
                        duration_s=duration_s,
                        thumbnail_url=og_image or cover_art,
                        source_url=track_url,
                    )
            except Exception as e:
                logger.debug("Failed to scrape track %s: %s", track_id, e)

            return track_id, None

        # Use thread pool for parallel scraping (limit concurrency)
        max_workers = min(8, len(missing_ids))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_scrape_single_track, tid): tid
                for tid in missing_ids
            }
            for future in as_completed(futures):
                tid, track_info = future.result()
                if track_info:
                    resolved[tid] = track_info

        logger.info(
            "Spotify: resolved metadata for %d/%d missing tracks",
            len(resolved), len(missing_ids),
        )

    # Assemble the final track list in playlist order
    final_tracks: list[TrackInfo] = []
    for tid in all_track_ids:
        if tid in embed_by_id:
            final_tracks.append(embed_by_id[tid])
        elif tid in resolved:
            final_tracks.append(resolved[tid])
        else:
            # Track couldn't be resolved — include with minimal info
            final_tracks.append(TrackInfo(
                title=f"Track {tid}",
                artist="",
                source_url=f"https://open.spotify.com/track/{tid}",
                thumbnail_url=cover_art,
            ))

    return final_tracks


def _parse_spotify_embed_tracks(
    track_list: list, collection_name: str, cover_art: str, resource_type: str,
) -> list[TrackInfo]:
    """Parse track entries from the Spotify embed page JSON."""
    tracks: list[TrackInfo] = []
    for item in track_list:
        title = item.get("title", "")
        artist = item.get("subtitle", "")
        duration_ms = item.get("duration", 0)
        duration_s = duration_ms / 1000.0 if duration_ms else None

        uri = item.get("uri", "")
        track_url = ""
        if uri.startswith("spotify:track:"):
            track_id = uri.split(":")[-1]
            track_url = f"https://open.spotify.com/track/{track_id}"

        if title:
            tracks.append(TrackInfo(
                title=title,
                artist=artist,
                album=collection_name if resource_type == "album" else "",
                duration_s=duration_s,
                thumbnail_url=cover_art,
                source_url=track_url,
            ))
    return tracks


def _scrape_spotify_collection_api(
    resource_type: str, resource_id: str, token: str,
    collection_name: str = "", cover_art: str = "",
) -> list[TrackInfo]:
    """
    Fetch all tracks from a Spotify playlist or album using the Web API
    with pagination. No 100-track limit.
    """
    api_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    # If we don't have collection metadata yet, fetch it
    if not collection_name:
        meta_url = f"https://api.spotify.com/v1/{resource_type}s/{resource_id}"
        try:
            meta_resp = requests.get(meta_url, headers=api_headers, timeout=REQUEST_TIMEOUT)
            meta_resp.raise_for_status()
            meta_data = meta_resp.json()
            collection_name = meta_data.get("name", "")
            images = meta_data.get("images", [])
            if images and not cover_art:
                cover_art = images[0].get("url", "")
        except requests.RequestException as e:
            logger.debug("Could not fetch collection metadata: %s", e)

    # Paginate through all tracks
    tracks: list[TrackInfo] = []
    limit = 100  # Maximum allowed by the Spotify API per request
    offset = 0

    if resource_type == "playlist":
        tracks_url = f"https://api.spotify.com/v1/playlists/{resource_id}/tracks"
    else:  # album
        tracks_url = f"https://api.spotify.com/v1/albums/{resource_id}/tracks"

    while True:
        paginated_url = f"{tracks_url}?limit={limit}&offset={offset}"
        try:
            resp = requests.get(paginated_url, headers=api_headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                raise ConnectionError("Spotify API rate limited")
            resp.raise_for_status()
            page_data = resp.json()
        except requests.RequestException as e:
            logger.warning("Spotify API pagination failed at offset %d: %s", offset, e)
            raise

        items = page_data.get("items", [])
        if not items:
            break

        for item in items:
            # Playlist items have a "track" wrapper; album items are direct
            track_data = item.get("track", item) if resource_type == "playlist" else item

            if not track_data or not track_data.get("name"):
                continue

            title = track_data.get("name", "")
            artists = track_data.get("artists", [])
            artist = ", ".join(a.get("name", "") for a in artists) if artists else ""

            duration_ms = track_data.get("duration_ms", 0)
            duration_s = duration_ms / 1000.0 if duration_ms else None

            # Album name
            album = ""
            if resource_type == "album":
                album = collection_name
            else:
                album_data = track_data.get("album", {})
                album = album_data.get("name", "")

            # Track artwork
            track_art = cover_art
            if resource_type == "playlist":
                album_images = track_data.get("album", {}).get("images", [])
                if album_images:
                    track_art = album_images[0].get("url", "") or cover_art

            track_id = track_data.get("id", "")
            track_url = f"https://open.spotify.com/track/{track_id}" if track_id else ""

            tracks.append(TrackInfo(
                title=title,
                artist=artist,
                album=album,
                duration_s=duration_s,
                thumbnail_url=track_art,
                source_url=track_url,
            ))

        # Check if there are more pages
        total = page_data.get("total", 0)
        offset += limit
        if offset >= total:
            break

    if not tracks:
        raise ValueError(f"No tracks found via Spotify API for {resource_type}/{resource_id}")

    return tracks


def _scrape_deezer_collection(
    url: str, match: re.Match | None, platform: Platform,
) -> list[TrackInfo]:
    """
    Scrape all tracks from a Deezer playlist or album via the public API.

    The Deezer public API paginates track results (typically 25 per page).
    This implementation follows the 'next' URL to fetch ALL tracks.
    """
    if match is None:
        raise ValueError(f"Could not parse Deezer URL: {url}")

    resource_type = match.group(1)  # "album" or "playlist"
    resource_id = match.group(2)

    api_url = f"https://api.deezer.com/{resource_type}/{resource_id}"

    try:
        resp = _session.get(api_url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to reach Deezer API: {e}") from e

    if "error" in data:
        raise ValueError(f"Deezer API error: {data['error'].get('message', 'Unknown')}")

    # Get collection-level artwork
    collection_art = (
        data.get("cover_xl")
        or data.get("cover_big")
        or data.get("picture_xl")
        or data.get("picture_big", "")
    )
    collection_name = data.get("title", "")

    # Extract first page of tracks
    tracks_section = data.get("tracks", {})
    raw_tracks = tracks_section.get("data", [])

    if not raw_tracks:
        raise ValueError(f"No tracks found in Deezer {resource_type}: {url}")

    # Follow pagination to get ALL tracks
    all_raw_tracks = list(raw_tracks)
    next_url = tracks_section.get("next")

    while next_url:
        try:
            next_resp = _session.get(next_url, timeout=REQUEST_TIMEOUT)
            next_resp.raise_for_status()
            next_data = next_resp.json()
        except requests.RequestException as e:
            logger.warning("Deezer pagination failed at %s: %s", next_url, e)
            break

        page_tracks = next_data.get("data", [])
        if not page_tracks:
            break

        all_raw_tracks.extend(page_tracks)
        next_url = next_data.get("next")

    tracks: list[TrackInfo] = []
    for t in all_raw_tracks:
        track_art = t.get("album", {}).get("cover_xl") or t.get("album", {}).get("cover_big") or collection_art
        tracks.append(TrackInfo(
            title=t.get("title", ""),
            artist=t.get("artist", {}).get("name", ""),
            album=t.get("album", {}).get("title", "") or collection_name,
            duration_s=t.get("duration"),
            thumbnail_url=track_art,
            source_url=t.get("link", ""),
        ))

    logger.info("Deezer collection: fetched %d tracks (across %d API pages)",
                len(tracks), 1 + len(all_raw_tracks) // 25)
    return tracks


def _scrape_generic_collection(
    url: str, match: re.Match | None, platform: Platform,
) -> list[TrackInfo]:
    """
    Generic collection scraper for platforms without a dedicated API.

    Scrapes the HTML page for track links (music:song meta tags or anchor
    tags), then scrapes each individual track page for metadata.
    """
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to fetch page: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    # Try to find individual track URLs from music:song meta tags
    track_urls: list[str] = []
    song_tags = soup.find_all("meta", attrs={"property": "music:song"})
    for tag in song_tags:
        content = tag.get("content", "")
        if content and ("track" in content or "song" in content):
            track_urls.append(content)

    # Fallback: look for links that look like track URLs
    if not track_urls:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Check if the link is a track URL on the same platform
            detected_platform, _ = detect_platform(href)
            if detected_platform == platform:
                # Make sure it's a track, not another collection
                from src.utils.constants import is_collection_url
                if not is_collection_url(href):
                    if href not in track_urls:
                        track_urls.append(href)

    if not track_urls:
        # Last resort: try to scrape the page as a single track
        logger.warning("No individual tracks found in collection, treating as single track")
        track = scrape_metadata(url)
        return [track]

    # Scrape each track URL individually
    tracks: list[TrackInfo] = []
    for track_url in track_urls:
        try:
            track = scrape_metadata(track_url)
            tracks.append(track)
        except Exception as e:
            logger.warning("Failed to scrape track %s: %s", track_url, e)

    return tracks

# ---------------------------------------------------------------------------
# SoundCloud Scrapers
# ---------------------------------------------------------------------------

def _scrape_soundcloud(url: str, match: re.Match) -> TrackInfo:
    """Extract metadata for a SoundCloud track using yt-dlp."""
    import yt_dlp
    ydl_opts = {'quiet': True, 'extract_flat': False}
    ydl_opts = apply_yt_dlp_cookies(ydl_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return TrackInfo(
                title=info.get('title', 'Unknown Title'),
                artist=info.get('uploader', 'Unknown Artist'),
                duration_s=info.get('duration'),
                thumbnail_url=info.get('thumbnail'),
                source_url=url,
                source_platform=Platform.SOUNDCLOUD,
            )
    except Exception as e:
        logger.error("SoundCloud scraping failed: %s", e)
        raise ValueError(f"Could not extract SoundCloud metadata: {e}") from e

def _scrape_soundcloud_collection(url: str, match: re.Match, platform: Platform) -> list[TrackInfo]:
    """Extract metadata for all tracks in a SoundCloud playlist using yt-dlp."""
    import yt_dlp
    ydl_opts = {'quiet': True, 'extract_flat': 'in_playlist'}
    ydl_opts = apply_yt_dlp_cookies(ydl_opts)
    tracks = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' not in info:
                raise ValueError("No tracks found in SoundCloud playlist")
            for entry in info['entries']:
                if entry:
                    tracks.append(TrackInfo(
                        title=entry.get('title', 'Unknown Title'),
                        artist=entry.get('uploader', 'Unknown Artist'),
                        duration_s=entry.get('duration'),
                        thumbnail_url=entry.get('thumbnail'),
                        source_url=entry.get('url') or entry.get('webpage_url') or "",
                        source_platform=Platform.SOUNDCLOUD,
                    ))
        return tracks
    except Exception as e:
        logger.error("SoundCloud playlist scraping failed: %s", e)
        raise ValueError(f"Could not extract SoundCloud playlist metadata: {e}") from e


# ---------------------------------------------------------------------------
# YouTube Scrapers
# ---------------------------------------------------------------------------

def _scrape_youtube(url: str, match: re.Match) -> TrackInfo:
    """Extract metadata for a YouTube video/track using yt-dlp."""
    import yt_dlp
    ydl_opts = {'quiet': True, 'extract_flat': False}
    ydl_opts = apply_yt_dlp_cookies(ydl_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return TrackInfo(
                title=info.get('title', 'Unknown Title'),
                artist=info.get('uploader') or info.get('channel', 'Unknown Artist'),
                duration_s=info.get('duration'),
                thumbnail_url=info.get('thumbnail'),
                source_url=url,
                source_platform=Platform.YOUTUBE,
            )
    except Exception as e:
        logger.error("YouTube scraping failed: %s", e)
        raise ValueError(f"Could not extract YouTube metadata: {e}") from e

def _scrape_youtube_collection(url: str, match: re.Match, platform: Platform) -> list[TrackInfo]:
    """Extract metadata for all tracks in a YouTube playlist using yt-dlp."""
    import yt_dlp
    ydl_opts = {'quiet': True, 'extract_flat': 'in_playlist'}
    ydl_opts = apply_yt_dlp_cookies(ydl_opts)
    tracks = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' not in info:
                raise ValueError("No tracks found in YouTube playlist")
            for entry in info['entries']:
                if entry:
                    tracks.append(TrackInfo(
                        title=entry.get('title', 'Unknown Title'),
                        artist=entry.get('uploader') or entry.get('channel', 'Unknown Artist'),
                        duration_s=entry.get('duration'),
                        thumbnail_url=entry.get('thumbnail'),
                        source_url=entry.get('url') or entry.get('webpage_url') or "",
                        source_platform=Platform.YOUTUBE,
                    ))
        return tracks
    except Exception as e:
        logger.error("YouTube playlist scraping failed: %s", e)
        raise ValueError(f"Could not extract YouTube playlist metadata: {e}") from e

