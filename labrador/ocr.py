"""OCR for images and scanned PDF pages.

macOS: Apple Vision through `ocrmac` (on-device, fast, ~25 languages).
Elsewhere: Tesseract through `pytesseract` if the binary is installed.
If neither is available OCR quietly returns "" and images are still found by what they show.
"""

from __future__ import annotations

import shutil
import sys
from functools import lru_cache

from PIL import Image


@lru_cache(maxsize=1)
def backend() -> str:
    if sys.platform == "darwin":
        try:
            import ocrmac  # noqa: F401
            return "vision"
        except ImportError:
            pass
    try:
        import pytesseract  # noqa: F401
        if shutil.which("tesseract"):
            return "tesseract"
    except ImportError:
        pass
    return "none"


def ocr_image(img: Image.Image) -> str:
    b = backend()
    try:
        if b == "vision":
            from ocrmac import ocrmac
            # Each annotation is (text, confidence, [x, y, w, h]) with a bottom-left origin.
            ann = ocrmac.OCR(img.convert("RGB"), recognition_level="accurate").recognize()
            ann = sorted(ann, key=lambda a: (-round(a[2][1], 2), a[2][0]))
            return "\n".join(a[0] for a in ann if a[1] >= 0.3).strip()
        if b == "tesseract":
            import pytesseract
            return pytesseract.image_to_string(img.convert("RGB")).strip()
    except Exception:
        return ""
    return ""


def useful(text: str, min_chars: int = 12) -> bool:
    """OCR on photos often yields a few junk glyphs; keep only real text."""
    letters = sum(ch.isalnum() for ch in text)
    return letters >= min_chars
