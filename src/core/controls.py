"""
Thread control primitives for download jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading


@dataclass
class DownloadControl:
    pause_event: threading.Event = field(default_factory=threading.Event)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    paused_event: threading.Event = field(default_factory=threading.Event)
