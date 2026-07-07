"""
Settings window for MiniDownloader.
"""

from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from src.core.config import AppConfig, load_config, save_config
from src.core.models import JobPriority
from src.ui.theme import Colors, Dimensions, Fonts


class SettingsWindow(ctk.CTkToplevel):
    YT_TEST_URLS = (
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    BROWSER_COOKIE_OPTIONS = [
        "none",
        "brave",
        "chrome",
        "edge",
        "firefox",
        "vivaldi",
        "opera",
        "chromium",
        "custom",
    ]

    def __init__(self, master, cfg: AppConfig, on_save):
        super().__init__(master)
        self.title("Settings")
        self.geometry("760x640")
        self.resizable(False, False)
        self.configure(fg_color=Colors.BG_PRIMARY)
        self._on_save = on_save

        browser_value, profile_value = self._split_browser_cookie(cfg.yt_cookies_from_browser)

        self._vars = {
            "download_dir": tk.StringVar(value=cfg.download_dir),
            "use_smart_folders": tk.BooleanVar(value=cfg.use_smart_folders),
            "organize_by_source": tk.BooleanVar(value=cfg.organize_by_source),
            "organize_by_date": tk.BooleanVar(value=cfg.organize_by_date),
            "organize_by_format": tk.BooleanVar(value=cfg.organize_by_format),
            "date_folder_format": tk.StringVar(value=cfg.date_folder_format),
            "max_concurrent_downloads": tk.StringVar(value=str(cfg.max_concurrent_downloads)),
            "concurrent_fragments": tk.StringVar(value=str(cfg.concurrent_fragments)),
            "speed_limit_kbps": tk.StringVar(value=str(cfg.speed_limit_kbps)),
            "max_retries": tk.StringVar(value=str(cfg.max_retries)),
            "retry_backoff_s": tk.StringVar(value=str(cfg.retry_backoff_s)),
            "enable_resume": tk.BooleanVar(value=cfg.enable_resume),
            "auto_retry": tk.BooleanVar(value=cfg.auto_retry),
            "clipboard_monitor": tk.BooleanVar(value=cfg.clipboard_monitor),
            "watch_folder_enabled": tk.BooleanVar(value=cfg.watch_folder_enabled),
            "watch_folder_path": tk.StringVar(value=cfg.watch_folder_path),
            "watch_poll_interval_s": tk.StringVar(value=str(cfg.watch_poll_interval_s)),
            "schedule_enabled": tk.BooleanVar(value=cfg.schedule_enabled),
            "schedule_time": tk.StringVar(value=cfg.schedule_time),
            "notifications_enabled": tk.BooleanVar(value=cfg.notifications_enabled),
            "tray_enabled": tk.BooleanVar(value=cfg.tray_enabled),
            "background_mode": tk.BooleanVar(value=cfg.background_mode),
            "ui_scale": tk.DoubleVar(value=cfg.ui_scale),
            "appearance_mode": tk.StringVar(value=cfg.appearance_mode),
            "default_priority": tk.StringVar(value=cfg.default_priority.value),
            "high_contrast": tk.BooleanVar(value=cfg.high_contrast),
            "yt_cookies_file": tk.StringVar(value=cfg.yt_cookies_file),
            "yt_cookies_browser": tk.StringVar(value=browser_value),
            "yt_cookies_profile": tk.StringVar(value=profile_value),
        }

        self._build()

    def _build(self):
        container = ctk.CTkScrollableFrame(
            self,
            fg_color=Colors.BG_PRIMARY,
            corner_radius=0,
            scrollbar_button_color=Colors.SCROLLBAR_FG,
            scrollbar_button_hover_color=Colors.PRIMARY_DARK,
        )
        container.pack(fill="both", expand=True, padx=Dimensions.PAD_LG, pady=Dimensions.PAD_LG)

        self._section_title(container, "Downloads")
        self._option_row(container, "Default priority", self._vars["default_priority"], [p.value for p in JobPriority])
        self._entry_row(container, "Download folder", self._vars["download_dir"])
        self._checkbox_row(container, "Smart folders (artist/album)", self._vars["use_smart_folders"])
        self._entry_row(container, "Max concurrent downloads", self._vars["max_concurrent_downloads"])
        self._entry_row(container, "Concurrent fragments", self._vars["concurrent_fragments"])
        self._entry_row(container, "Speed limit (KB/s, 0 = unlimited)", self._vars["speed_limit_kbps"])
        self._entry_row(container, "Max retries", self._vars["max_retries"])
        self._entry_row(container, "Retry backoff (seconds)", self._vars["retry_backoff_s"])
        self._checkbox_row(container, "Resume partial downloads", self._vars["enable_resume"])
        self._checkbox_row(container, "Auto-retry failures", self._vars["auto_retry"])

        self._section_title(container, "YouTube")
        self._entry_row(container, "Cookies file", self._vars["yt_cookies_file"], browse_file=True)
        self._option_row(container, "Browser cookies", self._vars["yt_cookies_browser"], self.BROWSER_COOKIE_OPTIONS)
        self._entry_row(container, "Browser profile (optional)", self._vars["yt_cookies_profile"])
        self._action_row(container, "One-click setup", "Auto Setup", self._auto_setup_youtube_cookies)
        self._action_row(container, "Auto-detect browser", "Detect", self._detect_browser)
        self._action_row(container, "Test YouTube auth", "Test", self._test_youtube_auth)
        self._action_row(container, "How to get cookies", "Help", self._show_cookie_help)

        self._section_title(container, "Organization")
        self._checkbox_row(container, "Organize by source platform", self._vars["organize_by_source"])
        self._checkbox_row(container, "Organize by download date", self._vars["organize_by_date"])
        self._checkbox_row(container, "Organize by format", self._vars["organize_by_format"])
        self._entry_row(container, "Date folder format", self._vars["date_folder_format"])

        self._section_title(container, "Monitoring")
        self._checkbox_row(container, "Monitor clipboard for URLs", self._vars["clipboard_monitor"])
        self._checkbox_row(container, "Watch folder for URL files", self._vars["watch_folder_enabled"])
        self._entry_row(container, "Watch folder path", self._vars["watch_folder_path"], browse=True)
        self._entry_row(container, "Watch poll interval (seconds)", self._vars["watch_poll_interval_s"])

        self._section_title(container, "Scheduling")
        self._checkbox_row(container, "Enable scheduling", self._vars["schedule_enabled"])
        self._entry_row(container, "Schedule time (HH:MM or ISO)", self._vars["schedule_time"])

        self._section_title(container, "Notifications")
        self._checkbox_row(container, "Enable notifications", self._vars["notifications_enabled"])
        self._checkbox_row(container, "Enable tray mode", self._vars["tray_enabled"])
        self._checkbox_row(container, "Background mode", self._vars["background_mode"])

        self._section_title(container, "Appearance")
        self._option_row(container, "Appearance mode", self._vars["appearance_mode"], ["dark", "light", "system"])
        self._slider_row(container, "UI scale", self._vars["ui_scale"], 0.8, 1.4)
        self._checkbox_row(container, "High contrast colors", self._vars["high_contrast"])

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(Dimensions.PAD_LG, 0))

        save_btn = ctk.CTkButton(
            btn_row, text="Save",
            width=120, height=36,
            font=Fonts.body_bold(),
            fg_color=Colors.ACCENT,
            hover_color=Colors.ACCENT_HOVER,
            text_color=Colors.BG_DARK,
            corner_radius=Dimensions.RADIUS_MD,
            command=self._save,
        )
        save_btn.pack(side="right")

    def _section_title(self, master, text: str):
        label = ctk.CTkLabel(master, text=text, font=Fonts.heading(), text_color=Colors.TEXT_PRIMARY)
        label.pack(fill="x", pady=(Dimensions.PAD_MD, Dimensions.PAD_SM))

    def _entry_row(
        self,
        master,
        label: str,
        var: tk.StringVar,
        browse: bool = False,
        browse_file: bool = False,
    ):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(0, Dimensions.PAD_SM))
        ctk.CTkLabel(row, text=label, font=Fonts.small(), text_color=Colors.TEXT_SECONDARY).pack(side="left")
        entry = ctk.CTkEntry(row, textvariable=var, width=300, font=Fonts.small())
        entry.pack(side="right")
        if browse:
            btn = ctk.CTkButton(
                row, text="Browse", width=80, height=26,
                font=Fonts.tiny(),
                fg_color=Colors.BG_SURFACE,
                hover_color=Colors.BG_SURFACE_HOVER,
                text_color=Colors.TEXT_PRIMARY,
                command=lambda: self._browse_folder(var),
            )
            btn.pack(side="right", padx=(0, 8))
        if browse_file:
            btn = ctk.CTkButton(
                row, text="Browse", width=80, height=26,
                font=Fonts.tiny(),
                fg_color=Colors.BG_SURFACE,
                hover_color=Colors.BG_SURFACE_HOVER,
                text_color=Colors.TEXT_PRIMARY,
                command=lambda: self._browse_file(var),
            )
            btn.pack(side="right", padx=(0, 8))

    def _checkbox_row(self, master, label: str, var: tk.BooleanVar):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(0, Dimensions.PAD_SM))
        ctk.CTkCheckBox(
            row, text=label, variable=var,
            font=Fonts.small(), text_color=Colors.TEXT_SECONDARY,
            fg_color=Colors.PRIMARY, hover_color=Colors.PRIMARY_HOVER,
            border_color=Colors.BORDER,
        ).pack(side="left")

    def _option_row(self, master, label: str, var: tk.StringVar, options: list[str]):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(0, Dimensions.PAD_SM))
        ctk.CTkLabel(row, text=label, font=Fonts.small(), text_color=Colors.TEXT_SECONDARY).pack(side="left")
        menu = ctk.CTkOptionMenu(
            row,
            values=options,
            command=lambda v: var.set(v),
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
        )
        menu.set(var.get())
        menu.pack(side="right")

    def _slider_row(self, master, label: str, var: tk.DoubleVar, min_val: float, max_val: float):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(0, Dimensions.PAD_SM))
        ctk.CTkLabel(row, text=label, font=Fonts.small(), text_color=Colors.TEXT_SECONDARY).pack(side="left")
        slider = ctk.CTkSlider(row, from_=min_val, to=max_val, number_of_steps=6, variable=var)
        slider.pack(side="right", fill="x", expand=True, padx=(16, 0))

    def _action_row(self, master, label: str, button_text: str, command):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(0, Dimensions.PAD_SM))
        ctk.CTkLabel(row, text=label, font=Fonts.small(), text_color=Colors.TEXT_SECONDARY).pack(side="left")
        btn = ctk.CTkButton(
            row,
            text=button_text,
            width=120,
            height=26,
            font=Fonts.tiny(),
            fg_color=Colors.BG_SURFACE,
            hover_color=Colors.BG_SURFACE_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            command=command,
        )
        btn.pack(side="right")

    def _browse_folder(self, var: tk.StringVar):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            var.set(folder)

    def _browse_file(self, var: tk.StringVar):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Cookies File",
            filetypes=[("Cookies", "*.txt"), ("All files", "*.*")],
        )
        if path:
            var.set(path)
            if var is self._vars.get("yt_cookies_file"):
                self._vars["yt_cookies_browser"].set("none")
                self._vars["yt_cookies_profile"].set("")
                self._persist_youtube_cookie_settings()

    def _browser_candidates(self) -> list[tuple[str, str]]:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")
        return [
            ("firefox", os.path.join(app_data, "Mozilla", "Firefox", "Profiles")),
            ("brave", os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "User Data")),
            ("chrome", os.path.join(local_app_data, "Google", "Chrome", "User Data")),
            ("edge", os.path.join(local_app_data, "Microsoft", "Edge", "User Data")),
            ("vivaldi", os.path.join(local_app_data, "Vivaldi", "User Data")),
            ("opera", os.path.join(app_data, "Opera Software", "Opera Stable")),
            ("chromium", os.path.join(local_app_data, "Chromium", "User Data")),
        ]

    def _available_browsers(self) -> list[str]:
        return [browser for browser, path in self._browser_candidates() if path and os.path.exists(path)]

    def _clean_error_message(self, msg: str) -> str:
        # yt-dlp can include ANSI color escapes in exceptions; remove them for UI dialogs.
        msg = re.sub(r"\x1b\[[0-9;]*m", "", msg or "")
        msg = re.sub(r"\[[0-9;]*m", "", msg)
        return msg.strip()

    def _is_dpapi_error(self, msg: str) -> bool:
        lower = (msg or "").lower()
        return "dpapi" in lower or "failed to decrypt" in lower

    def _persist_youtube_cookie_settings(self) -> None:
        cfg = load_config()
        yt_cookies_file = self._vars["yt_cookies_file"].get().strip()
        yt_cookies_from_browser = self._build_browser_cookie_value()
        if yt_cookies_file:
            yt_cookies_from_browser = ""
        cfg.yt_cookies_file = yt_cookies_file
        cfg.yt_cookies_from_browser = yt_cookies_from_browser
        save_config(cfg)

    def _detect_browser(self):
        for browser in self._available_browsers():
            self._vars["yt_cookies_browser"].set(browser)
            self._vars["yt_cookies_profile"].set("")
            messagebox.showinfo("Browser detected", f"Using {browser} cookies.")
            return

        messagebox.showwarning(
            "No browser found",
            "No supported browser profiles detected. Choose a browser manually or use a cookies file.",
        )

    def _test_auth_config(self, cfg: AppConfig) -> tuple[bool, str]:
        import yt_dlp
        from yt_dlp.utils import DownloadError
        from src.core.yt_dlp_config import apply_yt_dlp_cookies

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
        }
        ydl_opts = apply_yt_dlp_cookies(ydl_opts, cfg)

        last_msg = "Unknown error"
        for url in self.YT_TEST_URLS:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=False)
                return True, "OK"
            except DownloadError as exc:
                msg = self._clean_error_message(str(exc))
                last_msg = msg
                if "Sign in to confirm" in msg or "bot" in msg:
                    return False, "YouTube requires sign-in. Try another browser/profile or export cookies to a file."
                if (
                    "Video unavailable" in msg
                    or "This video is unavailable" in msg
                    or "No video formats found" in msg
                ):
                    continue
                return False, msg
            except Exception as exc:
                return False, self._clean_error_message(str(exc))

        if "No video formats found" in last_msg:
            return (
                False,
                "yt-dlp could not extract formats from YouTube right now. "
                "Please update yt-dlp (pip install -U yt-dlp) and try Test again.",
            )
        return False, last_msg

    def _auto_setup_youtube_cookies(self):
        def _run_auto_setup():
            from src.core.config import AppConfig

            errors: list[str] = []
            saw_dpapi_error = False
            available_browsers = self._available_browsers()
            if not available_browsers:
                self.after(0, lambda: messagebox.showwarning(
                    "No browser found",
                    "No supported browser profiles detected. Open YouTube in a browser first, then try again.",
                ))
                return

            for browser in available_browsers:
                cfg = AppConfig()
                cfg.yt_cookies_from_browser = browser
                ok, msg = self._test_auth_config(cfg)
                if ok:
                    self.after(0, lambda b=browser: self._apply_auto_setup_result(b))
                    return
                if self._is_dpapi_error(msg):
                    saw_dpapi_error = True
                errors.append(f"{browser}: {msg}")

            details = "\n".join(errors[:3])
            extra_help = ""
            if saw_dpapi_error:
                extra_help = (
                    "\n\nDetected Windows DPAPI decryption errors for Chromium cookies.\n"
                    "Use Firefox cookies if available, or export cookies.txt.\n"
                    "Also make sure MiniDownloader is not running as Administrator."
                )
            self.after(0, lambda: messagebox.showwarning(
                "Auto setup failed",
                "Could not find a working browser cookie source.\n\n"
                "Make sure you're logged into YouTube and browser is closed, then try again.\n\n"
                f"Last errors:\n{details}{extra_help}",
            ))

        threading.Thread(target=_run_auto_setup, daemon=True).start()

    def _apply_auto_setup_result(self, browser: str):
        self._vars["yt_cookies_file"].set("")
        self._vars["yt_cookies_browser"].set(browser)
        self._vars["yt_cookies_profile"].set("")
        self._persist_youtube_cookie_settings()
        messagebox.showinfo(
            "YouTube auth configured",
            f"Configured {browser} browser cookies successfully.\n"
            "Cookie settings were saved automatically.",
        )

    def _test_youtube_auth(self):
        self._persist_youtube_cookie_settings()

        def _run_test():
            from src.core.config import AppConfig

            cfg = AppConfig()
            cfg.yt_cookies_file = self._vars["yt_cookies_file"].get()
            cfg.yt_cookies_from_browser = self._build_browser_cookie_value()
            if cfg.yt_cookies_file.strip():
                cfg.yt_cookies_from_browser = ""

            ok, msg = self._test_auth_config(cfg)
            if ok:
                self.after(0, lambda: messagebox.showinfo(
                    "Auth OK",
                    "YouTube access looks good. You can start downloads.",
                ))
            else:
                self.after(0, lambda: messagebox.showwarning(
                    "Auth failed",
                    f"Could not verify YouTube access. {msg}",
                ))

        threading.Thread(target=_run_test, daemon=True).start()

    def _show_cookie_help(self):
        messagebox.showinfo(
            "How to get cookies",
            "Step-by-step:\n"
            "1) Open YouTube in your browser and confirm you're logged in.\n"
            "2) Close all browser windows.\n"
            "3) Open MiniDownloader as a normal user (not Administrator).\n"
            "4) Go to Settings > YouTube.\n"
            "5) Click 'Auto Setup'.\n"
            "6) If setup succeeds, click Save.\n"
            "7) If setup fails, set Browser cookies to firefox and click Test.\n"
            "8) If Chromium browsers still fail on Windows, export cookies.txt using\n"
            "   the 'Get cookies.txt locally' extension and select that file.\n"
            "9) Click Test again, then Save.\n\n"
            "Optional plugin for Chromium: https://github.com/seproDev/yt-dlp-ChromeCookieUnlock\n"
            "More info: https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies",
        )

    def _save(self):
        yt_cookies_from_browser = self._build_browser_cookie_value()
        yt_cookies_file = self._vars["yt_cookies_file"].get()
        if yt_cookies_file.strip():
            yt_cookies_from_browser = ""
        cfg = AppConfig(
            download_dir=self._vars["download_dir"].get(),
            use_smart_folders=self._vars["use_smart_folders"].get(),
            organize_by_source=self._vars["organize_by_source"].get(),
            organize_by_date=self._vars["organize_by_date"].get(),
            organize_by_format=self._vars["organize_by_format"].get(),
            date_folder_format=self._vars["date_folder_format"].get(),
            max_concurrent_downloads=int(self._vars["max_concurrent_downloads"].get() or 3),
            concurrent_fragments=int(self._vars["concurrent_fragments"].get() or 4),
            speed_limit_kbps=int(self._vars["speed_limit_kbps"].get() or 0),
            max_retries=int(self._vars["max_retries"].get() or 2),
            retry_backoff_s=int(self._vars["retry_backoff_s"].get() or 5),
            enable_resume=self._vars["enable_resume"].get(),
            auto_retry=self._vars["auto_retry"].get(),
            clipboard_monitor=self._vars["clipboard_monitor"].get(),
            watch_folder_enabled=self._vars["watch_folder_enabled"].get(),
            watch_folder_path=self._vars["watch_folder_path"].get(),
            watch_poll_interval_s=int(self._vars["watch_poll_interval_s"].get() or 5),
            schedule_enabled=self._vars["schedule_enabled"].get(),
            schedule_time=self._vars["schedule_time"].get(),
            notifications_enabled=self._vars["notifications_enabled"].get(),
            tray_enabled=self._vars["tray_enabled"].get(),
            background_mode=self._vars["background_mode"].get(),
            default_priority=JobPriority(self._vars["default_priority"].get()),
            ui_scale=float(self._vars["ui_scale"].get() or 1.0),
            appearance_mode=self._vars["appearance_mode"].get(),
            high_contrast=self._vars["high_contrast"].get(),
            yt_cookies_file=yt_cookies_file,
            yt_cookies_from_browser=yt_cookies_from_browser,
        )
        if self._on_save:
            self._on_save(cfg)
        self.destroy()

    def _split_browser_cookie(self, value: str) -> tuple[str, str]:
        raw = (value or "").strip()
        if not raw:
            return "none", ""
        if ":" in raw:
            browser, profile = raw.split(":", 1)
        else:
            browser, profile = raw, ""
        browser = browser.strip().lower()
        profile = profile.strip()
        if browser not in self.BROWSER_COOKIE_OPTIONS:
            return "custom", raw
        if browser == "custom":
            return "custom", raw
        return browser, profile

    def _build_browser_cookie_value(self) -> str:
        browser = (self._vars["yt_cookies_browser"].get() or "").strip().lower()
        profile = (self._vars["yt_cookies_profile"].get() or "").strip()
        if not browser or browser == "none":
            return ""
        if browser == "custom":
            return profile
        if profile:
            return f"{browser}:{profile}"
        return browser
