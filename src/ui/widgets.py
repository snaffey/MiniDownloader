"""
Custom reusable widgets for MiniDownloader UI.

Built on top of CustomTkinter with the dark theme system.
"""

from __future__ import annotations

import io
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from src.core.models import DownloadJob, DownloadProgress, JobPriority, JobStatus
from src.ui.theme import Colors, Dimensions, Fonts


class URLInputBar(ctk.CTkFrame):
    """
    URL input area with a text box supporting multi-line paste (batch mode)
    and an 'Add to Queue' button.
    """

    def __init__(
        self,
        master,
        on_submit: Callable[[list[str]], None],
        on_paste: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_submit = on_submit
        self._on_paste = on_paste
        self._build()

    def _build(self):
        # Header label
        header = ctk.CTkLabel(
            self, text="Paste URL(s)", font=Fonts.small(),
            text_color=Colors.TEXT_SECONDARY, anchor="w",
        )
        header.pack(fill="x", padx=2, pady=(0, 4))

        # Input row
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(fill="x")
        input_frame.grid_columnconfigure(0, weight=1)

        self._textbox = ctk.CTkTextbox(
            input_frame,
            height=70,
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=Dimensions.RADIUS_MD,
            font=Fonts.body(),
        )
        self._textbox.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # Placeholder
        self._textbox.insert("1.0", "Paste a Spotify, Apple Music, Tidal, Deezer, or Amazon Music URL...")
        self._textbox.configure(text_color=Colors.TEXT_MUTED)
        self._textbox.bind("<FocusIn>", self._on_focus_in)
        self._textbox.bind("<FocusOut>", self._on_focus_out)
        self._has_placeholder = True

        # Add button
        self._add_btn = ctk.CTkButton(
            input_frame,
            text="ADD  ▶",
            width=100,
            height=70,
            font=Fonts.body_bold(),
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER,
            text_color=Colors.TEXT_ON_PRIMARY,
            corner_radius=Dimensions.RADIUS_MD,
            command=self._handle_submit,
        )
        self._add_btn.grid(row=0, column=1, padx=(0, 8))

        self._paste_btn = ctk.CTkButton(
            input_frame,
            text="PASTE",
            width=80,
            height=70,
            font=Fonts.body_bold(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_MD,
            command=self._handle_paste,
        )
        self._paste_btn.grid(row=0, column=2)

    def _on_focus_in(self, _event):
        if self._has_placeholder:
            self._textbox.delete("1.0", "end")
            self._textbox.configure(text_color=Colors.TEXT_PRIMARY)
            self._has_placeholder = False

    def _on_focus_out(self, _event):
        content = self._textbox.get("1.0", "end").strip()
        if not content:
            self._textbox.insert("1.0", "Paste a Spotify, Apple Music, Tidal, Deezer, or Amazon Music URL...")
            self._textbox.configure(text_color=Colors.TEXT_MUTED)
            self._has_placeholder = True

    def _handle_submit(self):
        if self._has_placeholder:
            return
        raw = self._textbox.get("1.0", "end").strip()
        if not raw:
            return
        urls = [u.strip() for u in raw.splitlines() if u.strip()]
        if urls:
            self._on_submit(urls)
            self._textbox.delete("1.0", "end")
            self._has_placeholder = False

    def _handle_paste(self):
        if self._on_paste:
            self._on_paste()


class FormatSelector(ctk.CTkFrame):
    """Output format dropdown and destination folder picker."""

    def __init__(
        self,
        master,
        on_format_change: Optional[Callable[[str], None]] = None,
        on_folder_change: Optional[Callable[[str], None]] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_format_change = on_format_change
        self._on_folder_change = on_folder_change
        self._folder_var = tk.StringVar(value="~/Music/MiniDownloader")
        self._smart_folder_var = tk.BooleanVar(value=True)
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)

        # Format label + dropdown
        fmt_label = ctk.CTkLabel(
            self, text="Format:", font=Fonts.body_bold(),
            text_color=Colors.TEXT_SECONDARY,
        )
        fmt_label.grid(row=0, column=0, padx=(0, 8))

        self._format_menu = ctk.CTkOptionMenu(
            self,
            values=["FLAC", "ALAC", "MP3 320kbps"],
            font=Fonts.body(),
            dropdown_font=Fonts.body(),
            fg_color=Colors.BG_SURFACE,
            button_color=Colors.PRIMARY_DARK,
            button_hover_color=Colors.PRIMARY,
            dropdown_fg_color=Colors.BG_SURFACE,
            dropdown_hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            width=140,
            command=self._format_changed,
        )
        self._format_menu.set("FLAC")
        self._format_menu.grid(row=0, column=1, sticky="w", padx=(0, 20))

        # Folder label + display + browse button
        folder_label = ctk.CTkLabel(
            self, text="Folder:", font=Fonts.body_bold(),
            text_color=Colors.TEXT_SECONDARY,
        )
        folder_label.grid(row=0, column=2, padx=(0, 8))

        self._folder_display = ctk.CTkLabel(
            self,
            textvariable=self._folder_var,
            font=Fonts.small(),
            text_color=Colors.TEXT_MUTED,
            anchor="w",
        )
        self._folder_display.grid(row=0, column=3, sticky="ew", padx=(0, 8))

        browse_btn = ctk.CTkButton(
            self,
            text="📁",
            width=36,
            height=28,
            font=Fonts.body(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._browse_folder,
        )
        browse_btn.grid(row=0, column=4)

        # Smart Folders checkbox
        self._smart_folder_check = ctk.CTkCheckBox(
            self, text="Smart Folders", font=Fonts.small(),
            variable=self._smart_folder_var,
            text_color=Colors.TEXT_SECONDARY,
            fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
            border_color=Colors.BORDER,
            checkbox_width=20, checkbox_height=20, border_width=2,
        )
        self._smart_folder_check.grid(row=0, column=5, padx=(20, 0))

    def _format_changed(self, value: str):
        if self._on_format_change:
            self._on_format_change(value)

    def _browse_folder(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Select Download Folder")
        if folder:
            self._folder_var.set(folder)
            if self._on_folder_change:
                self._on_folder_change(folder)

    def set_defaults(self, folder: str, use_smart_folders: bool):
        if folder:
            self._folder_var.set(folder)
        self._smart_folder_var.set(bool(use_smart_folders))

    @property
    def selected_format(self) -> str:
        return self._format_menu.get()

    @property
    def destination_folder(self) -> str:
        return self._folder_var.get()

    @property
    def use_smart_folders(self) -> bool:
        return self._smart_folder_var.get()


class QueueItemCard(ctk.CTkFrame):
    """
    A single download job card in the queue.
    Shows thumbnail, track name, progress bar, speed, and status badge.
    """

    def __init__(
        self,
        master,
        job: DownloadJob,
        on_pause: Optional[Callable[[DownloadJob], None]] = None,
        on_resume: Optional[Callable[[DownloadJob], None]] = None,
        on_cancel: Optional[Callable[[DownloadJob], None]] = None,
        on_retry: Optional[Callable[[DownloadJob], None]] = None,
        on_priority_change: Optional[Callable[[DownloadJob, JobPriority], None]] = None,
        on_tags_change: Optional[Callable[[DownloadJob, list[str]], None]] = None,
        **kwargs,
    ):
        super().__init__(
            master,
            fg_color=Colors.BG_SURFACE,
            corner_radius=Dimensions.RADIUS_MD,
            height=Dimensions.QUEUE_ITEM_HEIGHT,
            **kwargs,
        )
        self.job = job
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_cancel = on_cancel
        self._on_retry = on_retry
        self._on_priority_change = on_priority_change
        self._on_tags_change = on_tags_change
        self._paused = False
        self._thumb_image = None
        self._build()

    def _build(self):
        self.pack_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        # Thumbnail placeholder
        self._thumb_label = ctk.CTkLabel(
            self,
            text="🎵",
            width=Dimensions.THUMBNAIL_SIZE,
            height=Dimensions.THUMBNAIL_SIZE,
            fg_color=Colors.BG_INPUT,
            corner_radius=Dimensions.RADIUS_SM,
            font=("Segoe UI", 20),
        )
        self._thumb_label.grid(row=0, column=0, rowspan=2, padx=Dimensions.PAD_MD, pady=Dimensions.PAD_MD)

        # Info Frame (Name + Metadata)
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=(0, Dimensions.PAD_MD), pady=(Dimensions.PAD_MD, 0))
        
        # Track name
        self._name_label = ctk.CTkLabel(
            info_frame,
            text=self.job.display_name,
            font=Fonts.body_bold(),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w",
        )
        self._name_label.pack(fill="x", anchor="w")
        
        # Track metadata (Album • Duration)
        self._meta_label = ctk.CTkLabel(
            info_frame,
            text="",
            font=Fonts.tiny(),
            text_color=Colors.TEXT_MUTED,
            anchor="w",
        )
        self._meta_label.pack(fill="x", anchor="w", pady=(0, 2))

        # Progress row
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.grid(row=1, column=1, sticky="ew", padx=(0, Dimensions.PAD_MD), pady=(2, Dimensions.PAD_MD))
        progress_frame.grid_columnconfigure(0, weight=1)

        self._progress_bar = ctk.CTkProgressBar(
            progress_frame,
            height=Dimensions.PROGRESS_HEIGHT,
            fg_color=Colors.PROGRESS_BG,
            progress_color=Colors.PROGRESS_FILL,
            corner_radius=3,
        )
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self._speed_label = ctk.CTkLabel(
            progress_frame,
            text="",
            font=Fonts.tiny(),
            text_color=Colors.TEXT_MUTED,
            width=80,
            anchor="e",
        )
        self._speed_label.grid(row=0, column=1)

        # Status badge
        self._status_badge = ctk.CTkLabel(
            self,
            text=self.job.status.value,
            font=Fonts.tiny(),
            text_color=Colors.TEXT_ON_PRIMARY,
            fg_color=self._status_color(self.job.status),
            corner_radius=Dimensions.RADIUS_SM,
            width=80,
            height=24,
        )
        self._status_badge.grid(row=0, column=2, rowspan=2, padx=Dimensions.PAD_MD)

        # Controls row
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, Dimensions.PAD_MD), pady=(0, Dimensions.PAD_MD))
        controls_frame.grid_columnconfigure(0, weight=1)

        self._tags_entry = ctk.CTkEntry(
            controls_frame,
            height=24,
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=Dimensions.RADIUS_SM,
            font=Fonts.tiny(),
            placeholder_text="tags (comma-separated)",
        )
        if self.job.tags:
            self._tags_entry.insert(0, ", ".join(self.job.tags))
        self._tags_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._tags_entry.bind("<FocusOut>", self._on_tags_commit)
        self._tags_entry.bind("<Return>", self._on_tags_commit)

        self._priority_menu = ctk.CTkOptionMenu(
            controls_frame,
            values=[p.value for p in JobPriority],
            width=90,
            height=24,
            font=Fonts.tiny(),
            dropdown_font=Fonts.tiny(),
            fg_color=Colors.BG_SURFACE,
            button_color=Colors.PRIMARY_DARK,
            button_hover_color=Colors.PRIMARY,
            dropdown_fg_color=Colors.BG_SURFACE,
            dropdown_hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._priority_changed,
        )
        self._priority_menu.set(self.job.priority.value)
        self._priority_menu.grid(row=0, column=1, padx=(0, 8))

        self._pause_btn = ctk.CTkButton(
            controls_frame,
            text="Pause",
            width=60,
            height=24,
            font=Fonts.tiny(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._toggle_pause,
        )
        self._pause_btn.grid(row=0, column=2, padx=(0, 6))

        self._cancel_btn = ctk.CTkButton(
            controls_frame,
            text="Cancel",
            width=60,
            height=24,
            font=Fonts.tiny(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._cancel,
        )
        self._cancel_btn.grid(row=0, column=3, padx=(0, 6))

        self._retry_btn = ctk.CTkButton(
            controls_frame,
            text="Retry",
            width=60,
            height=24,
            font=Fonts.tiny(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._retry,
        )
        self._retry_btn.grid(row=0, column=4)

    def update_progress(self, progress: DownloadProgress):
        """Update the card with new progress data (called from main thread)."""
        self._progress_bar.set(progress.percent / 100.0)
        speed_text = progress.speed
        if progress.eta:
            speed_text += f"  ETA {progress.eta}"
        self._speed_label.configure(text=speed_text)
        
        # If progress hook provides a status string, update the badge
        if progress.status:
            # We skip updating if it's generic 'Converting' so our custom format message stays
            if progress.status != "Converting":
                self._status_badge.configure(
                    text=progress.status,
                    fg_color=self._status_color(self.job.status),
                )

    def update_status(self, status: JobStatus, error: str = "", custom_text: str = ""):
        """Update the status badge, optionally with custom descriptive text."""
        self.job.status = status
        text = custom_text if custom_text else status.value
        
        # Add format context for downloading and converting if not using custom text
        if not custom_text and status in (JobStatus.DOWNLOADING, JobStatus.CONVERTING) and self.job.output_format:
            fmt_name = self.job.output_format.name.replace("_", " ")
            if status == JobStatus.CONVERTING:
                text = f"Converting to {fmt_name}"
            else:
                text = "Downloading audio stream..."

        if status == JobStatus.FAILED and error:
            text = "Failed"
            
        self._status_badge.configure(
            text=text,
            fg_color=self._status_color(status),
        )
        if status == JobStatus.DONE:
            self._progress_bar.set(1.0)
            self._speed_label.configure(text="✓ Complete")
            self._pause_btn.configure(state="disabled")
            self._cancel_btn.configure(state="disabled")
            self._retry_btn.configure(state="disabled")
        elif status == JobStatus.FAILED:
            self._progress_bar.configure(progress_color=Colors.ERROR)
            self._speed_label.configure(text=error[:40] if error else "Error")
            self._retry_btn.configure(state="normal")
        elif status == JobStatus.PAUSED:
            self._paused = True
            self._pause_btn.configure(text="Resume")
        elif status == JobStatus.CANCELLED:
            self._pause_btn.configure(state="disabled")
            self._cancel_btn.configure(state="disabled")
            self._retry_btn.configure(state="normal")
        else:
            self._retry_btn.configure(state="disabled")
            if self._paused and status != JobStatus.PAUSED:
                self._paused = False
                self._pause_btn.configure(text="Pause")

    def update_metadata(self, track: 'TrackInfo'):
        """Update the track name and sub-metadata display."""
        self._name_label.configure(text=track.display_name)
        
        meta_parts = []
        if track.album:
            meta_parts.append(track.album)
        if track.duration_s:
            mins = int(track.duration_s // 60)
            secs = int(track.duration_s % 60)
            meta_parts.append(f"{mins}:{secs:02d}")

        if self.job.expected_size_bytes:
            meta_parts.append(self._format_bytes(self.job.expected_size_bytes))
            
        if meta_parts:
            self._meta_label.configure(text=" • ".join(meta_parts))

    def set_thumbnail(self, image_data: bytes):
        """Set the thumbnail from raw image bytes."""
        try:
            img = Image.open(io.BytesIO(image_data))
            img = img.resize(
                (Dimensions.THUMBNAIL_SIZE, Dimensions.THUMBNAIL_SIZE),
                Image.LANCZOS,
            )
            self._thumb_image = ctk.CTkImage(img, size=(Dimensions.THUMBNAIL_SIZE, Dimensions.THUMBNAIL_SIZE))
            self._thumb_label.configure(image=self._thumb_image, text="")
        except Exception:
            pass

    @staticmethod
    def _status_color(status: JobStatus) -> str:
        return {
            JobStatus.QUEUED: Colors.TEXT_MUTED,
            JobStatus.SCHEDULED: Colors.TEXT_MUTED,
            JobStatus.SCRAPING: Colors.INFO,
            JobStatus.SEARCHING: Colors.INFO,
            JobStatus.DOWNLOADING: Colors.PRIMARY,
            JobStatus.CONVERTING: Colors.WARNING,
            JobStatus.TAGGING: Colors.ACCENT,
            JobStatus.DONE: Colors.SUCCESS,
            JobStatus.FAILED: Colors.ERROR,
            JobStatus.PAUSED: Colors.WARNING,
            JobStatus.CANCELLED: Colors.TEXT_MUTED,
        }.get(status, Colors.TEXT_MUTED)

    @staticmethod
    def _format_bytes(num: int) -> str:
        if num <= 0:
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if num < 1024:
                return f"{num:.0f}{unit}"
            num /= 1024
        return f"{num:.1f}TB"

    def _toggle_pause(self):
        if self._paused:
            if self._on_resume:
                self._on_resume(self.job)
        else:
            if self._on_pause:
                self._on_pause(self.job)

    def _cancel(self):
        if self._on_cancel:
            self._on_cancel(self.job)

    def _retry(self):
        if self._on_retry:
            self._on_retry(self.job)

    def _priority_changed(self, value: str):
        if not self._on_priority_change:
            return
        try:
            pr = JobPriority(value)
        except Exception:
            pr = JobPriority.NORMAL
        self._on_priority_change(self.job, pr)

    def _on_tags_commit(self, _event=None):
        if not self._on_tags_change:
            return
        raw = self._tags_entry.get().strip()
        tags = [t.strip() for t in raw.split(",") if t.strip()]
        self._on_tags_change(self.job, tags)


class DownloadQueue(ctk.CTkScrollableFrame):
    """Scrollable container for QueueItemCard widgets."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=Colors.BG_PRIMARY,
            corner_radius=0,
            scrollbar_button_color=Colors.SCROLLBAR_FG,
            scrollbar_button_hover_color=Colors.PRIMARY_DARK,
            **kwargs,
        )
        self._cards: dict[int, QueueItemCard] = {}
        self._next_id = 0

        # Empty state label
        self._empty_label = ctk.CTkLabel(
            self,
            text="📥\n\nNo tracks in queue.\nPaste a URL above to get started.",
            font=Fonts.heading(),
            text_color=Colors.TEXT_MUTED,
        )
        self._empty_label.pack(pady=80)

    def add_job(
        self,
        job: DownloadJob,
        on_pause: Optional[Callable[[DownloadJob], None]] = None,
        on_resume: Optional[Callable[[DownloadJob], None]] = None,
        on_cancel: Optional[Callable[[DownloadJob], None]] = None,
        on_retry: Optional[Callable[[DownloadJob], None]] = None,
        on_priority_change: Optional[Callable[[DownloadJob, JobPriority], None]] = None,
        on_tags_change: Optional[Callable[[DownloadJob, list[str]], None]] = None,
    ) -> int:
        """Add a new job card to the queue. Returns the card ID."""
        if self._empty_label.winfo_ismapped():
            self._empty_label.pack_forget()

        card_id = self._next_id
        self._next_id += 1

        card = QueueItemCard(
            self,
            job,
            on_pause=on_pause,
            on_resume=on_resume,
            on_cancel=on_cancel,
            on_retry=on_retry,
            on_priority_change=on_priority_change,
            on_tags_change=on_tags_change,
        )
        card.pack(fill="x", padx=Dimensions.PAD_SM, pady=Dimensions.PAD_XS)
        self._cards[card_id] = card

        return card_id

    def get_card(self, card_id: int) -> Optional[QueueItemCard]:
        return self._cards.get(card_id)

    def clear_all(self):
        for card in self._cards.values():
            card.destroy()
        self._cards.clear()
        self._next_id = 0
        self._empty_label.pack(pady=40)
