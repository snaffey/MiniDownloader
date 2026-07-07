"""
Dark theme color system and typography constants for MiniDownloader UI.
"""


class Colors:
    """Premium dark theme color palette."""

    # Backgrounds
    BG_DARK = "#0A0A0F"        # Deepest background
    BG_PRIMARY = "#12121A"     # Main window background
    BG_SURFACE = "#1A1A2E"     # Cards, panels
    BG_SURFACE_HOVER = "#222238"  # Hovered cards
    BG_INPUT = "#16162A"       # Input fields

    # Primary accent — vibrant purple
    PRIMARY = "#7C6AFF"
    PRIMARY_HOVER = "#9585FF"
    PRIMARY_DARK = "#5A4BD4"

    # Secondary accent — teal/green
    ACCENT = "#00D4AA"
    ACCENT_HOVER = "#00F0C0"
    ACCENT_DARK = "#00B890"

    # Status colors
    SUCCESS = "#4ECB71"
    WARNING = "#FFB347"
    ERROR = "#FF6B6B"
    INFO = "#64B5F6"

    # Text
    TEXT_PRIMARY = "#E8E8F0"
    TEXT_SECONDARY = "#9090AA"
    TEXT_MUTED = "#60607A"
    TEXT_ON_PRIMARY = "#FFFFFF"

    # Borders
    BORDER = "#2A2A40"
    BORDER_FOCUS = "#7C6AFF"

    # Progress bar
    PROGRESS_BG = "#1E1E32"
    PROGRESS_FILL = "#7C6AFF"

    # Scrollbar
    SCROLLBAR_BG = "#16162A"
    SCROLLBAR_FG = "#2A2A40"


class Fonts:
    """Typography settings."""

    # Font family — Inter preferred, with system fallbacks
    FAMILY = "Segoe UI"  # Windows default, Inter can be installed

    # Sizes
    SIZE_TITLE = 22
    SIZE_HEADING = 16
    SIZE_BODY = 14
    SIZE_SMALL = 12
    SIZE_TINY = 10

    @classmethod
    def title(cls):
        return (cls.FAMILY, cls.SIZE_TITLE, "bold")

    @classmethod
    def heading(cls):
        return (cls.FAMILY, cls.SIZE_HEADING, "bold")

    @classmethod
    def body(cls):
        return (cls.FAMILY, cls.SIZE_BODY)

    @classmethod
    def body_bold(cls):
        return (cls.FAMILY, cls.SIZE_BODY, "bold")

    @classmethod
    def small(cls):
        return (cls.FAMILY, cls.SIZE_SMALL)

    @classmethod
    def small_bold(cls):
        return (cls.FAMILY, cls.SIZE_SMALL, "bold")

    @classmethod
    def tiny(cls):
        return (cls.FAMILY, cls.SIZE_TINY)


class Dimensions:
    """Spacing and sizing constants."""

    # Window
    WINDOW_MIN_WIDTH = 800
    WINDOW_MIN_HEIGHT = 600
    WINDOW_DEFAULT_SIZE = "900x700"

    # Padding
    PAD_XS = 4
    PAD_SM = 8
    PAD_MD = 12
    PAD_LG = 16
    PAD_XL = 24

    # Border radius (CustomTkinter corner_radius)
    RADIUS_SM = 6
    RADIUS_MD = 10
    RADIUS_LG = 14

    # Queue item
    QUEUE_ITEM_HEIGHT = 96
    THUMBNAIL_SIZE = 52

    # Progress bar
    PROGRESS_HEIGHT = 6


def apply_high_contrast(enabled: bool) -> None:
    if not enabled:
        return
    Colors.BG_PRIMARY = "#0B0B0B"
    Colors.BG_SURFACE = "#1A1A1A"
    Colors.BG_INPUT = "#141414"
    Colors.TEXT_PRIMARY = "#FFFFFF"
    Colors.TEXT_SECONDARY = "#D0D0D0"
    Colors.TEXT_MUTED = "#9A9A9A"
    Colors.BORDER = "#3A3A3A"
    Colors.PROGRESS_BG = "#2A2A2A"
