"""
YouTube Music search and ranking engine.

Implements the "Metadata Mirroring" strategy:
1. Search YouTube Music for the track using ytmusicapi.
2. Filter results by duration tolerance.
3. Rank by audio bitrate (via yt-dlp metadata extraction).
4. Return the best matching result.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import yt_dlp
from ytmusicapi import YTMusic

from src.core.models import SearchResult, TrackInfo
from src.core.yt_dlp_config import apply_yt_dlp_cookies
from src.utils.constants import DURATION_TOLERANCE_S

logger = logging.getLogger(__name__)

_ytmusic: Optional[YTMusic] = None
_SEARCH_RESULT_LIMIT = 6
_BITRATE_PROBE_LIMIT = 0
_HIGH_CONFIDENCE_MATCH = 0.92

_NOISE_TOKENS = {
    "official",
    "audio",
    "video",
    "lyrics",
    "lyric",
    "hq",
    "hd",
    "explicit",
    "clean",
    "version",
    "remaster",
    "remastered",
    "mono",
    "stereo",
}

_PENALTY_TOKENS = {
    "karaoke",
    "cover",
    "live",
    "remix",
    "mix",
    "instrumental",
    "sped",
    "slowed",
    "nightcore",
    "8d",
    "edit",
    "tribute",
    "parody",
    "reverb",
    "acoustic",
    "piano",
    "demo",
    "extended",
    "loop",
}


def _get_ytmusic() -> YTMusic:
    global _ytmusic
    if _ytmusic is None:
        _ytmusic = YTMusic()
    return _ytmusic


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokenize(text: str, drop_noise: bool = True) -> set[str]:
    norm = _normalize_text(text)
    if not norm:
        return set()
    tokens = [t for t in norm.split(" ") if t]
    if drop_noise:
        tokens = [t for t in tokens if t not in _NOISE_TOKENS]
    return set(tokens)


def _text_similarity(a: str, b: str) -> float:
    a_tokens = _tokenize(a)
    b_tokens = _tokenize(b)
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return len(overlap) / len(union)


def _extract_artist_names(item: dict) -> str:
    artists = item.get("artists") or []
    names = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or ""
            if name:
                names.append(name)
    if not names and isinstance(item.get("artist"), str):
        names = [item.get("artist", "")]
    return " ".join(names).strip()


def _compute_penalty(track_title: str, candidate_title: str) -> float:
    track_tokens = _tokenize(track_title, drop_noise=False)
    candidate_tokens = _tokenize(candidate_title, drop_noise=False)
    if not candidate_tokens:
        return 0.0
    bad_hits = [t for t in _PENALTY_TOKENS if t in candidate_tokens and t not in track_tokens]
    return min(0.5, 0.1 * len(bad_hits))


def _compute_match_score(track: TrackInfo, item: dict) -> float:
    title = item.get("title", "") or ""
    artist = _extract_artist_names(item)

    title_score = _text_similarity(track.title, title)
    if track.artist:
        artist_score = _text_similarity(track.artist, artist)
        base = (title_score * 0.7) + (artist_score * 0.3)
    else:
        base = title_score

    bonus = 0.0
    track_title_norm = _normalize_text(track.title)
    title_norm = _normalize_text(title)
    if track_title_norm and track_title_norm in title_norm:
        bonus += 0.1
    if track.artist:
        track_artist_norm = _normalize_text(track.artist)
        artist_norm = _normalize_text(artist)
        if track_artist_norm and track_artist_norm in artist_norm:
            bonus += 0.05

    penalty = _compute_penalty(track.title, title)
    score = base + bonus - penalty
    return max(0.0, min(1.0, score))


def search_and_match(track: TrackInfo, max_results: int = _SEARCH_RESULT_LIMIT) -> Optional[SearchResult]:
    """Search YouTube Music for the best audio match for a given track. # ponytail: removed unrequested plugin abstraction (YAGNI)"""
    result = _search_with_query(track.search_query, track, max_results)
    if result:
        return result

    logger.info("Primary search failed, trying fallback: %s", track.fallback_query)
    result = _search_with_query(track.fallback_query, track, max_results)
    if result:
        return result

    logger.warning("No match found for: %s", track.display_name)
    return None


def _search_with_query(query: str, track: TrackInfo, max_results: int) -> Optional[SearchResult]:
    yt = _get_ytmusic()
    try:
        raw_results = yt.search(query, filter="songs", limit=max_results)
    except Exception as e:
        logger.error("YTMusic search failed for '%s': %s", query, e)
        return None

    if not raw_results:
        return None

    candidates: list[SearchResult] = []
    for item in raw_results:
        video_id = item.get("videoId")
        if not video_id:
            continue

        duration_s = _parse_duration(item)
        if track.duration_s is not None and duration_s is not None:
            if abs(duration_s - track.duration_s) > DURATION_TOLERANCE_S:
                continue

        match_score = _compute_match_score(track, item)
        candidates.append(SearchResult(
            video_id=video_id,
            title=item.get("title", ""),
            duration_s=duration_s or 0,
            url=f"https://www.youtube.com/watch?v={video_id}",
            match_score=match_score,
        ))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c.match_score, reverse=True)
    probe_limit = _BITRATE_PROBE_LIMIT
    if candidates and candidates[0].match_score >= _HIGH_CONFIDENCE_MATCH:
        probe_limit = 1

    for c in candidates[:probe_limit]:
        c.abr = _probe_bitrate(c.video_id)
        c.compute_score(track.duration_s, match_score=c.match_score)
    for c in candidates[probe_limit:]:
        c.compute_score(track.duration_s, match_score=c.match_score)

    candidates.sort(key=lambda c: c.score, reverse=True)
    best = candidates[0]
    logger.info(
        "Best match: '%s' (abr=%.0f, match=%.2f, score=%.1f)",
        best.title,
        best.abr,
        best.match_score,
        best.score,
    )
    return best


def _parse_duration(item: dict) -> Optional[float]:
    if "duration_seconds" in item and item["duration_seconds"]:
        try:
            return float(item["duration_seconds"])
        except (ValueError, TypeError):
            pass
    duration_str = item.get("duration", "")
    if duration_str and ":" in duration_str:
        parts = duration_str.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, TypeError):
            pass
    return None


def _probe_bitrate(video_id: str) -> float:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
    }
    ydl_opts = apply_yt_dlp_cookies(ydl_opts)
    try:
        # ponytail: let yt-dlp use configured cookies directly without retry boilerplate
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            abr = info.get("abr")
            if abr:
                return float(abr)
            formats = info.get("formats", [])
            audio_fmts = [f for f in formats if f.get("acodec") and f["acodec"] != "none" and f.get("vcodec", "none") == "none"]
            if audio_fmts:
                best = max(audio_fmts, key=lambda f: f.get("abr", 0) or 0)
                return float(best.get("abr", 128))
    except Exception as e:
        logger.debug("Bitrate probe failed for %s: %s", video_id, e)
    return 0.0

