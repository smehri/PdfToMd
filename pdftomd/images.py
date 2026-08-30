# PdfToMd -- convert PDFs to Markdown for cheaper AI context.
# Copyright (C) 2026 Saeed Mehri
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. See <https://www.gnu.org/licenses/> for details.

"""Image extraction and filtering.

Most images embedded in a PDF are decoration: logos, bullet glyphs, header
rules, background watermarks. Keeping them produces a folder of hundreds of
junk files and clutters the Markdown. The heuristics here drop the noise while
keeping charts, diagrams, screenshots and photos.
"""

from __future__ import annotations

import hashlib
import io
from collections import Counter
from dataclasses import dataclass, field

import fitz  # PyMuPDF
from PIL import Image

# --- Filtering thresholds -------------------------------------------------
MIN_WIDTH = 100          # px; below this it is an icon or glyph
MIN_HEIGHT = 100
MIN_BYTES = 5 * 1024     # 5 KB; tiny files are never real figures
MAX_ASPECT = 10.0        # wider/taller than 10:1 is a divider rule
MIN_PAGE_AREA_RATIO = 0.01   # under 1% of the page is decoration
REPEAT_PAGE_RATIO = 0.5      # on >50% of pages => logo / watermark


@dataclass
class ExtractedImage:
    """One image pulled out of the PDF, with the metadata used to judge it."""

    page_number: int
    index: int
    data: bytes
    ext: str
    width: int
    height: int
    digest: str
    page_area_ratio: float
    kept: bool = True
    reason: str = ""
    filename: str = ""

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@dataclass
class ImageReport:
    """Summary of what was kept and why the rest was dropped."""

    total: int = 0
    kept: int = 0
    dropped_by_reason: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "kept": self.kept,
            "dropped": self.total - self.kept,
            "dropped_by_reason": dict(self.dropped_by_reason),
        }


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _is_low_colour(data: bytes) -> bool:
    """True for 1-bit or 2-colour images, which are almost always rules."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.mode == "1":
                return True
            colours = im.convert("RGB").getcolors(maxcolors=4)
            return colours is not None and len(colours) <= 2
    except Exception:
        # Unreadable images are handled by the size checks instead.
        return False


def extract_images(doc: fitz.Document) -> list[ExtractedImage]:
    """Pull every embedded raster image out of the document."""
    out: list[ExtractedImage] = []

    for page_number, page in enumerate(doc, start=1):
        page_area = abs(page.rect.width * page.rect.height) or 1.0

        for index, info in enumerate(page.get_images(full=True), start=1):
            xref = info[0]
            try:
                raw = doc.extract_image(xref)
            except Exception:
                continue

            data = raw["image"]
            width = raw.get("width", 0)
            height = raw.get("height", 0)

            # Where the image actually sits on the page, for the area test.
            try:
                rects = page.get_image_rects(xref)
                drawn = max((abs(r.width * r.height) for r in rects), default=0.0)
            except Exception:
                drawn = 0.0

            out.append(
                ExtractedImage(
                    page_number=page_number,
                    index=index,
                    data=data,
                    ext=raw.get("ext", "png"),
                    width=width,
                    height=height,
                    digest=_digest(data),
                    page_area_ratio=drawn / page_area if drawn else 0.0,
                )
            )

    return out


def filter_images(
    images: list[ExtractedImage], page_count: int
) -> tuple[list[ExtractedImage], ImageReport]:
    """Mark decoration as dropped. Returns the kept images and a report."""
    report = ImageReport(total=len(images))

    # A digest appearing on many distinct pages is a logo or watermark.
    pages_per_digest: dict[str, set[int]] = {}
    for img in images:
        pages_per_digest.setdefault(img.digest, set()).add(img.page_number)

    repeat_threshold = max(2, int(page_count * REPEAT_PAGE_RATIO))
    seen_digests: set[str] = set()

    for img in images:
        if len(pages_per_digest[img.digest]) >= repeat_threshold:
            img.kept, img.reason = False, "repeated on most pages (logo/watermark)"
        elif img.width < MIN_WIDTH or img.height < MIN_HEIGHT:
            img.kept, img.reason = False, "too small (icon/glyph)"
        elif img.size_bytes < MIN_BYTES:
            img.kept, img.reason = False, "file too small"
        elif img.height and max(img.width / img.height, img.height / img.width) > MAX_ASPECT:
            img.kept, img.reason = False, "extreme aspect ratio (divider rule)"
        elif 0 < img.page_area_ratio < MIN_PAGE_AREA_RATIO:
            img.kept, img.reason = False, "covers under 1% of the page"
        elif _is_low_colour(img.data):
            img.kept, img.reason = False, "1-bit or 2-colour (rule/separator)"
        elif img.digest in seen_digests:
            img.kept, img.reason = False, "duplicate of an earlier image"

        if img.kept:
            seen_digests.add(img.digest)
            report.kept += 1
        else:
            report.dropped_by_reason[img.reason] += 1

    return [i for i in images if i.kept], report
