"""Tesseract discovery.

The Windows installer does not add Tesseract to PATH, so importing pytesseract
is not enough -- the binary has to be located explicitly. Availability is
resolved once and cached, so a missing engine is reported clearly rather than
silently producing empty pages.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Where the common Windows installers put it.
WINDOWS_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

_state: dict | None = None


def _discover() -> dict:
    """Locate the binary and confirm it runs. Cached after the first call."""
    exe = shutil.which("tesseract")

    if not exe:
        for candidate in WINDOWS_CANDIDATES:
            if Path(candidate).exists():
                exe = candidate
                break

    if not exe:
        env = os.environ.get("TESSERACT_CMD")
        if env and Path(env).exists():
            exe = env

    if not exe:
        return {
            "available": False,
            "path": "",
            "version": "",
            "error": "Tesseract is not installed, or could not be found. "
            "Install it, or set TESSERACT_CMD to the full path of tesseract.exe.",
        }

    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = exe
        version = str(pytesseract.get_tesseract_version())
    except ImportError:
        return {
            "available": False,
            "path": exe,
            "version": "",
            "error": "pytesseract is not installed. Run: pip install -r requirements.txt",
        }
    except Exception as exc:
        return {"available": False, "path": exe, "version": "", "error": str(exc)}

    return {"available": True, "path": exe, "version": version, "error": ""}


def status() -> dict:
    """Return the cached OCR status, discovering it on first use."""
    global _state
    if _state is None:
        _state = _discover()
    return _state


def is_available() -> bool:
    return status()["available"]
