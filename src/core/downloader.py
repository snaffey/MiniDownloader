"""
Audio downloader and transcoder.

Phase 1: Download best audio via yt-dlp from YouTube Music.
Phase 2: Transcode to the user's preferred format via ffmpeg (invoked through yt-dlp postprocessors).
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
import uuid
from typing import Callable, Optional

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from src.core.controls import DownloadControl
from src.core.models import DownloadJob, DownloadProgress, JobStatus, OutputFormat
from src.core.yt_dlp_config import apply_yt_dlp_cookies
from src.utils.sanitizer import sanitize_filename
from src.utils.constants import FORMAT_EXTENSIONS

logger = logging.getLogger(__name__)


class DownloadCancelledError(RuntimeError):
    """Raised when a download is cancelled by the user."""


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available on the system PATH."""
    return shutil.which("ffmpeg") is not None


def download_track(
    job: DownloadJob,
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    control: Optional[DownloadControl] = None,
) -> str:
    """
    Download and transcode a track according to the job specification.

    Args:
        job: A DownloadJob with search_result and output_format set.
        progress_callback: Optional callback for real-time progress updates.

    Returns:
        The absolute path to the final output file.

    Raises:
        RuntimeError: If the download or conversion fails.
    """
    if not job.search_result:
        raise RuntimeError("No search result to download")

    if not job.destination_dir:
        job.destination_dir = os.path.expanduser("~/Music/MiniDownloader")

    if job.use_smart_folders and job.track_info:
        artist_dir = sanitize_filename(job.track_info.artist) or "Unknown Artist"
        album_dir = sanitize_filename(job.track_info.album) if job.track_info.album else ""
        job.destination_dir = os.path.join(job.destination_dir, artist_dir, album_dir)

    os.makedirs(job.destination_dir, exist_ok=True)

    # Build output filename
    display = job.display_name or "Unknown Track"
    safe_name = sanitize_filename(display)
    ext = FORMAT_EXTENSIONS.get(job.output_format.value, ".mp3")
    final_path = os.path.join(job.destination_dir, f"{safe_name}{ext}")

    # Handle duplicate filenames
    counter = 1
    while os.path.exists(final_path):
        final_path = os.path.join(job.destination_dir, f"{safe_name} ({counter}){ext}")
        counter += 1

    # Set up yt-dlp options with ffmpeg postprocessor
    codec, quality = _get_ffmpeg_params(job.output_format)

    # Use a stable temp directory to allow resume
    job_id = job.job_id or uuid.uuid4().hex
    job.job_id = job_id
    temp_dir = os.path.join(job.destination_dir, ".minidownloader_tmp", job_id)
    os.makedirs(temp_dir, exist_ok=True)

    def _progress_hook(d: dict):
        if progress_callback is None:
            return
        if control:
            if control.cancel_event.is_set():
                raise DownloadCancelled()
            if control.pause_event.is_set():
                control.paused_event.set()
                progress_callback(DownloadProgress(
                    percent=job.progress.percent,
                    speed="",
                    eta="",
                    status="Paused",
                ))
                while control.pause_event.is_set() and not control.cancel_event.is_set():
                    time.sleep(0.2)
                control.paused_event.clear()
        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total > 0 else 0
            speed_bps = d.get("speed") or 0
            speed_str = _format_speed(speed_bps)
            eta_raw = d.get("eta") or 0
            eta_str = f"{eta_raw}s" if eta_raw else ""
            progress_callback(DownloadProgress(
                percent=pct,
                speed=speed_str,
                eta=eta_str,
                status="Downloading",
                downloaded_bytes=int(downloaded or 0),
                total_bytes=int(total or 0),
            ))
        elif status == "finished":
            progress_callback(DownloadProgress(
                percent=100, speed="", eta="", status="Converting",
            ))

    postprocessors = [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": codec,
    }]
    if quality:
        postprocessors[0]["preferredquality"] = quality

    # For FLAC: add extra ffmpeg args for 16-bit/44.1kHz
    postprocessor_args = {}
    if job.output_format == OutputFormat.FLAC:
        postprocessor_args = {
            "ffmpeg": ["-sample_fmt", "s16", "-ar", "44100"],
        }
    elif job.output_format == OutputFormat.ALAC:
        # yt-dlp doesn't have native ALAC support in postprocessor
        # We'll download as WAV first, then convert manually
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }]

    ydl_opts = {
        "format": "bestaudio/bestaudio*/best",
        "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_progress_hook],
        "postprocessors": postprocessors,
        "writethumbnail": False,
        "continuedl": job.enable_resume,
        "retries": max(1, job.max_retries),
    }
    if job.speed_limit_kbps > 0:
        ydl_opts["ratelimit"] = job.speed_limit_kbps * 1024
    if job.concurrent_fragments > 1:
        ydl_opts["concurrent_fragment_downloads"] = job.concurrent_fragments
    if postprocessor_args:
        ydl_opts["postprocessor_args"] = postprocessor_args
    ydl_opts = apply_yt_dlp_cookies(ydl_opts)

    success = False
    try:
        attempt = 0
        while True:
            try:
                attempt += 1
                job.attempts = attempt
                job.status = JobStatus.DOWNLOADING

                # ponytail: let yt-dlp handle format fallback natively via slash syntax without deleting extractor_args
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([job.search_result.url])

                # Find the output file in temp dir
                temp_files = os.listdir(temp_dir)
                if not temp_files:
                    raise RuntimeError("Download produced no output files")

                temp_output = os.path.join(temp_dir, temp_files[0])

                # Handle ALAC: convert WAV → ALAC via ffmpeg subprocess
                if job.output_format == OutputFormat.ALAC:
                    job.status = JobStatus.CONVERTING
                    if progress_callback:
                        progress_callback(DownloadProgress(
                            percent=95, speed="", eta="", status="Converting to ALAC",
                        ))
                    temp_output = _convert_to_alac(temp_output, temp_dir)

                # Move to final destination
                shutil.move(temp_output, final_path)
                job.output_path = final_path
                job.checksum_sha256 = _compute_sha256(final_path)
                success = True
                logger.info(
                    "Downloaded: %s → %s [quality: %s]",
                    job.display_name,
                    final_path,
                    _describe_output_quality(final_path),
                )
                return final_path

            except DownloadCancelled:
                job.status = JobStatus.CANCELLED
                raise DownloadCancelledError("Download cancelled")
            except Exception as e:
                logger.error("Download failed for '%s': %s", job.display_name, e)
                non_retryable = (
                    "Requested format is not available" in str(e)
                )
                if non_retryable:
                    raise RuntimeError(f"Download failed: {e}") from e
                if job.auto_retry and job.attempts <= job.max_retries:
                    time.sleep(max(1, job.retry_backoff_s) * job.attempts)
                    continue
                raise RuntimeError(f"Download failed: {e}") from e
    finally:
        if success or not job.enable_resume:
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


