"""
Main application window for MiniDownloader.

Orchestrates the UI layout and wires up the download pipeline
with threaded workers for non-blocking operation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests
import customtkinter as ctk

from src.core.config import AppConfig, load_config, save_config
from src.core.controls import DownloadControl
from src.core.history import HistoryEntry, HistoryStore
from src.core.models import (
    DownloadJob, DownloadProgress, JobPriority, JobStatus, OutputFormat, TrackInfo,
)
from src.core.scraper import scrape_metadata, scrape_playlist
from src.core.searcher import search_and_match
from src.core.downloader import download_track, DownloadCancelledError
from src.core.tagger import tag_file
from src.core.yt_dlp_config import apply_yt_dlp_cookies
from src.ui.theme import Colors, Dimensions, Fonts, apply_high_contrast
from src.ui.widgets import URLInputBar, FormatSelector, DownloadQueue
from src.ui.tray import TrayManager
from src.utils.constants import detect_platform, is_collection_url
from src.utils.paths import get_queue_path

logger = logging.getLogger(__name__)


class MiniDownloaderApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self._config = load_config()
        apply_high_contrast(self._config.high_contrast)
        try:
            ctk.set_widget_scaling(self._config.ui_scale)
        except Exception:
            pass
        try:
            ctk.set_appearance_mode(self._config.appearance_mode)
        except Exception:
            pass

        # Window config
        self.title("MiniDownloader")
        self.geometry(Dimensions.WINDOW_DEFAULT_SIZE)
        self.minsize(Dimensions.WINDOW_MIN_WIDTH, Dimensions.WINDOW_MIN_HEIGHT)
        self.configure(fg_color=Colors.BG_PRIMARY)

        # State
        self._executor = ThreadPoolExecutor(max_workers=self._config.max_concurrent_downloads)
        self._active_jobs: dict[int, DownloadJob] = {}
        self._controls: dict[int, DownloadControl] = {}
        self._job_start_times: dict[int, float] = {}
        self._running_jobs: set[int] = set()
        self._lock = threading.Lock()
        self._history = HistoryStore()
        self._queue_path = get_queue_path()
        self._last_clipboard = ""
        self._seen_watch_files: set[str] = set()
        self._last_watch_poll = 0.0
        self._tray: Optional[TrayManager] = None
        self._queue_dirty = False
        self._last_queue_save = 0.0

        # Build UI
        self._build_ui()

        self._load_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start scheduler tick
        self.after(2000, self._scheduler_tick)

        if self._config.tray_enabled:
            self._init_tray()

    def _build_ui(self):
        """Construct the full UI layout."""
        # Main container with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=Dimensions.PAD_XL, pady=Dimensions.PAD_XL)

        # ─── Header ───
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, Dimensions.PAD_LG))

        # App title with gradient-like effect
        title_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_row.pack(fill="x")

        icon_label = ctk.CTkLabel(
            title_row, text="🎵", font=("Segoe UI", 28),
            text_color=Colors.PRIMARY,
        )
        icon_label.pack(side="left", padx=(0, 8))

        title_label = ctk.CTkLabel(
            title_row, text="MiniDownloader",
            font=Fonts.title(), text_color=Colors.TEXT_PRIMARY,
        )
        title_label.pack(side="left")

        subtitle = ctk.CTkLabel(
            title_row, text="Universal Music Downloader",
            font=Fonts.small(), text_color=Colors.TEXT_MUTED,
        )
        subtitle.pack(side="left", padx=(12, 0), pady=(6, 0))

        actions = ctk.CTkFrame(header_frame, fg_color="transparent")
        actions.pack(side="right")

        self._checker_btn = ctk.CTkButton(
            actions, text="🎧 Rekordbox Check", width=125, height=28,
            font=Fonts.small(),
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER,
            text_color=Colors.TEXT_ON_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._open_checker,
        )
        self._checker_btn.pack(side="left", padx=(0, 8))

        self._history_btn = ctk.CTkButton(
            actions, text="History", width=80, height=28,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._open_history,
        )
        self._history_btn.pack(side="left", padx=(0, 8))

        self._settings_btn = ctk.CTkButton(
            actions, text="Settings", width=80, height=28,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._open_settings,
        )
        self._settings_btn.pack(side="left")

        # ─── URL Input ───
        self._url_input = URLInputBar(
            container, on_submit=self._on_urls_submitted, on_paste=self._paste_from_clipboard,
        )
        self._url_input.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        # ─── Format + Folder row ───
        self._format_selector = FormatSelector(
            container,
            on_format_change=self._on_format_change,
            on_folder_change=self._on_folder_change,
        )
        self._format_selector.pack(fill="x", pady=(0, Dimensions.PAD_LG))
        self._format_selector.set_defaults(self._config.download_dir, self._config.use_smart_folders)

        # ─── Divider ───
        divider = ctk.CTkFrame(container, fg_color=Colors.BORDER, height=1)
        divider.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        # ─── Queue header ───
        queue_header = ctk.CTkFrame(container, fg_color="transparent")
        queue_header.pack(fill="x", pady=(0, Dimensions.PAD_SM))

        queue_title = ctk.CTkLabel(
            queue_header, text="DOWNLOAD QUEUE",
            font=Fonts.small(), text_color=Colors.TEXT_MUTED,
        )
        queue_title.pack(side="left")

        self._import_btn = ctk.CTkButton(
            queue_header, text="Import", width=70, height=28,
            font=Fonts.small(),
            fg_color="transparent", hover_color=Colors.BG_SURFACE,
            text_color=Colors.TEXT_MUTED, border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._import_queue,
        )
        self._import_btn.pack(side="right", padx=(0, 6))

        self._export_btn = ctk.CTkButton(
            queue_header, text="Export", width=70, height=28,
            font=Fonts.small(),
            fg_color="transparent", hover_color=Colors.BG_SURFACE,
            text_color=Colors.TEXT_MUTED, border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._export_queue,
        )
        self._export_btn.pack(side="right", padx=(0, 6))

        # Clear button
        self._clear_btn = ctk.CTkButton(
            queue_header, text="Clear All", width=80, height=28,
            font=Fonts.small(),
            fg_color="transparent", hover_color=Colors.BG_SURFACE,
            text_color=Colors.TEXT_MUTED, border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._clear_queue,
        )
        self._clear_btn.pack(side="right")

        # ─── Download Queue (scrollable) ───
        self._queue = DownloadQueue(container)
        self._queue.pack(fill="both", expand=True, pady=(0, Dimensions.PAD_MD))

        # ─── Bottom bar ───
        bottom_bar = ctk.CTkFrame(container, fg_color="transparent")
        bottom_bar.pack(fill="x")

        self._status_label = ctk.CTkLabel(
            bottom_bar, text="Ready",
            font=Fonts.small(), text_color=Colors.TEXT_MUTED,
            anchor="w",
        )
        self._status_label.pack(side="left")

        self._resume_all_btn = ctk.CTkButton(
            bottom_bar, text="Resume", width=90, height=32,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._resume_all,
        )
        self._resume_all_btn.pack(side="right", padx=(8, 0))

        self._pause_all_btn = ctk.CTkButton(
            bottom_bar, text="Pause", width=90, height=32,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._pause_all,
        )
        self._pause_all_btn.pack(side="right", padx=(8, 0))

        self._start_btn = ctk.CTkButton(
            bottom_bar, text="▶  START ALL", width=140, height=40,
            font=Fonts.body_bold(),
            fg_color=Colors.ACCENT,
            hover_color=Colors.ACCENT_HOVER,
            text_color=Colors.BG_DARK,
            corner_radius=Dimensions.RADIUS_MD,
            command=self._start_all,
        )
        self._start_btn.pack(side="right")

    # ─── Callbacks ───

    def _on_urls_submitted(self, urls: list[str]):
        """Handle URL(s) submitted from the input bar."""
        for url in urls:
            url = url.strip()
            if not url:
                continue

            # Check if this is a playlist/album — expand into individual tracks
            if is_collection_url(url):
                self._status_label.configure(text=f"Expanding playlist...")
                self.update_idletasks()
                # Run playlist scraping in a background thread to avoid freezing UI
                self._executor.submit(self._expand_collection, url)
            else:
                self._add_single_job(url)

        self._update_queue_count()

    def _expand_collection(self, url: str):
        """Scrape a playlist/album URL and add each track as a separate job."""
        try:
            tracks = scrape_playlist(url)
            # Schedule adding jobs on the main thread (Tkinter requirement)
            def _add_all():
                added = 0
                skipped = 0
                for track in tracks:
                    card_id = self._add_single_job(
                        track.source_url or url,
                        prefetched_track=track,
                    )
                    if card_id is None:
                        skipped += 1
                    else:
                        added += 1
                self._update_queue_count()
                msg = f"Added {added} tracks from playlist"
                if skipped:
                    msg += f" ({skipped} duplicates skipped)"
                self._status_label.configure(text=msg)
            self.after(0, _add_all)
        except Exception as e:
            logger.error("Failed to expand playlist %s: %s", url, e)
            def _show_error():
                self._status_label.configure(
                    text=f"Failed to load playlist: {e}"
                )
            self.after(0, _show_error)

    def _add_single_job(
        self,
        url: str,
        prefetched_track: TrackInfo | None = None,
        destination_override: Optional[str] = None,
    ) -> Optional[int]:
        """Create and enqueue a single download job."""
        dedupe_keys = self._job_dedupe_keys(url, prefetched_track)
        duplicate_of = self._find_duplicate_job(dedupe_keys)
        if duplicate_of is not None:
            logger.info("Skipping duplicate URL: %s", url)
            self._status_label.configure(text=f"Skipped duplicate: {duplicate_of.display_name}")
            return None

        dest = destination_override or self._get_destination()
        job = DownloadJob(
            source_url=url,
            output_format=self._get_output_format(),
            destination_dir=os.path.expanduser(dest),
            status=JobStatus.QUEUED,
            job_id=uuid.uuid4().hex,
            created_at=datetime.utcnow().isoformat(),
            priority=self._config.default_priority,
            max_retries=self._config.max_retries,
            retry_backoff_s=self._config.retry_backoff_s,
            speed_limit_kbps=self._config.speed_limit_kbps,
            concurrent_fragments=self._config.concurrent_fragments,
            enable_resume=self._config.enable_resume,
            auto_retry=self._config.auto_retry,
        )

        scheduled = self._next_schedule_time()
        if scheduled and scheduled > datetime.now():
            job.scheduled_for = scheduled.isoformat()
            job.status = JobStatus.SCHEDULED

        # If track metadata was already fetched (from playlist expansion),
        # attach it so the pipeline can skip the scrape stage
        if prefetched_track is not None:
            job.track_info = prefetched_track

        card_id = self._queue.add_job(
            job,
            on_pause=self._pause_job,
            on_resume=self._resume_job,
            on_cancel=self._cancel_job,
            on_retry=self._retry_job,
            on_priority_change=self._update_job_priority,
            on_tags_change=self._update_job_tags,
        )
        with self._lock:
            self._active_jobs[card_id] = job
            self._controls[card_id] = DownloadControl()
        self._mark_queue_dirty()

        # Update card metadata immediately if we have it
        if prefetched_track:
            card = self._queue.get_card(card_id)
            if card:
                card.update_metadata(prefetched_track)
        if job.status == JobStatus.SCHEDULED and job.scheduled_for:
            self._update_ui(card_id, status=JobStatus.SCHEDULED, custom_text=f"Scheduled {job.scheduled_for}")
        return card_id

    def _add_job_from_import(self, job: DownloadJob) -> Optional[int]:
        dedupe_keys = self._job_dedupe_keys(job.source_url, job.track_info)
        duplicate_of = self._find_duplicate_job(dedupe_keys)
        if duplicate_of is not None:
            logger.info("Skipping duplicate imported job: %s", job.source_url)
            return None

        card_id = self._queue.add_job(
            job,
            on_pause=self._pause_job,
            on_resume=self._resume_job,
            on_cancel=self._cancel_job,
            on_retry=self._retry_job,
            on_priority_change=self._update_job_priority,
            on_tags_change=self._update_job_tags,
        )
        with self._lock:
            self._active_jobs[card_id] = job
            self._controls[card_id] = DownloadControl()
        self._mark_queue_dirty()
        if job.track_info:
            card = self._queue.get_card(card_id)
            if card:
                card.update_metadata(job.track_info)
        return card_id

    def _update_queue_count(self):
        """Update the status bar with the current queue count."""
        count = len(self._active_jobs)
        self._status_label.configure(
            text=f"{count} track{'s' if count != 1 else ''} in queue"
        )

    def _on_format_change(self, value: str):
        pass  # Format is read at download time

    def _on_folder_change(self, folder: str):
        self._config.download_dir = folder
        save_config(self._config)

    def _clear_queue(self):
        self._queue.clear_all()
        with self._lock:
            self._active_jobs.clear()
            self._controls.clear()
            self._running_jobs.clear()
        self._mark_queue_dirty()
        self._status_label.configure(text="Ready")

    def _start_all(self):
        """Start downloading all queued jobs."""
        self._config.use_smart_folders = self._format_selector.use_smart_folders
        save_config(self._config)
        with self._lock:
            jobs_to_start = []
            for cid, job in self._active_jobs.items():
                if job.status == JobStatus.QUEUED:
                    jobs_to_start.append((cid, job))
                elif job.status == JobStatus.SCHEDULED and self._is_job_due(job):
                    jobs_to_start.append((cid, job))

        if not jobs_to_start:
            return

        self._start_btn.configure(state="disabled", text="Downloading...")

        jobs_to_start.sort(key=lambda item: self._priority_rank(item[1]), reverse=True)

        for card_id, job in jobs_to_start:
            # Update format/folder at submit time
            job.output_format = self._get_output_format()
            job.destination_dir = self._get_destination()
            job.use_smart_folders = self._format_selector.use_smart_folders
            job.max_retries = self._config.max_retries
            job.retry_backoff_s = self._config.retry_backoff_s
            job.speed_limit_kbps = self._config.speed_limit_kbps
            job.concurrent_fragments = self._config.concurrent_fragments
            job.enable_resume = self._config.enable_resume
            job.auto_retry = self._config.auto_retry
            self._executor.submit(self._process_job, card_id, job)

    def _process_job(self, card_id: int, job: DownloadJob):
        """
        Full download pipeline, runs in a worker thread.

        Stages: Scrape → Search → Download → Tag → Done
        """
        card = self._queue.get_card(card_id)
        if not card:
            return

        control = self._controls.get(card_id)
        self._job_start_times[card_id] = time.time()
        with self._lock:
            self._running_jobs.add(card_id)

        try:
            # Stage 1: Scrape metadata
            self._update_ui(card_id, status=JobStatus.SCRAPING, custom_text="Fetching metadata...")

            if job.track_info is not None and job.source_url:
                # Pre-fetched from playlist — enrich with per-track metadata
                # (album art, album name, duration) from the individual track page
                track = job.track_info
                logger.info("Enriching playlist track: %s", track.display_name)
                try:
                    full_track = scrape_metadata(job.source_url)
                    # Merge: keep playlist title/artist (already correct),
                    # but take album, duration, and artwork from the track page
                    if full_track.thumbnail_url:
                        track.thumbnail_url = full_track.thumbnail_url
                    if full_track.album:
                        track.album = full_track.album
                    if full_track.duration_s and not track.duration_s:
                        track.duration_s = full_track.duration_s
                except Exception as e:
                    logger.warning("Could not enrich track '%s': %s", track.display_name, e)
            elif job.track_info is not None:
                # Pre-fetched but no individual URL available — use as-is
                track = job.track_info
            else:
                # Single track URL — scrape from scratch
                track = scrape_metadata(job.source_url)
                job.track_info = track

            self._update_ui(card_id, track=track)

            # Download thumbnail for the card
            if track.thumbnail_url:
                self._load_thumbnail(card_id, track.thumbnail_url)

            # Stage 2: Search YouTube Music (skip if SoundCloud or YouTube)
            if track.source_platform.value in ("soundcloud", "youtube"):
                self._update_ui(card_id, status=JobStatus.SEARCHING, custom_text="Preparing direct download...")
                from src.core.models import SearchResult
                job.search_result = SearchResult(
                    video_id=track.source_platform.value,
                    title=track.title,
                    duration_s=track.duration_s or 0,
                    url=track.source_url
                )
            else:
                self._update_ui(card_id, status=JobStatus.SEARCHING, custom_text="Finding best audio...")
                result = search_and_match(track)
                if result is None:
                    raise RuntimeError(f"No matching audio found for '{track.display_name}'")
                job.search_result = result

            # Stage 3: Download + transcode
            self._update_ui(card_id, status=JobStatus.DOWNLOADING)

            def progress_cb(p: DownloadProgress):
                self._update_ui(card_id, progress=p)

            self._apply_organization(job)
            output_path = download_track(job, progress_callback=progress_cb, control=control)

            # Stage 4: Tag
            self._update_ui(card_id, status=JobStatus.TAGGING, custom_text="Embedding cover art...")
            tag_file(output_path, track)

            # Done!
            job.status = JobStatus.DONE
            job.output_path = output_path
            self._update_ui(card_id, status=JobStatus.DONE)
            self._record_history(card_id, job, status="Done")

        except DownloadCancelledError:
            job.status = JobStatus.CANCELLED
            self._update_ui(card_id, status=JobStatus.CANCELLED, custom_text="Cancelled")
            self._record_history(card_id, job, status="Cancelled")
        except Exception as e:
            logger.error("Job failed for %s: %s", job.source_url, e)
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            self._update_ui(card_id, status=JobStatus.FAILED, error=str(e))
            self._record_history(card_id, job, status="Failed", error=str(e))

        finally:
            with self._lock:
                self._running_jobs.discard(card_id)
            self._check_all_done()

    def _update_ui(
        self,
        card_id: int,
        status: Optional[JobStatus] = None,
        progress: Optional[DownloadProgress] = None,
        track: Optional[TrackInfo] = None,
        error: str = "",
        custom_text: str = "",
    ):
        """Thread-safe UI update via root.after()."""
        def _do():
            card = self._queue.get_card(card_id)
            if not card:
                return
            if status is not None:
                card.update_status(status, error, custom_text=custom_text)
            if progress is not None:
                card.update_progress(progress)
            if track is not None:
                card.update_metadata(track)
        self.after(0, _do)

    def _load_thumbnail(self, card_id: int, url: str):
        """Download and display thumbnail (called from worker thread)."""
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.content

            def _do():
                card = self._queue.get_card(card_id)
                if card:
                    card.set_thumbnail(data)
            self.after(0, _do)
        except Exception:
            pass

    def _check_all_done(self):
        """Re-enable the start button if all jobs are finished."""
        def _do():
            with self._lock:
                still_running = any(
                    j.status in (
                        JobStatus.SCRAPING,
                        JobStatus.SEARCHING,
                        JobStatus.DOWNLOADING,
                        JobStatus.CONVERTING,
                        JobStatus.TAGGING,
                    )
                    for j in self._active_jobs.values()
                )
            if not still_running:
                self._start_btn.configure(state="normal", text="▶  START ALL")
                done = sum(1 for j in self._active_jobs.values() if j.status == JobStatus.DONE)
                failed = sum(1 for j in self._active_jobs.values() if j.status == JobStatus.FAILED)
                self._status_label.configure(
                    text=f"Finished — {done} done, {failed} failed"
                )
        self.after(0, _do)

    # ─── Helpers ───

    def _get_output_format(self) -> OutputFormat:
        val = self._format_selector.selected_format
        if "ALAC" in val:
            return OutputFormat.ALAC
        elif "MP3" in val:
            return OutputFormat.MP3_320
        return OutputFormat.FLAC

    def _canonical_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    def _canonical_track_key(self, title: str, artist: str) -> str:
        t = self._canonical_text(title)
        a = self._canonical_text(artist)
        if not t:
            return ""
        return f"track:{a}|{t}"

    def _normalize_source_url(self, url: str) -> str:
        raw = (url or "").strip()
        if not raw:
            return ""
        try:
            parsed = urlsplit(raw)
            host = (parsed.netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            path = parsed.path.rstrip("/")
            query = ""
            if "youtube.com" in host and path == "/watch":
                video_id = (parse_qs(parsed.query or "").get("v") or [""])[0]
                if video_id:
                    query = urlencode({"v": video_id})
            return urlunsplit((parsed.scheme.lower(), host, path, query, ""))
        except Exception:
            return raw.lower()

    def _job_dedupe_keys(self, source_url: str, track_info: Optional[TrackInfo]) -> set[str]:
        keys: set[str] = set()
        normalized_url = self._normalize_source_url(source_url)
        if normalized_url:
            keys.add(f"url:{normalized_url}")
        if track_info:
            track_key = self._canonical_track_key(track_info.title, track_info.artist)
            if track_key:
                keys.add(track_key)
        return keys

    def _is_downloaded_job(self, job: DownloadJob) -> bool:
        return (
            job.status == JobStatus.DONE
            and bool(job.output_path)
            and os.path.exists(job.output_path)
        )

    def _find_duplicate_job(self, candidate_keys: set[str]) -> Optional[DownloadJob]:
        if not candidate_keys:
            return None

        with self._lock:
            existing_jobs = list(self._active_jobs.values())

        for existing in existing_jobs:
            if existing.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                continue
            if existing.status == JobStatus.DONE and not self._is_downloaded_job(existing):
                continue
            existing_keys = self._job_dedupe_keys(existing.source_url, existing.track_info)
            if candidate_keys & existing_keys:
                return existing

        for entry in self._history.list_entries():
            if entry.status.lower() != "done":
                continue
            if not entry.output_path or not os.path.exists(entry.output_path):
                continue
            history_keys: set[str] = set()
            normalized_url = self._normalize_source_url(entry.source_url)
            if normalized_url:
                history_keys.add(f"url:{normalized_url}")
            track_key = self._canonical_track_key(entry.title, entry.artist)
            if track_key:
                history_keys.add(track_key)
            if candidate_keys & history_keys:
                return DownloadJob(
                    source_url=entry.source_url,
                    track_info=TrackInfo(
                        title=entry.title,
                        artist=entry.artist,
                        album=entry.album,
                    ),
                    status=JobStatus.DONE,
                )
        return None

    def _get_destination(self) -> str:
        folder = self._format_selector.destination_folder
        return os.path.expanduser(folder)

    def _get_card_id(self, job: DownloadJob) -> Optional[int]:
        with self._lock:
            for cid, j in self._active_jobs.items():
                if j is job:
                    return cid
        return None

    def _priority_rank(self, job: DownloadJob) -> int:
        return {
            JobPriority.HIGH: 3,
            JobPriority.NORMAL: 2,
            JobPriority.LOW: 1,
        }.get(job.priority, 2)

    def _is_job_due(self, job: DownloadJob) -> bool:
        if not job.scheduled_for:
            return True
        try:
            due = datetime.fromisoformat(job.scheduled_for)
        except Exception:
            return True
        return datetime.now() >= due

    def _next_schedule_time(self) -> Optional[datetime]:
        if not self._config.schedule_enabled:
            return None
        raw = (self._config.schedule_time or "").strip()
        if not raw:
            return None
        try:
            if "T" in raw:
                return datetime.fromisoformat(raw)
            if ":" in raw:
                parts = raw.split(":", 1)
                hour = int(parts[0])
                minute = int(parts[1])
                now = datetime.now()
                candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate <= now:
                    candidate = candidate + timedelta(days=1)
                return candidate
        except Exception:
            return None
        return None

    def _scheduler_tick(self):
        self._start_due_jobs()
        self._poll_clipboard()
        self._poll_watch_folder()
        self._save_queue()
        self.after(2000, self._scheduler_tick)

    def _start_due_jobs(self):
        with self._lock:
            due = [
                (cid, job) for cid, job in self._active_jobs.items()
                if job.status == JobStatus.SCHEDULED and self._is_job_due(job)
            ]
        if not due:
            return
        due.sort(key=lambda item: self._priority_rank(item[1]), reverse=True)
        for card_id, job in due:
            job.status = JobStatus.QUEUED
            job.output_format = self._get_output_format()
            job.destination_dir = self._get_destination()
            job.use_smart_folders = self._format_selector.use_smart_folders
            job.max_retries = self._config.max_retries
            job.retry_backoff_s = self._config.retry_backoff_s
            job.speed_limit_kbps = self._config.speed_limit_kbps
            job.concurrent_fragments = self._config.concurrent_fragments
            job.enable_resume = self._config.enable_resume
            job.auto_retry = self._config.auto_retry
            self._executor.submit(self._process_job, card_id, job)

    def _pause_job(self, job: DownloadJob):
        card_id = self._get_card_id(job)
        if card_id is None:
            return
        control = self._controls.get(card_id)
        if control and card_id in self._running_jobs:
            control.pause_event.set()
        job.status = JobStatus.PAUSED
        self._update_ui(card_id, status=JobStatus.PAUSED, custom_text="Paused")

    def _resume_job(self, job: DownloadJob):
        card_id = self._get_card_id(job)
        if card_id is None:
            return
        control = self._controls.get(card_id)
        if control and control.pause_event.is_set():
            control.pause_event.clear()
            self._update_ui(card_id, status=JobStatus.DOWNLOADING, custom_text="Resuming...")
            return
        if job.status == JobStatus.PAUSED:
            if job.scheduled_for and not self._is_job_due(job):
                job.status = JobStatus.SCHEDULED
                self._update_ui(card_id, status=JobStatus.SCHEDULED)
            else:
                job.status = JobStatus.QUEUED
                self._update_ui(card_id, status=JobStatus.QUEUED)

    def _cancel_job(self, job: DownloadJob):
        card_id = self._get_card_id(job)
        if card_id is None:
            return
        control = self._controls.get(card_id)
        if control:
            control.cancel_event.set()
        job.status = JobStatus.CANCELLED
        self._update_ui(card_id, status=JobStatus.CANCELLED, custom_text="Cancelled")
        self._mark_queue_dirty()

    def _retry_job(self, job: DownloadJob):
        card_id = self._get_card_id(job)
        if card_id is None:
            return
        control = self._controls.get(card_id)
        if control:
            control.cancel_event.clear()
            control.pause_event.clear()
        job.error_message = ""
        job.attempts = 0
        job.status = JobStatus.QUEUED
        self._update_ui(card_id, status=JobStatus.QUEUED, custom_text="Queued")
        self._mark_queue_dirty()

    def _pause_all(self):
        with self._lock:
            jobs = list(self._active_jobs.values())
        for job in jobs:
            self._pause_job(job)

    def _resume_all(self):
        with self._lock:
            jobs = list(self._active_jobs.values())
        for job in jobs:
            self._resume_job(job)

    def _update_job_priority(self, job: DownloadJob, priority: JobPriority):
        job.priority = priority
        self._mark_queue_dirty()

    def _update_job_tags(self, job: DownloadJob, tags: list[str]):
        job.tags = tags
        self._mark_queue_dirty()

    def _apply_organization(self, job: DownloadJob):
        base = self._get_destination()
        if self._config.organize_by_source and job.track_info:
            base = os.path.join(base, job.track_info.source_platform.value)
        if self._config.organize_by_date:
            try:
                base = os.path.join(base, datetime.utcnow().strftime(self._config.date_folder_format))
            except Exception:
                base = os.path.join(base, datetime.utcnow().strftime("%Y/%m"))
        if self._config.organize_by_format:
            base = os.path.join(base, job.output_format.value)
        job.destination_dir = base

    def _mark_queue_dirty(self):
        self._queue_dirty = True

    def _save_queue(self):
        if not self._queue_dirty:
            return
        now = time.time()
        if now - self._last_queue_save < 2:
            return
        self._last_queue_save = now
        with self._lock:
            jobs = [
                j.to_dict() for j in self._active_jobs.values()
                if j.status not in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)
            ]
        try:
            self._queue_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
            self._queue_dirty = False
        except Exception:
            pass

    def _load_queue(self):
        if not self._queue_path.exists():
            return
        try:
            data = json.loads(self._queue_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, list):
            return
        from src.core.models import DownloadJob
        for raw in data:
            try:
                job = DownloadJob.from_dict(raw)
            except Exception:
                continue
            if not job.source_url:
                continue
            self._add_job_from_import(job)
        self._update_queue_count()

    def _poll_clipboard(self):
        if not self._config.clipboard_monitor:
            return
        try:
            text = self.clipboard_get()
        except Exception:
            return
        if not text or text == self._last_clipboard:
            return
        self._last_clipboard = text
        urls = [u.strip() for u in text.splitlines() if u.strip().startswith("http")]
        added = 0
        for url in urls:
            platform, _ = detect_platform(url)
            if platform.value != "unknown":
                if self._add_single_job(url) is not None:
                    added += 1
        if added:
            self._status_label.configure(text=f"Added {added} URL(s) from clipboard")
            self._update_queue_count()

    def _poll_watch_folder(self):
        if not self._config.watch_folder_enabled:
            return
        if not self._config.watch_folder_path:
            return
        now = time.time()
        if now - self._last_watch_poll < max(2, self._config.watch_poll_interval_s):
            return
        self._last_watch_poll = now
        try:
            files = os.listdir(self._config.watch_folder_path)
        except Exception:
            return
        for name in files:
            if not name.lower().endswith((".txt", ".urls")):
                continue
            full = os.path.join(self._config.watch_folder_path, name)
            if full in self._seen_watch_files:
                continue
            try:
                raw = open(full, "r", encoding="utf-8").read()
            except Exception:
                continue
            urls = [u.strip() for u in raw.splitlines() if u.strip().startswith("http")]
            added = 0
            for url in urls:
                platform, _ = detect_platform(url)
                if platform.value != "unknown":
                    if self._add_single_job(url) is not None:
                        added += 1
            if added:
                self._status_label.configure(text=f"Added {added} URL(s) from watch folder")
                self._update_queue_count()
            self._seen_watch_files.add(full)

    def _paste_from_clipboard(self):
        try:
            text = self.clipboard_get()
        except Exception:
            return
        urls = [u.strip() for u in text.splitlines() if u.strip().startswith("http")]
        added = 0
        for url in urls:
            platform, _ = detect_platform(url)
            if platform.value != "unknown":
                if self._add_single_job(url) is not None:
                    added += 1
        if added:
            self._status_label.configure(text=f"Added {added} URL(s) from clipboard")
            self._update_queue_count()

    def _prefetch_media_info(self, card_id: int, job: DownloadJob):
        if not job.search_result or job.expected_size_bytes:
            return
        try:
            import yt_dlp
            ydl_opts = {"quiet": True, "no_warnings": True}
            ydl_opts = apply_yt_dlp_cookies(ydl_opts, self._config)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(job.search_result.url, download=False)
            size = info.get("filesize") or info.get("filesize_approx") or 0
            job.expected_size_bytes = int(size or 0)
            job.media_type = info.get("ext") or ""
            if job.track_info:
                self._update_ui(card_id, track=job.track_info)
        except Exception:
            pass

    def _record_history(self, card_id: int, job: DownloadJob, status: str, error: str = ""):
        track = job.track_info
        if not track:
            return
        start_ts = self._job_start_times.get(card_id, time.time())
        finished_ts = time.time()
        duration_s = max(0.1, finished_ts - start_ts)
        size_bytes = 0
        if job.output_path and os.path.exists(job.output_path):
            try:
                size_bytes = os.path.getsize(job.output_path)
            except Exception:
                size_bytes = 0
        avg_speed = size_bytes / duration_s if size_bytes > 0 else 0.0

        entry = HistoryEntry(
            job_id=job.job_id,
            title=track.title,
            artist=track.artist,
            album=track.album,
            platform=track.source_platform.value,
            source_url=job.source_url,
            output_path=job.output_path,
            output_format=job.output_format.value,
            status=status,
            tags=job.tags,
            size_bytes=size_bytes,
            checksum_sha256=job.checksum_sha256,
            started_at=datetime.utcfromtimestamp(start_ts).isoformat(),
            finished_at=datetime.utcfromtimestamp(finished_ts).isoformat(),
            duration_s=duration_s,
            avg_speed_bps=avg_speed,
            error_message=error,
        )
        self._history.add_entry(entry)
        self._mark_queue_dirty()
        if self._config.notifications_enabled:
            msg = f"{track.artist} - {track.title}"
            if status.lower() == "failed":
                msg = f"Failed: {msg}"
            self._notify("MiniDownloader", msg)

    def _notify(self, title: str, message: str):
        try:
            from plyer import notification
            notification.notify(title=title, message=message, timeout=4)
        except Exception:
            pass

    def _init_tray(self):
        self._tray = TrayManager(self._show_window, self._hide_window, self._exit_app)
        self._tray.start()

    def _on_close(self):
        if self._config.tray_enabled or self._config.background_mode:
            self._hide_window()
            return
        self._exit_app()

    def _show_window(self):
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass

    def _hide_window(self):
        try:
            self.withdraw()
        except Exception:
            pass

    def _exit_app(self):
        try:
            self.destroy()
        except Exception:
            pass

    def _open_settings(self):
        try:
            from src.ui.settings import SettingsWindow
            SettingsWindow(self, self._config, on_save=self._apply_settings)
        except Exception as e:
            logger.error("Failed to open settings: %s", e)

    def _open_history(self):
        try:
            from src.ui.history import HistoryWindow
            HistoryWindow(self, self._history)
        except Exception as e:
            logger.error("Failed to open history: %s", e)

    def _open_checker(self):
        try:
            from src.ui.checker import PlaylistCheckerWindow
            PlaylistCheckerWindow(self, self._get_destination())
        except Exception as e:
            logger.error("Failed to open playlist checker: %s", e)

    def _apply_settings(self, cfg: AppConfig):
        self._config = cfg
        apply_high_contrast(cfg.high_contrast)
        save_config(cfg)
        try:
            ctk.set_widget_scaling(cfg.ui_scale)
        except Exception:
            pass
        try:
            ctk.set_appearance_mode(cfg.appearance_mode)
        except Exception:
            pass
        self._format_selector.set_defaults(cfg.download_dir, cfg.use_smart_folders)
        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self._executor = ThreadPoolExecutor(max_workers=cfg.max_concurrent_downloads)

    def _export_queue(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export Queue",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        if not path:
            return
        jobs = []
        with self._lock:
            jobs = [j.to_dict() for j in self._active_jobs.values()]
        if path.lower().endswith(".csv"):
            import csv
            fields = ["source_url", "title", "artist", "album", "priority", "tags", "status"]
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                for j in jobs:
                    track = j.get("track_info") or {}
                    writer.writerow({
                        "source_url": j.get("source_url", ""),
                        "title": track.get("title", ""),
                        "artist": track.get("artist", ""),
                        "album": track.get("album", ""),
                        "priority": j.get("priority", ""),
                        "tags": ", ".join(j.get("tags", []) or []),
                        "status": j.get("status", ""),
                    })
            return
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)

    def _import_queue(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Import Queue",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        if not path:
            return
        if path.lower().endswith(".csv"):
            import csv
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("source_url") or row.get("url") or ""
                    if url:
                        self._add_single_job(url)
            self._update_queue_count()
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not isinstance(data, list):
            return
        from src.core.models import DownloadJob
        for raw in data:
            try:
                job = DownloadJob.from_dict(raw)
            except Exception:
                continue
            if not job.source_url:
                continue
            self._add_job_from_import(job)
        self._update_queue_count()

    def destroy(self):
        """Clean up thread pool on exit."""
        if self._tray:
            self._tray.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()
