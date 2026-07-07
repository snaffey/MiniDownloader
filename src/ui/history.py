"""
History window for MiniDownloader.
"""

from __future__ import annotations

import tkinter as tk
import customtkinter as ctk

from src.core.history import HistoryStore
from src.ui.theme import Colors, Dimensions, Fonts


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, master, history: HistoryStore):
        super().__init__(master)
        self.title("Download History")
        self.geometry("900x640")
        self.resizable(True, True)
        self.configure(fg_color=Colors.BG_PRIMARY)
        self._history = history

        self._search_var = tk.StringVar()
        self._status_var = tk.StringVar(value="All")
        self._platform_var = tk.StringVar(value="All")

        self._build()
        self._refresh()

    def _build(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=Dimensions.PAD_LG, pady=Dimensions.PAD_LG)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        ctk.CTkLabel(header, text="History", font=Fonts.title(), text_color=Colors.TEXT_PRIMARY).pack(side="left")

        export_btn = ctk.CTkButton(
            header, text="Export JSON", width=110, height=28,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            command=self._export_json,
        )
        export_btn.pack(side="right")

        export_csv_btn = ctk.CTkButton(
            header, text="Export CSV", width=110, height=28,
            font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            command=self._export_csv,
        )
        export_csv_btn.pack(side="right", padx=(0, 8))

        stats_frame = ctk.CTkFrame(container, fg_color=Colors.BG_SURFACE, corner_radius=Dimensions.RADIUS_MD)
        stats_frame.pack(fill="x", pady=(0, Dimensions.PAD_MD))
        self._stats_label = ctk.CTkLabel(stats_frame, text="", font=Fonts.small(), text_color=Colors.TEXT_MUTED)
        self._stats_label.pack(fill="x", padx=Dimensions.PAD_MD, pady=Dimensions.PAD_SM)

        filters = ctk.CTkFrame(container, fg_color="transparent")
        filters.pack(fill="x", pady=(0, Dimensions.PAD_MD))

        search_entry = ctk.CTkEntry(
            filters, textvariable=self._search_var,
            placeholder_text="Search title, artist, tags, path...",
            font=Fonts.small(),
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_PRIMARY,
            border_color=Colors.BORDER,
            border_width=1,
            corner_radius=Dimensions.RADIUS_SM,
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        search_entry.bind("<Return>", lambda _e: self._refresh())

        status_menu = ctk.CTkOptionMenu(
            filters,
            values=["All", "Done", "Failed", "Cancelled"],
            command=lambda _v: self._refresh(),
            width=120,
            font=Fonts.small(),
            dropdown_font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            button_color=Colors.PRIMARY_DARK,
            button_hover_color=Colors.PRIMARY,
            dropdown_fg_color=Colors.BG_SURFACE,
            dropdown_hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            variable=self._status_var,
        )
        status_menu.pack(side="left", padx=(0, 8))

        platform_menu = ctk.CTkOptionMenu(
            filters,
            values=["All", "spotify", "apple_music", "tidal", "deezer", "amazon_music", "soundcloud", "youtube"],
            command=lambda _v: self._refresh(),
            width=140,
            font=Fonts.small(),
            dropdown_font=Fonts.small(),
            fg_color=Colors.BG_SURFACE,
            button_color=Colors.PRIMARY_DARK,
            button_hover_color=Colors.PRIMARY,
            dropdown_fg_color=Colors.BG_SURFACE,
            dropdown_hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            variable=self._platform_var,
        )
        platform_menu.pack(side="left")

        self._list = ctk.CTkScrollableFrame(
            container,
            fg_color=Colors.BG_PRIMARY,
            corner_radius=0,
            scrollbar_button_color=Colors.SCROLLBAR_FG,
            scrollbar_button_hover_color=Colors.PRIMARY_DARK,
        )
        self._list.pack(fill="both", expand=True)

    def _refresh(self):
        for child in self._list.winfo_children():
            child.destroy()

        stats = self._history.stats()
        self._stats_label.configure(
            text=(
                f"Total: {stats['total']}  |  Success: {stats['success']}  |  "
                f"Failed: {stats['failed']}  |  Success rate: {stats['success_rate']}%  |  "
                f"Total bytes: {self._format_bytes(stats['bytes'])}  |  Avg speed: {self._format_speed(stats['avg_speed_bps'])}"
            )
        )

        status = self._status_var.get()
        if status == "All":
            status = ""
        platform = self._platform_var.get()
        if platform == "All":
            platform = ""

        results = self._history.search(
            query=self._search_var.get(),
            status=status,
            platform=platform,
        )

        if not results:
            ctk.CTkLabel(
                self._list,
                text="No history entries match your filters.",
                font=Fonts.small(),
                text_color=Colors.TEXT_MUTED,
            ).pack(pady=40)
            return

        for entry in results[::-1]:
            row = ctk.CTkFrame(self._list, fg_color=Colors.BG_SURFACE, corner_radius=Dimensions.RADIUS_MD)
            row.pack(fill="x", pady=(0, Dimensions.PAD_SM), padx=Dimensions.PAD_SM)

            title = f"{entry.artist} - {entry.title}"
            if entry.album:
                title += f"  ({entry.album})"

            ctk.CTkLabel(row, text=title, font=Fonts.body_bold(), text_color=Colors.TEXT_PRIMARY).pack(
                anchor="w", padx=Dimensions.PAD_MD, pady=(Dimensions.PAD_SM, 0)
            )
            meta = (
                f"{entry.platform}  |  {entry.status}  |  {self._format_bytes(entry.size_bytes)}  |  "
                f"{self._format_speed(entry.avg_speed_bps)}"
            )
            if entry.tags:
                meta += f"  |  tags: {', '.join(entry.tags)}"
            ctk.CTkLabel(row, text=meta, font=Fonts.tiny(), text_color=Colors.TEXT_MUTED).pack(
                anchor="w", padx=Dimensions.PAD_MD, pady=(0, Dimensions.PAD_SM)
            )

    def _export_json(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export History (JSON)",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if path:
            self._history.export_json(path)

    def _export_csv(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export History (CSV)",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if path:
            self._history.export_csv(path)

    @staticmethod
    def _format_bytes(num: int) -> str:
        if num <= 0:
            return "0B"
        for unit in ("B", "KB", "MB", "GB"):
            if num < 1024:
                return f"{num:.0f}{unit}"
            num /= 1024
        return f"{num:.1f}TB"

    @staticmethod
    def _format_speed(bps: float) -> str:
        if bps <= 0:
            return "0 B/s"
        if bps >= 1_000_000:
            return f"{bps / 1_000_000:.1f} MB/s"
        if bps >= 1_000:
            return f"{bps / 1_000:.0f} KB/s"
        return f"{bps:.0f} B/s"
