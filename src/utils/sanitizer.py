"""
Filename sanitization for cross-platform compatibility.

Handles Windows, macOS, and Linux filesystem restrictions.
"""

import re
import unicodedata

# Characters illegal on Windows
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*]')

# Control characters (U+0000–U+001F and U+007F)
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# Windows reserved device names
_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})

MAX_FILENAME_LENGTH = 200


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """
    Clean a string so it is safe to use as a filename on Windows, macOS, and Linux.

    Args:
        name: The raw filename (without extension).
        replacement: Character to substitute for illegal characters.

    Returns:
        A sanitized filename string.
    """
    if not name:
        return "untitled"

    # Normalize Unicode (NFC form — composed characters)
    name = unicodedata.normalize("NFC", name)

    # Replace illegal characters
    name = _ILLEGAL_CHARS.sub(replacement, name)

    # Remove control characters
    name = _CONTROL_CHARS.sub("", name)

    # Strip leading/trailing whitespace and dots (Windows issue)
    name = name.strip(" .")

    # Check for reserved names (Windows)
    stem = name.split(".")[0].upper()
    if stem in _RESERVED_NAMES:
        name = f"_{name}"

    # Truncate to safe length
    if len(name) > MAX_FILENAME_LENGTH:
        name = name[:MAX_FILENAME_LENGTH].rstrip(" .")

    # Final fallback
    if not name:
        return "untitled"

    return name
