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

# --- Column detection -----------------------------------------------------
GUTTER_MIN_BLOCKS = 6          # too few blocks to judge a layout
GUTTER_MIN_BLOCK_WIDTH = 0.03  # ignore slivers when looking for the gap
GUTTER_MAX_SPAN_RATIO = 0.25   # share of blocks allowed to straddle the gutter
GUTTER_MIN_WIDTH = 0.015       # a narrower gap is word spacing, not a gutter
GUTTER_MIN_SIDE_RATIO = 0.15   # each column must hold this share of the text

IMAGE_MODES = ("extract", "none", "embed")


@dataclass
class ConversionResult:
    markdown_path: Path | None = None
    page_count: int = 0
    images_kept: int = 0
    image_report: dict = field(default_factory=dict)
    ocr_pages: list[int] = field(default_factory=list)
    ocr_skipped_pages: list[int] = field(default_factory=list)
    warning: str = ""
    tables_found: int = 0
    two_column_pages: int = 0
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


def _find_tables(page: fitz.Page, gutter: float | None) -> list:
    """Tables on a page. Ruled tables only, searched per column when there are two.

    Only the 'lines' strategy is used, because a drawn grid is real evidence of
    a table. PyMuPDF's whitespace strategy, which is meant to catch unruled
    tables, does not return the table on its own -- it returns the whole column
    with the prose above and below folded in -- so it cannot be used without
    corrupting the text. Unruled tables are therefore left as text; see the
    limitations in the README.

    Clipping to each column still matters: a ruled table inside one column of a
    two-column page is found more reliably when the other column is excluded.
    """
    found: list = []
    seen: list[fitz.Rect] = []

    if gutter is None:
        regions = [None]  # whole page
    else:
        regions = [
            fitz.Rect(page.rect.x0, page.rect.y0, gutter, page.rect.y1),
            fitz.Rect(gutter, page.rect.y0, page.rect.x1, page.rect.y1),
            None,  # and once page-wide, for a table that spans both columns
        ]

    for region in regions:
        try:
            tables = page.find_tables(strategy="lines").tables if region is None \
                else page.find_tables(clip=region, strategy="lines").tables
        except Exception:
            continue
        for table in tables:
            rect = fitz.Rect(table.bbox)
            # The same table surfaces from more than one pass.
            if any(rect.intersects(s) for s in seen):
                continue
            seen.append(rect)
            found.append(table)

    return found


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


def _page_gutter(page: fitz.Page) -> float | None:
    """The x of a two-column page's gutter, or None for a single column.

    Looks for a vertical band in the middle of the page that text does not
    cross. A few blocks may straddle it -- a full-width figure, a caption, a
    displayed equation -- so a small number of crossings is tolerated, and the
    narrowest such band wins.
    """
    width = page.rect.width
    if not width:
        return None

    try:
        data = page.get_text("dict")
    except Exception:
        return None

    blocks = [
        b["bbox"]
        for b in data.get("blocks", [])
        if b.get("type") == 0
        and b.get("bbox")
        and (b["bbox"][2] - b["bbox"][0]) > width * GUTTER_MIN_BLOCK_WIDTH
    ]
    if len(blocks) < GUTTER_MIN_BLOCKS:
        return None

    lo, hi = width * 0.35, width * 0.65
    max_spanning = max(1, int(len(blocks) * GUTTER_MAX_SPAN_RATIO))

    # Prefer the band crossed by fewest blocks, and among those the widest --
    # the gutter is the largest clear gap, not the first sliver found.
    best: tuple[int, float, float] | None = None
    run_start: float | None = None
    run_span = 0
    x = lo
    while x <= hi:
        crossing = sum(1 for b in blocks if b[0] < x < b[2])
        if crossing <= max_spanning:
            if run_start is None:
                run_start, run_span = x, crossing
            run_span = max(run_span, crossing)
            band = x - run_start
            if band > 0:
                # Fewer crossings wins; then a wider band.
                candidate = (run_span, -band, run_start + band / 2)
                if best is None or candidate < best:
                    best = candidate
        else:
            run_start = None
        x += 1.0

    if best is None:
        return None

    _, negative_band, centre = best
    band = -negative_band
    if band < width * GUTTER_MIN_WIDTH:
        return None

    # Blocks allowed to straddle the band widen it and pull the midpoint off
    # true. Re-centre on the real gap: the right edge of the text to its left,
    # and the left edge of the text to its right.
    left_edge = max((b[2] for b in blocks if b[2] <= centre), default=None)
    right_edge = min((b[0] for b in blocks if b[0] >= centre), default=None)
    if left_edge is not None and right_edge is not None and right_edge > left_edge:
        centre = (left_edge + right_edge) / 2

    # Both columns have to carry a real share of the text. Measure area rather
    # than block count: a column can be one tall block or twenty short ones.
    def area(bbox) -> float:
        return (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])

    left = sum(area(b) for b in blocks if b[2] <= centre)
    right = sum(area(b) for b in blocks if b[0] >= centre)
    if not left or not right:
        return None
    if min(left, right) / (left + right) < GUTTER_MIN_SIDE_RATIO:
        return None

    return centre


