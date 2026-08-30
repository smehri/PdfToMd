# PdfToMd -- convert PDFs to Markdown for cheaper AI context.
# Copyright (C) 2026 Saeed Mehri
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. See <https://www.gnu.org/licenses/> for details.

"""PDF to Markdown conversion.

Strategy for images is 'extract and link': images are written to a sibling
folder and referenced from the Markdown as ![](images/...). A reference costs
roughly 8 tokens where an inlined image costs 750-1600, so nothing is paid for
upfront and nothing is lost -- a specific figure can be attached to a
conversation later if a question needs it.
"""

from __future__ import annotations

import base64
import io
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from . import ocr as ocr_status
from .images import ExtractedImage, ImageReport, extract_images, filter_images

# A page with almost no text but a large image is a scan, not a blank page.
SCAN_TEXT_THRESHOLD = 50

IMAGE_MODES = ("extract", "none", "embed")


@dataclass
class ConversionResult:
    source: Path
    markdown_path: Path | None = None
    image_dir: Path | None = None
    page_count: int = 0
    images_kept: int = 0
    image_report: dict = field(default_factory=dict)
    ocr_pages: list[int] = field(default_factory=list)
    ocr_skipped_pages: list[int] = field(default_factory=list)
    warning: str = ""
    tables_found: int = 0
    chars: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def slugify(name: str) -> str:
    """Filesystem-safe stem, so output names survive odd PDF filenames."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\s-]", "", name).strip()
    name = re.sub(r"[\s_-]+", "-", name)
    return name.lower() or "document"


def find_pdfs(paths: list[Path], recursive: bool = True) -> list[Path]:
    """Expand a mix of files and directories into a sorted list of PDFs."""
    found: list[Path] = []
    for p in paths:
        if p.is_dir():
            found.extend(p.rglob("*.pdf") if recursive else p.glob("*.pdf"))
        elif p.suffix.lower() == ".pdf":
            found.append(p)
    # Deduplicate while keeping a stable order.
    return sorted({f.resolve() for f in found})


def _ocr_page(page: fitz.Page) -> str:
    """Render a page and OCR it. Returns an empty string if OCR is unavailable."""
    if not ocr_status.is_available():
        return ""

    try:
        import pytesseract
        from PIL import Image

        # 300 DPI renders small print legibly for the OCR engine.
        pix = page.get_pixmap(dpi=300)
        with Image.open(io.BytesIO(pix.tobytes("png"))) as im:
            return pytesseract.image_to_string(im).strip()
    except Exception:
        return ""


def _table_to_markdown(table) -> str:
    """Render an extracted table as Markdown pipes.

    A table as an image costs ~1500 tokens; the same table as pipes costs ~200
    and is actually queryable, so this is the single biggest token win.
    """
    try:
        rows = table.extract()
    except Exception:
        return ""

    cleaned = [
        [str(c).replace("\n", " ").replace("|", "\\|").strip() if c else "" for c in row]
        for row in rows
        if any(c for c in row)
    ]
    if len(cleaned) < 2:
        return ""

    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]

    header, *body = cleaned
    out = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(out)


def _body_font_size(doc: fitz.Document) -> float:
    """The most common span size across the first pages is the body text size."""
    sizes: Counter = Counter()
    for page in list(doc)[:5]:
        try:
            data = page.get_text("dict")
        except Exception:
            continue
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        sizes[round(span.get("size", 10), 1)] += len(text)

    return sizes.most_common(1)[0][0] if sizes else 10.0


def _blocks_to_markdown(
    page: fitz.Page, body_size: float, skip_rects: list[fitz.Rect] | None = None
) -> str:
    """Turn a page's text blocks into Markdown, inferring headings from size.

    Text inside `skip_rects` is left out: those areas are rendered separately as
    Markdown tables, and emitting them twice would duplicate the content.
    """
    try:
        data = page.get_text("dict")
    except Exception:
        return page.get_text().strip()

    skip_rects = skip_rects or []

    parts: list[str] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 = text
            continue

        # Drop the block if its centre sits inside a table region.
        bbox = block.get("bbox")
        if bbox and skip_rects:
            centre = fitz.Point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
            if any(centre in r for r in skip_rects):
                continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue

            size = max((s.get("size", body_size) for s in spans), default=body_size)
            bold = any("bold" in s.get("font", "").lower() for s in spans)

            # Headings run larger than body text; map the jump to a level.
            if size >= body_size * 1.6:
                parts.append(f"# {text}")
            elif size >= body_size * 1.3:
                parts.append(f"## {text}")
            elif size >= body_size * 1.15 or (bold and len(text) < 80):
                parts.append(f"### {text}")
            else:
                parts.append(text)

    # Join consecutive plain lines into paragraphs, keep headings on their own.
    out: list[str] = []
    buffer: list[str] = []
    for part in parts:
        if part.startswith("#"):
            if buffer:
                out.append(" ".join(buffer))
                buffer = []
            out.append(part)
        else:
            buffer.append(part)
    if buffer:
        out.append(" ".join(buffer))

    return "\n\n".join(out)


def convert_pdf(
    pdf_path: Path,
    output_dir: Path,
    image_mode: str = "extract",
    ocr_enabled: bool = True,
    detect_tables: bool = True,
) -> ConversionResult:
    """Convert one PDF to Markdown. Never raises; errors land on the result."""
    result = ConversionResult(source=pdf_path)

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        result.error = f"Could not open PDF: {exc}"
        return result

    try:
        stem = slugify(pdf_path.stem)
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{stem}.md"

        result.page_count = doc.page_count
        body_size = _body_font_size(doc)

        # --- Images -------------------------------------------------------
        kept: list[ExtractedImage] = []
        report = ImageReport()
        image_dir = output_dir / f"{stem}-images"

        if image_mode != "none":
            all_images = extract_images(doc)
            kept, report = filter_images(all_images, doc.page_count)

            if kept and image_mode == "extract":
                if image_dir.exists():
                    shutil.rmtree(image_dir)
                image_dir.mkdir(parents=True, exist_ok=True)

                for img in kept:
                    img.filename = f"page{img.page_number:03d}-{img.index:02d}.{img.ext}"
                    (image_dir / img.filename).write_bytes(img.data)

                result.image_dir = image_dir

        result.images_kept = len(kept)
        result.image_report = report.as_dict()

        by_page: dict[int, list[ExtractedImage]] = {}
        for img in kept:
            by_page.setdefault(img.page_number, []).append(img)

        # --- Pages --------------------------------------------------------
        chunks: list[str] = []
        title_written = False

        for page_number, page in enumerate(doc, start=1):
            # Find tables first: their regions are excluded from the text pass
            # so the same content is not emitted twice.
            page_tables: list[str] = []
            table_rects: list[fitz.Rect] = []
            if detect_tables:
                try:
                    for table in page.find_tables().tables:
                        md_table = _table_to_markdown(table)
                        if md_table:
                            page_tables.append(md_table)
                            table_rects.append(fitz.Rect(table.bbox))
                            result.tables_found += 1
                except Exception:
                    pass  # Table detection is best-effort.

            text = _blocks_to_markdown(page, body_size, table_rects)

            # No text layer means a scan -- without OCR the page comes out blank.
            if ocr_enabled and len(text.strip()) < SCAN_TEXT_THRESHOLD:
                if ocr_status.is_available():
                    ocr_text = _ocr_page(page)
                    if len(ocr_text) > len(text):
                        text = ocr_text
                        result.ocr_pages.append(page_number)
                else:
                    # Record it: a blank page here means a missing engine, not
                    # an empty document, and the user needs to be told which.
                    result.ocr_skipped_pages.append(page_number)

            page_parts: list[str] = []
            if text.strip():
                body = text.strip()

                # Use the filename as the title only when the document does not
                # open with a heading of its own -- otherwise the file gets two H1s.
                if not title_written:
                    title_written = True
                    if not body.startswith("# "):
                        page_parts.append(f"# {pdf_path.stem}")

                page_parts.append(body)

            page_parts.extend(page_tables)

            for img in by_page.get(page_number, []):
                if image_mode == "extract":
                    rel = f"{image_dir.name}/{img.filename}"
                    page_parts.append(
                        f"![Page {img.page_number} figure {img.index}]({rel})"
                    )
                elif image_mode == "embed":
                    b64 = base64.b64encode(img.data).decode()
                    page_parts.append(
                        f"![Page {img.page_number} figure {img.index}]"
                        f"(data:image/{img.ext};base64,{b64})"
                    )

            if page_parts:
                chunks.append("\n\n".join(page_parts))
                chunks.append("")

        if result.ocr_skipped_pages:
            n = len(result.ocr_skipped_pages)
            result.warning = (
                f"{n} page(s) have no text layer and OCR is unavailable, so they "
                f"converted to images only. {ocr_status.status()['error']}"
            )

        markdown = "\n".join(chunks).strip() + "\n"
        markdown = re.sub(r"\n{4,}", "\n\n\n", markdown)

        md_path.write_text(markdown, encoding="utf-8")
        result.markdown_path = md_path
        result.chars = len(markdown)

    except Exception as exc:
        result.error = f"Conversion failed: {exc}"
    finally:
        doc.close()

    return result
