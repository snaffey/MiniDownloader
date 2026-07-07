"""
MiniDownloader — Universal Music Downloader

Entry point. Checks for system dependencies, configures logging,
and launches the CustomTkinter application.
"""

import logging
import shutil
import sys
import os

# Ensure the project root is on the path so 'src' is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _check_ffmpeg() -> bool:
    """Verify that ffmpeg is available on the system PATH."""
    return shutil.which("ffmpeg") is not None


def _show_ffmpeg_error():
    """Show a GUI dialog explaining that ffmpeg is missing."""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title("MiniDownloader — Missing Dependency")
    root.geometry("500x280")
    root.resizable(False, False)

    frame = ctk.CTkFrame(root, fg_color="#12121A")
    frame.pack(fill="both", expand=True, padx=20, pady=20)

    ctk.CTkLabel(
        frame,
        text="⚠️  ffmpeg not found",
        font=("Segoe UI", 20, "bold"),
        text_color="#FF6B6B",
    ).pack(pady=(20, 10))

    ctk.CTkLabel(
        frame,
        text=(
            "MiniDownloader requires ffmpeg for audio conversion.\n\n"
            "Install it:\n"
            "• Windows: winget install ffmpeg\n"
            "• macOS: brew install ffmpeg\n"
            "• Linux: sudo apt install ffmpeg\n\n"
            "Then restart the application."
        ),
        font=("Segoe UI", 13),
        text_color="#E8E8F0",
        justify="left",
    ).pack(padx=20)

    ctk.CTkButton(
        frame,
        text="Close",
        command=root.destroy,
        fg_color="#7C6AFF",
        hover_color="#9585FF",
    ).pack(pady=15)

    root.mainloop()


def main():
    """Application entry point."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("MiniDownloader")

    # Check ffmpeg
    if not _check_ffmpeg():
        logger.error("ffmpeg not found in PATH")
        _show_ffmpeg_error()
        sys.exit(1)

    logger.info("Starting MiniDownloader...")

    # Set appearance before creating any widgets
    import customtkinter as ctk
    try:
        from src.core.config import load_config
        cfg = load_config()
        ctk.set_appearance_mode(cfg.appearance_mode)
    except Exception:
        ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # Launch the app
    from src.ui.app import MiniDownloaderApp
    app = MiniDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
