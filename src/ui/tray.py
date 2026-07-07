"""
System tray integration using pystray.
"""

from __future__ import annotations

import threading
from typing import Callable

from PIL import Image


class TrayManager:
    def __init__(self, on_show: Callable[[], None], on_hide: Callable[[], None], on_exit: Callable[[], None]):
        self._on_show = on_show
        self._on_hide = on_hide
        self._on_exit = on_exit
        self._icon = None

    def start(self):
        try:
            import pystray
        except Exception:
            return

        icon = Image.new("RGB", (64, 64), color=(124, 106, 255))
        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self._on_show()),
            pystray.MenuItem("Hide", lambda: self._on_hide()),
            pystray.MenuItem("Exit", lambda: self._on_exit()),
        )
        self._icon = pystray.Icon("MiniDownloader", icon, "MiniDownloader", menu)
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def stop(self):
        try:
            if self._icon:
                self._icon.stop()
        except Exception:
            pass
