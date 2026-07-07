"""
Data models for the MiniDownloader pipeline.

Defines the core data structures that flow through the scraper → searcher → downloader → tagger pipeline.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, List


class Platform(enum.Enum):
    """Supported source platforms."""
    SPOTIFY = "spotify"
    APPLE_MUSIC = "apple_music"
    TIDAL = "tidal"
    DEEZER = "deezer"
    AMAZON_MUSIC = "amazon_music"
    SOUNDCLOUD = "soundcloud"
    YOUTUBE = "youtube"
    UNKNOWN = "unknown"


class OutputFormat(enum.Enum):
    """Supported output audio formats."""
    FLAC = "flac"
    ALAC = "alac"
    MP3_320 = "mp3"


class JobPriority(enum.Enum):
    """User-defined download priority."""
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"


class JobStatus(enum.Enum):
    """Download job lifecycle states."""
    QUEUED = "Queued"
    SCHEDULED = "Scheduled"
    SCRAPING = "Scraping Metadata"
    SEARCHING = "Searching"
    DOWNLOADING = "Downloading"
    CONVERTING = "Converting"
    TAGGING = "Tagging"
    DONE = "Done"
    FAILED = "Failed"
    PAUSED = "Paused"
    CANCELLED = "Cancelled"


@dataclass
class TrackInfo:
    """Metadata extracted from the source platform URL."""
    title: str
    artist: str
    album: str = ""
    duration_s: Optional[float] = None
    thumbnail_url: Optional[str] = None
    source_platform: Platform = Platform.UNKNOWN
    source_url: str = ""

    @property
    def search_query(self) -> str:
        """Build the optimized search query for YouTube Music."""
        return f"{self.artist} - {self.title} (Official Audio)"

    @property
    def fallback_query(self) -> str:
        """Broader fallback query without '(Official Audio)' qualifier."""
        return f"{self.artist} {self.title}"

    @property
    def display_name(self) -> str:
        """Human-readable display string."""
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_s": self.duration_s,
            "thumbnail_url": self.thumbnail_url,
            "source_platform": self.source_platform.value,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrackInfo":
        return cls(
            title=data.get("title", ""),
            artist=data.get("artist", ""),
            album=data.get("album", ""),
            duration_s=data.get("duration_s"),
            thumbnail_url=data.get("thumbnail_url"),
            source_platform=Platform(data.get("source_platform", Platform.UNKNOWN.value)),
            source_url=data.get("source_url", ""),
        )


@dataclass
class SearchResult:
    """A candidate match found on YouTube Music."""
    video_id: str
    title: str
    duration_s: float
    abr: float = 0.0  # Average bitrate in kbps
    url: str = ""
    score: float = 0.0
    match_score: float = 0.0

    def compute_score(
        self,
        original_duration: Optional[float] = None,
        match_score: Optional[float] = None,
    ) -> float:
        """
        Score this result based on bitrate and duration match.
        Higher is better.
        """
        self.score = self.abr * 10
        if original_duration is not None:
            duration_diff = abs(self.duration_s - original_duration)
            self.score -= duration_diff * 2
        if match_score is None:
            match_score = self.match_score
        if match_score:
            self.score += match_score * 1000
        return self.score


@dataclass
class DownloadProgress:
    """Real-time progress data for UI updates."""
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    status: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0


@dataclass
class DownloadJob:
    """A complete download task tracking state through the entire pipeline."""
    track_info: Optional[TrackInfo] = None
    search_result: Optional[SearchResult] = None
    output_format: OutputFormat = OutputFormat.FLAC
    status: JobStatus = JobStatus.QUEUED
    progress: DownloadProgress = field(default_factory=DownloadProgress)
    output_path: str = ""
    error_message: str = ""
    source_url: str = ""
    destination_dir: str = ""
    use_smart_folders: bool = False
    job_id: str = ""
    created_at: str = ""
    scheduled_for: Optional[str] = None
    priority: JobPriority = JobPriority.NORMAL
    tags: List[str] = field(default_factory=list)
    max_retries: int = 2
    attempts: int = 0
    speed_limit_kbps: int = 0
    concurrent_fragments: int = 4
    retry_backoff_s: int = 5
    enable_resume: bool = True
    auto_retry: bool = True
    expected_size_bytes: int = 0
    media_type: str = ""
    checksum_sha256: str = ""

    # Internal tracking
    _temp_file: str = ""

    @property
    def display_name(self) -> str:
        if self.track_info:
            return self.track_info.display_name
        return self.source_url or "Unknown Track"

    @property
    def thumbnail_url(self) -> Optional[str]:
        if self.track_info:
            return self.track_info.thumbnail_url
        return None

    def to_dict(self) -> dict:
        return {
            "track_info": self.track_info.to_dict() if self.track_info else None,
            "output_format": self.output_format.value,
            "status": self.status.value,
            "output_path": self.output_path,
            "error_message": self.error_message,
            "source_url": self.source_url,
            "destination_dir": self.destination_dir,
            "use_smart_folders": self.use_smart_folders,
            "job_id": self.job_id,
            "created_at": self.created_at,
            "scheduled_for": self.scheduled_for,
            "priority": self.priority.value,
            "tags": self.tags,
            "max_retries": self.max_retries,
            "attempts": self.attempts,
            "speed_limit_kbps": self.speed_limit_kbps,
            "concurrent_fragments": self.concurrent_fragments,
            "retry_backoff_s": self.retry_backoff_s,
            "enable_resume": self.enable_resume,
            "auto_retry": self.auto_retry,
            "expected_size_bytes": self.expected_size_bytes,
            "media_type": self.media_type,
            "checksum_sha256": self.checksum_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadJob":
        track_raw = data.get("track_info") or None
        track = TrackInfo.from_dict(track_raw) if track_raw else None
        job = cls(
            track_info=track,
            output_format=OutputFormat(data.get("output_format", OutputFormat.FLAC.value)),
            status=JobStatus(data.get("status", JobStatus.QUEUED.value)),
            output_path=data.get("output_path", ""),
            error_message=data.get("error_message", ""),
            source_url=data.get("source_url", ""),
            destination_dir=data.get("destination_dir", ""),
            use_smart_folders=bool(data.get("use_smart_folders", False)),
            job_id=data.get("job_id", ""),
            created_at=data.get("created_at", ""),
            scheduled_for=data.get("scheduled_for"),
            priority=JobPriority(data.get("priority", JobPriority.NORMAL.value)),
            tags=list(data.get("tags", []) or []),
            max_retries=int(data.get("max_retries", 2) or 2),
            attempts=int(data.get("attempts", 0) or 0),
            speed_limit_kbps=int(data.get("speed_limit_kbps", 0) or 0),
            concurrent_fragments=int(data.get("concurrent_fragments", 4) or 4),
            retry_backoff_s=int(data.get("retry_backoff_s", 5) or 5),
            enable_resume=bool(data.get("enable_resume", True)),
            auto_retry=bool(data.get("auto_retry", True)),
            expected_size_bytes=int(data.get("expected_size_bytes", 0) or 0),
            media_type=data.get("media_type", ""),
            checksum_sha256=data.get("checksum_sha256", ""),
        )
        return job