def _get_ffmpeg_params(fmt: OutputFormat) -> tuple[str, str]:
    """Return (codec, quality) for yt-dlp FFmpegExtractAudio postprocessor."""
    if fmt == OutputFormat.FLAC:
        return "flac", ""
    elif fmt == OutputFormat.ALAC:
        return "wav", ""  # Intermediate step
    elif fmt == OutputFormat.MP3_320:
        return "mp3", "320"
    return "mp3", "320"


def _convert_to_alac(input_path: str, temp_dir: str) -> str:
    """Convert a WAV file to ALAC (Apple Lossless) using ffmpeg subprocess."""
    import subprocess
    output_path = os.path.join(temp_dir, "output.m4a")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-acodec", "alac",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ALAC conversion failed: {e.stderr.decode()[:500]}") from e


def _format_speed(bps: float) -> str:
    """Format bytes/second into a human-readable string."""
    if bps <= 0:
        return ""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} MB/s"
    elif bps >= 1_000:
        return f"{bps / 1_000:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _compute_sha256(path: str) -> str:
    """Compute a SHA-256 checksum for the downloaded file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _describe_output_quality(path: str) -> str:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
        info = getattr(audio, "info", None)
        if info is None:
            return "unknown"

        parts: list[str] = []
        sample_rate = getattr(info, "sample_rate", None)
        bits_per_sample = getattr(info, "bits_per_sample", None)
        channels = getattr(info, "channels", None)
        bitrate = getattr(info, "bitrate", None)

        if sample_rate:
            parts.append(f"{sample_rate / 1000:.1f}kHz")
        if bits_per_sample:
            parts.append(f"{bits_per_sample}-bit")
        if channels:
            parts.append(f"{channels}ch")
        if bitrate:
            parts.append(f"{int(bitrate / 1000)}kbps")

        return ", ".join(parts) if parts else "unknown"
    except Exception:
        return "unknown"
