"""Command-line interface, for scripting and batch runs without the UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .convert import IMAGE_MODES, convert_pdf, find_pdfs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdftomd",
        description="Convert PDFs to Markdown for cheaper AI context.",
    )
    parser.add_argument(
        "inputs", nargs="+", type=Path, help="PDF files and/or directories of PDFs"
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("output"), help="output directory"
    )
    parser.add_argument(
        "--images",
        choices=IMAGE_MODES,
        default="extract",
        help="extract: save to a folder and link (default); "
        "none: strip images; embed: inline as base64",
    )
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR on scanned pages")
    parser.add_argument("--no-tables", action="store_true", help="skip table detection")
    parser.add_argument(
        "--no-recursive", action="store_true", help="do not descend into subfolders"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    pdfs = find_pdfs(args.inputs, recursive=not args.no_recursive)
    if not pdfs:
        print("No PDF files found.", file=sys.stderr)
        return 1

    print(f"Converting {len(pdfs)} file(s) to {args.output}\n")
    failed = 0

    for i, pdf in enumerate(pdfs, start=1):
        result = convert_pdf(
            pdf,
            args.output,
            image_mode=args.images,
            ocr_enabled=not args.no_ocr,
            detect_tables=not args.no_tables,
        )

        if result.ok:
            bits = [f"{result.page_count}p", f"{result.chars:,} chars"]
            if result.images_kept:
                dropped = result.image_report.get("dropped", 0)
                bits.append(f"{result.images_kept} images (+{dropped} filtered)")
            if result.tables_found:
                bits.append(f"{result.tables_found} tables")
            if result.ocr_pages:
                bits.append(f"OCR on {len(result.ocr_pages)} pages")
            print(f"  [{i}/{len(pdfs)}] {pdf.name} -> {', '.join(bits)}")
            if result.warning:
                print(f"        warning: {result.warning}")
        else:
            failed += 1
            print(f"  [{i}/{len(pdfs)}] {pdf.name} -> FAILED: {result.error}", file=sys.stderr)

    print(f"\nDone. {len(pdfs) - failed} succeeded, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