def _repeated_edge_lines(doc: fitz.Document, min_pages: int = 3) -> set[str]:
    """Find running headers and footers, so they are written once, not per page.

    Journal papers repeat a title strip and page number on every page. Over a
    14-page article that is a few hundred wasted tokens, and it interrupts the
    text mid-sentence. Same principle as the repeated-image filter: a line that
    appears near the top or bottom edge of most pages is furniture, not content.
    """
    if doc.page_count < min_pages:
        return set()

    counts: Counter = Counter()
    for page in doc:
        height = page.rect.height or 1.0
        try:
            data = page.get_text("dict")
        except Exception:
            continue

        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            bbox = block.get("bbox")
            if not bbox:
                continue

            # Only the top and bottom 8% of the page.
            if not (bbox[3] < height * 0.08 or bbox[1] > height * 0.92):
                continue

            text = " ".join(
                "".join(s.get("text", "") for s in line.get("spans", []))
                for line in block.get("lines", [])
            ).strip()
            if text:
                counts[text] += 1

    threshold = max(min_pages, int(doc.page_count * 0.5))
    repeated = {text for text, n in counts.items() if n >= threshold}

    # Page numbers differ per page, so they never repeat verbatim. Catch them
    # by shape instead: a short edge block that is mostly digits.
    for text, n in counts.items():
        if n >= threshold or len(text) > 12:
            continue
        digits = sum(c.isdigit() for c in text)
        if digits and digits >= len(text.replace(" ", "")) * 0.6:
            repeated.add(text)

    return repeated


def _blocks_to_markdown(
    page: fitz.Page,
    body_size: float,
    skip_rects: list[fitz.Rect] | None = None,
    drop_lines: set[str] | None = None,
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

        # Drop running headers, footers and page numbers.
        if drop_lines:
            block_text = " ".join(
                "".join(s.get("text", "") for s in line.get("spans", []))
                for line in block.get("lines", [])
            ).strip()
            if block_text in drop_lines:
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

    # A heading that wraps onto several lines arrives as several headings of the
    # same level; join them back into one.
    merged: list[str] = []
    for part in parts:
        if (
            part.startswith("#")
            and merged
            and merged[-1].startswith("#")
            and part.split(" ", 1)[0] == merged[-1].split(" ", 1)[0]
        ):
            merged[-1] = merged[-1].rstrip() + " " + part.split(" ", 1)[1]
        else:
            merged.append(part)

    # Join consecutive plain lines into paragraphs, keep headings on their own.
    out: list[str] = []
    buffer: list[str] = []
    for part in merged:
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
    result = ConversionResult()

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


        result.images_kept = len(kept)
        result.image_report = report.as_dict()

        by_page: dict[int, list[ExtractedImage]] = {}
        for img in kept:
            by_page.setdefault(img.page_number, []).append(img)

        # --- Pages --------------------------------------------------------
        chunks: list[str] = []
        title_written = False
        drop_lines = _repeated_edge_lines(doc)

        for page_number, page in enumerate(doc, start=1):
            # Find tables first: their regions are excluded from the text pass
            # so the same content is not emitted twice.
            gutter = _page_gutter(page)
            if gutter is not None:
                result.two_column_pages += 1

            page_tables: list[str] = []
            table_rects: list[fitz.Rect] = []
            if detect_tables:
                try:
                    for table in _find_tables(page, gutter):
                        md_table = _table_to_markdown(table)
                        if md_table:
                            page_tables.append(md_table)
                            table_rects.append(fitz.Rect(table.bbox))
                            result.tables_found += 1
                except Exception:
                    pass  # Table detection is best-effort.

            text = _blocks_to_markdown(page, body_size, table_rects, drop_lines)

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
                    # Papers often lead with a metadata strip before the title,
                    # so look for an H1 anywhere on this page, not just at the
                    # start, before falling back to the filename.
                    if not re.search(r"^# ", body, re.M):
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
