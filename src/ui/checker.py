"""
UI Window for Rekordbox & Playlist Library Checker.
"""

from __future__ import annotations

import csv
import logging
import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from src.core.checker import LibraryChecker, TrackMatchResult
from src.core.models import TrackInfo
from src.ui.theme import Colors, Dimensions, Fonts

logger = logging.getLogger(__name__)


class PlaylistCheckerWindow(ctk.CTkToplevel):
    """
    Toplevel window for comparing a playlist against a local music folder (Rekordbox).
    """

    def __init__(self, master, default_folder: str):
        super().__init__(master)
        self.title("Rekordbox & Playlist Library Checker")
        self.geometry("960x740")
        self.minsize(800, 600)
        self.configure(fg_color=Colors.BG_PRIMARY)

        self._url_var = tk.StringVar()
        self._folder_var = tk.StringVar(value=default_folder or os.path.expanduser("~"))
        self._filter_var = tk.StringVar(value="All Tracks")
        self._search_var = tk.StringVar()
        self._status_var = tk.StringVar(value="Ready to compare playlist against folder.")

        self._results: List[TrackMatchResult] = []
        self._is_scanning = False
        self._item_widgets: List[ctk.CTkFrame] = []

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Main container
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=Dimensions.PAD_XL, pady=Dimensions.PAD_XL)

        # ─── Header ───
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, Dimensions.PAD_LG))

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")

        ctk.CTkLabel(
            title_row, text="🎧", font=("Segoe UI", 28), text_color=Colors.PRIMARY
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            title_row, text="Rekordbox & Playlist Checker", font=Fonts.title(), text_color=Colors.TEXT_PRIMARY
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Compare a Spotify (or other platform) playlist against your local Rekordbox / music folder to check what is already downloaded.",
            font=Fonts.small(),
            text_color=Colors.TEXT_MUTED,
        ).pack(fill="x", pady=(4, 0))

        # ─── Input Card ───
        input_card = ctk.CTkFrame(container, fg_color=Colors.BG_SURFACE, corner_radius=Dimensions.RADIUS_MD)
        input_card.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        # URL Row
        url_row = ctk.CTkFrame(input_card, fg_color="transparent")
        url_row.pack(fill="x", padx=Dimensions.PAD_LG, pady=(Dimensions.PAD_LG, Dimensions.PAD_SM))

        ctk.CTkLabel(
            url_row, text="Playlist URL:", font=Fonts.body_bold(), text_color=Colors.TEXT_PRIMARY, width=130, anchor="w"
        ).pack(side="left")

        url_entry = ctk.CTkEntry(
            url_row,
            textvariable=self._url_var,
            placeholder_text="Paste Spotify, Apple Music, Deezer, or YouTube playlist URL...",
            font=Fonts.body(),
            fg_color=Colors.BG_INPUT,
            border_color=Colors.BORDER,
            height=34,
        )
        url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        paste_btn = ctk.CTkButton(
            url_row,
            text="📋 Paste",
            width=80,
            height=34,
            font=Fonts.small(),
            fg_color=Colors.BG_PRIMARY,
            hover_color=Colors.BG_SURFACE_HOVER,
            command=self._paste_url,
        )
        paste_btn.pack(side="left")

        # Folder Row
        folder_row = ctk.CTkFrame(input_card, fg_color="transparent")
        folder_row.pack(fill="x", padx=Dimensions.PAD_LG, pady=(0, Dimensions.PAD_MD))

        ctk.CTkLabel(
            folder_row, text="Rekordbox Folder:", font=Fonts.body_bold(), text_color=Colors.TEXT_PRIMARY, width=130, anchor="w"
        ).pack(side="left")

        folder_entry = ctk.CTkEntry(
            folder_row,
            textvariable=self._folder_var,
            font=Fonts.body(),
            fg_color=Colors.BG_INPUT,
            border_color=Colors.BORDER,
            height=34,
        )
        folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = ctk.CTkButton(
            folder_row,
            text="📁 Browse...",
            width=80,
            height=34,
            font=Fonts.small(),
            fg_color=Colors.BG_PRIMARY,
            hover_color=Colors.BG_SURFACE_HOVER,
            command=self._browse_folder,
        )
        browse_btn.pack(side="left")

        # Scan & Progress Row
        action_row = ctk.CTkFrame(input_card, fg_color="transparent")
        action_row.pack(fill="x", padx=Dimensions.PAD_LG, pady=(0, Dimensions.PAD_LG))

        self._scan_btn = ctk.CTkButton(
            action_row,
            text="🔍 Scan & Compare",
            width=160,
            height=38,
            font=Fonts.body_bold(),
            fg_color=Colors.PRIMARY,
            hover_color=Colors.PRIMARY_HOVER,
            text_color=Colors.TEXT_ON_PRIMARY,
            corner_radius=Dimensions.RADIUS_SM,
            command=self._start_scan,
        )
        self._scan_btn.pack(side="left", padx=(0, Dimensions.PAD_LG))

        progress_frame = ctk.CTkFrame(action_row, fg_color="transparent")
        progress_frame.pack(side="left", fill="x", expand=True)

        self._status_label = ctk.CTkLabel(
            progress_frame, textvariable=self._status_var, font=Fonts.small(), text_color=Colors.TEXT_SECONDARY, anchor="w"
        )
        self._status_label.pack(fill="x", pady=(0, 4))

        self._progress_bar = ctk.CTkProgressBar(
            progress_frame, height=8, fg_color=Colors.PROGRESS_BG, progress_color=Colors.PROGRESS_FILL
        )
        self._progress_bar.pack(fill="x")
        self._progress_bar.set(0.0)

        # ─── Stats & Filter Bar (Initially Hidden / Empty) ───
        self._stats_card = ctk.CTkFrame(container, fg_color=Colors.BG_SURFACE, corner_radius=Dimensions.RADIUS_MD)
        self._stats_card.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        stats_row = ctk.CTkFrame(self._stats_card, fg_color="transparent")
        stats_row.pack(fill="x", padx=Dimensions.PAD_LG, pady=Dimensions.PAD_MD)

        self._lbl_total = ctk.CTkLabel(
            stats_row, text="Total: 0", font=Fonts.body_bold(), text_color=Colors.TEXT_PRIMARY
        )
        self._lbl_total.pack(side="left", padx=(0, 20))

        self._lbl_found = ctk.CTkLabel(
            stats_row, text="✅ In Rekordbox: 0 (0%)", font=Fonts.body_bold(), text_color=Colors.SUCCESS
        )
        self._lbl_found.pack(side="left", padx=(0, 20))

        self._lbl_missing = ctk.CTkLabel(
            stats_row, text="❌ Missing: 0", font=Fonts.body_bold(), text_color=Colors.ERROR
        )
        self._lbl_missing.pack(side="left", padx=(0, 20))

        # Filter controls
        filter_menu = ctk.CTkOptionMenu(
            stats_row,
            values=["All Tracks", "❌ Missing Only", "✅ In Rekordbox Only"],
            variable=self._filter_var,
            width=160,
            font=Fonts.small(),
            fg_color=Colors.BG_INPUT,
            button_color=Colors.BORDER,
            command=lambda _: self._render_results(),
        )
        filter_menu.pack(side="right")

        search_entry = ctk.CTkEntry(
            stats_row,
            textvariable=self._search_var,
            placeholder_text="Filter track or artist...",
            width=180,
            font=Fonts.small(),
            fg_color=Colors.BG_INPUT,
            border_color=Colors.BORDER,
            height=28,
        )
        search_entry.pack(side="right", padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda _e: self._render_results())

        # ─── Action Bar (Download Missing & Export) ───
        self._action_bar = ctk.CTkFrame(container, fg_color="transparent")
        self._action_bar.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        self._dl_missing_btn = ctk.CTkButton(
            self._action_bar,
            text="⬇️ Download All Missing Tracks to Queue",
            height=36,
            font=Fonts.body_bold(),
            fg_color=Colors.ACCENT,
            hover_color=Colors.ACCENT_HOVER,
            text_color="#000000",
            command=self._download_all_missing,
        )
        self._dl_missing_btn.pack(side="left")

        self._export_btn = ctk.CTkButton(
            self._action_bar,
            text="📋 Export Report (CSV)",
            width=150,
            height=36,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            command=self._export_csv,
        )
        self._export_btn.pack(side="right")

        # ─── Scrollable Track List ───
        self._list_frame = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self._list_frame.pack(fill="both", expand=True)

        # Show empty placeholder
        self._show_empty_placeholder("Paste a playlist URL and select your Rekordbox folder to scan.")

    def _paste_url(self):
        try:
            clipboard = self.clipboard_get()
            if clipboard:
                self._url_var.set(clipboard.strip())
        except Exception:
            pass

    def _browse_folder(self):
        folder = filedialog.askdirectory(
            initialdir=self._folder_var.get() or os.path.expanduser("~"),
            title="Select Rekordbox / Music Folder",
        )
        if folder:
            self._folder_var.set(folder)

    def _show_empty_placeholder(self, text: str):
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        self._item_widgets.clear()

        placeholder = ctk.CTkLabel(
            self._list_frame,
            text=text,
            font=Fonts.body(),
            text_color=Colors.TEXT_MUTED,
            pady=40,
        )
        placeholder.pack(fill="x", expand=True)

    def _start_scan(self):
        if self._is_scanning:
            return

        url = self._url_var.get().strip()
        folder = self._folder_var.get().strip()

        if not url:
            messagebox.showwarning("Missing Input", "Please enter a playlist or album URL.")
            return

        if not folder or not os.path.exists(folder):
            messagebox.showwarning("Invalid Folder", "Please select a valid folder path on your computer.")
            return

        self._is_scanning = True
        self._scan_btn.configure(state="disabled", text="⏳ Scanning...")
        self._progress_bar.set(0.05)
        self._status_var.set("Connecting and scraping playlist metadata...")
        self._show_empty_placeholder("Scanning playlist and indexing local music library... Please wait.")

        def worker():
            try:
                checker = LibraryChecker()

                def progress_cb(msg: str, pct: float):
                    self.after(0, lambda m=msg, p=pct: self._update_progress(m, p))

                res = checker.scan_and_compare(url, folder, progress_cb=progress_cb)
                self.after(0, lambda r=res: self._on_scan_complete(r))
            except Exception as e:
                logger.error("Error during playlist library check: %s", e, exc_info=True)
                self.after(0, lambda err=str(e): self._on_scan_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, msg: str, pct: float):
        self._status_var.set(msg)
        self._progress_bar.set(min(1.0, max(0.0, pct / 100.0)))

    def _on_scan_complete(self, results: List[TrackMatchResult]):
        self._is_scanning = False
        self._scan_btn.configure(state="normal", text="🔍 Scan & Compare")
        self._progress_bar.set(1.0)
        self._results = results

        total = len(results)
        found = sum(1 for r in results if r.exists)
        missing = total - found
        pct = round((found / total * 100), 1) if total > 0 else 0.0

        self._status_var.set(f"Scan complete! Found {found} tracks in folder, {missing} tracks missing.")
        self._lbl_total.configure(text=f"Total: {total}")
        self._lbl_found.configure(text=f"✅ In Rekordbox: {found} ({pct}%)")
        self._lbl_missing.configure(text=f"❌ Missing: {missing}")

        self._render_results()

    def _on_scan_error(self, err_msg: str):
        self._is_scanning = False
        self._scan_btn.configure(state="normal", text="🔍 Scan & Compare")
        self._progress_bar.set(0.0)
        self._status_var.set(f"Error: {err_msg}")
        messagebox.showerror("Scan Failed", f"Could not check playlist:\n\n{err_msg}")
        self._show_empty_placeholder(f"Scan failed: {err_msg}")

    def _render_results(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        self._item_widgets.clear()

        if not self._results:
            self._show_empty_placeholder("No tracks to display.")
            return

        filter_mode = self._filter_var.get()
        search_query = self._search_var.get().strip().lower()

        filtered = []
        for item in self._results:
            if filter_mode == "❌ Missing Only" and item.exists:
                continue
            if filter_mode == "✅ In Rekordbox Only" and not item.exists:
                continue

            if search_query:
                t_low = item.track.title.lower()
                a_low = item.track.artist.lower()
                f_low = (item.matched_rel_path or "").lower()
                if search_query not in t_low and search_query not in a_low and search_query not in f_low:
                    continue

            filtered.append(item)

        if not filtered:
            self._show_empty_placeholder("No tracks match your current filter/search.")
            return

        for item in filtered:
            card = self._create_track_card(item)
            card.pack(fill="x", pady=4, padx=4)
            self._item_widgets.append(card)

    def _create_track_card(self, item: TrackMatchResult) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._list_frame, fg_color=Colors.BG_SURFACE, corner_radius=Dimensions.RADIUS_SM)

        # Status badge
        badge_color = Colors.SUCCESS if item.exists else Colors.ERROR
        badge_text = "✅ IN REKORDBOX" if item.exists else "❌ MISSING"

        badge = ctk.CTkLabel(
            card,
            text=badge_text,
            font=Fonts.tiny(),
            text_color=Colors.TEXT_ON_PRIMARY,
            fg_color=badge_color,
            corner_radius=4,
            width=105,
            height=22,
        )
        badge.pack(side="left", padx=Dimensions.PAD_MD, pady=Dimensions.PAD_MD)

        # Info column
        info_col = ctk.CTkFrame(card, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True, padx=Dimensions.PAD_SM, pady=Dimensions.PAD_SM)

        title_str = item.track.display_name
        ctk.CTkLabel(
            info_col, text=title_str, font=Fonts.body_bold(), text_color=Colors.TEXT_PRIMARY, anchor="w"
        ).pack(fill="x")

        if item.exists:
            detail_str = f"📁 Found ({item.matched_by}): {item.matched_rel_path}"
            ctk.CTkLabel(
                info_col, text=detail_str, font=Fonts.small(), text_color=Colors.SUCCESS, anchor="w"
            ).pack(fill="x")
        else:
            album_str = f"Album: {item.track.album}" if item.track.album else "Not found in selected folder"
            ctk.CTkLabel(
                info_col, text=album_str, font=Fonts.small(), text_color=Colors.TEXT_MUTED, anchor="w"
            ).pack(fill="x")

        # Action column on right
        action_col = ctk.CTkFrame(card, fg_color="transparent")
        action_col.pack(side="right", padx=Dimensions.PAD_MD)

        if item.exists:
            open_btn = ctk.CTkButton(
                action_col,
                text="📂 Reveal File",
                width=100,
                height=28,
                font=Fonts.small(),
                fg_color=Colors.BG_INPUT,
                hover_color=Colors.BG_SURFACE_HOVER,
                text_color=Colors.TEXT_PRIMARY,
                command=lambda p=item.matched_file_path: self._reveal_file(p),
            )
            open_btn.pack()
        else:
            dl_btn = ctk.CTkButton(
                action_col,
                text="⬇️ Download",
                width=100,
                height=28,
                font=Fonts.small(),
                fg_color=Colors.PRIMARY,
                hover_color=Colors.PRIMARY_HOVER,
                text_color=Colors.TEXT_ON_PRIMARY,
                command=lambda i=item: self._download_single(i),
            )
            dl_btn.pack()

        return card

    def _reveal_file(self, filepath: Optional[str]):
        if not filepath or not os.path.exists(filepath):
            messagebox.showwarning("File Missing", "The matched audio file could not be found on disk.")
            return

        try:
            if os.name == "nt":
                subprocess.run(["explorer", "/select,", os.path.normpath(filepath)])
            elif os.name == "posix":
                if os.path.exists("/usr/bin/open"):  # macOS
                    subprocess.run(["open", "-R", filepath])
                else:  # Linux
                    subprocess.run(["xdg-open", os.path.dirname(filepath)])
        except Exception as e:
            logger.error("Failed to reveal file: %s", e)
            try:
                os.startfile(os.path.dirname(filepath))  # Windows fallback
            except Exception:
                pass

    def _download_single(self, item: TrackMatchResult):
        target_folder = self._folder_var.get().strip()
        track = item.track
        url = track.source_url or self._url_var.get().strip()

        card_id = self.master._add_single_job(
            url=url,
            prefetched_track=track,
            destination_override=target_folder,
        )

        if card_id is not None:
            self._status_var.set(f"Added '{track.display_name}' to download queue!")
            messagebox.showinfo("Queued", f"Added '{track.display_name}' to the download queue!\nDestination: {target_folder}")
        else:
            messagebox.showinfo("Skipped", f"'{track.display_name}' is already in the download queue or downloaded.")

    def _download_all_missing(self):
        missing_items = [r for r in self._results if not r.exists]
        if not missing_items:
            messagebox.showinfo("All Done!", "All tracks from this playlist are already present in your Rekordbox folder!")
            return

        target_folder = self._folder_var.get().strip()
        added = 0
        skipped = 0

        for item in missing_items:
            track = item.track
            url = track.source_url or self._url_var.get().strip()
            card_id = self.master._add_single_job(
                url=url,
                prefetched_track=track,
                destination_override=target_folder,
            )
            if card_id is not None:
                added += 1
            else:
                skipped += 1

        self._status_var.set(f"Added {added} missing tracks to download queue! ({skipped} duplicates skipped)")
        messagebox.showinfo(
            "Batch Download Queued",
            f"Successfully queued {added} missing tracks for download into:\n{target_folder}\n\n({skipped} tracks skipped as duplicates)"
        )

    def _export_csv(self):
        if not self._results:
            messagebox.showwarning("Nothing to Export", "Please run a scan first before exporting.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile="rekordbox_playlist_report.csv",
            title="Save Library Report",
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Status", "Title", "Artist", "Album", "Matched File", "Match Type", "Similarity Score"])
                for r in self._results:
                    status = "Exists in Rekordbox" if r.exists else "Missing"
                    writer.writerow([
                        status,
                        r.track.title,
                        r.track.artist,
                        r.track.album,
                        r.matched_rel_path or "",
                        r.matched_by or "",
                        r.similarity_score,
                    ])
            messagebox.showinfo("Export Success", f"Report saved successfully to:\n{filepath}")
        except Exception as e:
            logger.error("Failed to export report: %s", e)
            messagebox.showerror("Export Failed", f"Could not save report:\n{e}")

    def _on_close(self):
        self._is_scanning = False
        self.destroy()
