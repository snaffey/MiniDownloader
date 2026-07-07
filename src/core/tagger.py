"""
Audio file tagger using mutagen.

Embeds metadata (title, artist, album) and high-res album art into
downloaded audio files. Supports MP3 (ID3), FLAC (VorbisComment), and
M4A/ALAC (MP4 tags).
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import requests
from PIL import Image

from src.core.models import TrackInfo

logger = logging.getLogger(__name__)

# Maximum album art dimension (will be resized if larger)
MAX_ART_SIZE = 800


def tag_file(file_path: str, track: TrackInfo) -> None:
    """
    Embed metadata and album art into a downloaded audio file.

    Automatically detects the file format from the extension and uses
    the appropriate tagging method.
    """
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""

    # Download album art
    art_data, art_mime = _download_artwork(track.thumbnail_url)

    try:
        if ext == "mp3":
            _tag_mp3(file_path, track, art_data, art_mime)
        elif ext == "flac":
            _tag_flac(file_path, track, art_data, art_mime)
        elif ext in ("m4a", "mp4", "alac"):
            _tag_m4a(file_path, track, art_data)
        else:
            logger.warning("Unknown format '%s', skipping tagging", ext)
            return

        logger.info("Tagged: %s", file_path)

    except Exception as e:
        logger.error("Tagging failed for '%s': %s", file_path, e)


def _tag_mp3(
    path: str, track: TrackInfo,
    art_data: Optional[bytes], art_mime: str,
) -> None:
    """Embed ID3 tags into an MP3 file."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error as ID3Error

    audio = MP3(path, ID3=ID3)
    try:
        audio.add_tags()
    except ID3Error:
        pass  # Tags already exist

    audio.tags.add(TIT2(encoding=3, text=track.title))
    audio.tags.add(TPE1(encoding=3, text=track.artist))
    if track.album:
        audio.tags.add(TALB(encoding=3, text=track.album))

    if art_data:
        audio.tags.add(APIC(
            encoding=3,
            mime=art_mime,
            type=3,  # Front cover
            desc="Cover",
            data=art_data,
        ))

    audio.save()


def _tag_flac(
    path: str, track: TrackInfo,
    art_data: Optional[bytes], art_mime: str,
) -> None:
    """Embed VorbisComment tags and a Picture into a FLAC file."""
    from mutagen.flac import FLAC, Picture

    audio = FLAC(path)
    audio["TITLE"] = track.title
    audio["ARTIST"] = track.artist
    if track.album:
        audio["ALBUM"] = track.album

    if art_data:
        pic = Picture()
        pic.type = 3  # Front cover
        pic.mime = art_mime
        pic.desc = "Cover"
        pic.data = art_data
        audio.clear_pictures()
        audio.add_picture(pic)

    audio.save()


def _tag_m4a(
    path: str, track: TrackInfo,
    art_data: Optional[bytes],
) -> None:
    """Embed MP4 tags into an M4A/ALAC file."""
    from mutagen.mp4 import MP4, MP4Cover

    audio = MP4(path)
    audio["\xa9nam"] = [track.title]
    audio["\xa9ART"] = [track.artist]
    if track.album:
        audio["\xa9alb"] = [track.album]

    if art_data:
        # Detect format for MP4Cover
        fmt = MP4Cover.FORMAT_JPEG
        if art_data[:4] == b"\x89PNG":
            fmt = MP4Cover.FORMAT_PNG
        audio["covr"] = [MP4Cover(art_data, imageformat=fmt)]

    audio.save()


def _download_artwork(url: Optional[str]) -> tuple[Optional[bytes], str]:
    """
    Download and resize album artwork.

    Returns:
        Tuple of (image_bytes, mime_type) or (None, "") if unavailable.
    """
    if not url:
        return None, ""

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.content

        # Detect MIME type
        mime = resp.headers.get("Content-Type", "image/jpeg")
        if "png" in mime:
            mime = "image/png"
        else:
            mime = "image/jpeg"

        # Resize if too large
        img = Image.open(io.BytesIO(data))
        if max(img.size) > MAX_ART_SIZE:
            img.thumbnail((MAX_ART_SIZE, MAX_ART_SIZE), Image.LANCZOS)
            buf = io.BytesIO()
            img_format = "PNG" if mime == "image/png" else "JPEG"
            img.save(buf, format=img_format, quality=95)
            data = buf.getvalue()

        return data, mime

    except Exception as e:
        logger.warning("Failed to download artwork from %s: %s", url, e)
        return None, ""
