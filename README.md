# PdfToMd

Convert PDFs to Markdown so they cost fewer tokens as AI context.

A local web UI plus a CLI. Point it at a PDF, a set of PDFs, or a folder, and it
writes clean `.md` files — with images filtered, tables converted to Markdown
pipes, and scanned pages read by OCR.

![UI](docs/screenshot.png)

## Why the output is smaller

| In the PDF | In the Markdown | Tokens |
|---|---|---|
| A page of text | The same text, no layout | roughly the same |
| A table as a bitmap | Markdown pipes | ~1500 → ~200 |
| A chart or figure | `![](images/page04-01.png)` | ~1000 → ~8 |
| A logo on every page | dropped | ~750 → 0 |

The image link is the important part: a reference costs about 8 tokens, so
nothing is paid for upfront, and the file is still there to attach to a
conversation when a question actually needs it.

## Install

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

OCR is optional and only used for scanned pages. It needs Tesseract:

```powershell
winget install --id UB-Mannheim.TesseractOCR --source winget   # Windows
# brew install tesseract                                       # macOS
# sudo apt install tesseract-ocr                               # Debian/Ubuntu
```

The app finds Tesseract automatically in the usual install locations. If yours
is somewhere else, set `TESSERACT_CMD` to the full path of the binary. The UI
shows whether OCR is ready before you convert.

## Run the web UI

Either double-click the icon (see below), or from a terminal:

```bash
python -m pdftomd
```

That starts a local server on <http://127.0.0.1:8765> and opens a browser tab.
Drag PDFs in, or type a folder path and press **Scan**. Nothing leaves the
machine.

Stop it with Ctrl+C, or by closing the `pythonw.exe` process when it was started
from the icon.

## Desktop icon (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_shortcut.ps1
```

That puts a **PdfToMd** shortcut on the desktop. Add `-StartMenu` to also list it
in the Start Menu, or `-Remove` to take the shortcuts away again.

Double-clicking it starts the server with no console window and opens the
browser once the server is actually listening. Launching it a second time does
not fail on the bound port — it just opens the tab again. If startup does fail,
a message box points at `%TEMP%\pdftomd-error.log`.

The shortcut runs [`PdfToMd.vbs`](PdfToMd.vbs), which resolves paths relative to
itself, so the project folder can be moved or renamed — just re-run the script
above to repoint the shortcut.

## Run the CLI

```bash
# One file
python -m pdftomd.cli report.pdf -o output

# Several files and a whole folder
python -m pdftomd.cli a.pdf b.pdf ./papers -o output

# Text only, no images
python -m pdftomd.cli ./papers -o output --images none
```

| Flag | Meaning |
|---|---|
| `-o, --output` | Output directory (default `output`) |
| `--images extract` | Save images to a folder and link them — **default** |
| `--images none` | Strip images; smallest output |
| `--images embed` | Inline as base64; one self-contained file, much larger |
| `--no-ocr` | Skip OCR on scanned pages |
| `--no-tables` | Skip table detection |
| `--no-recursive` | Do not descend into subfolders |

## Output layout

```
output/
  quarterly-report.md
  quarterly-report-images/
    page001-01.png
    page004-02.png
```

Image links are relative, so the `.md` and its image folder can be moved
together and the links keep working.

## How images are filtered

Most images embedded in a PDF are decoration. These are dropped:

- smaller than 100×100 px, or under 5 KB — icons and bullet glyphs
- aspect ratio beyond 10:1 — divider rules
- under 1% of the page area
- 1-bit or 2-colour — rules and separators
- the same image on more than half the pages — logos and watermarks
- exact duplicates of an image already kept

Each result says how many were dropped, so nothing disappears silently.

Note that vector charts are not embedded rasters and are not extracted; they
stay part of the page's drawing instructions.

## Scanned PDFs

A page with no text layer would otherwise convert to nothing. Pages under 50
characters of extracted text are rendered at 300 DPI and passed to OCR. If OCR
is unavailable, the file still converts and carries a warning saying which pages
were affected — rather than quietly producing a blank document.

## Layout

```
PdfToMd.vbs    double-click launcher (no console window)
assets/        app.ico
scripts/
  install_shortcut.ps1   creates the desktop / Start Menu shortcut
  make_test_pdfs.py      generates sample PDFs to try it on
pdftomd/
  convert.py   PDF -> Markdown: text, headings, tables, OCR
  images.py    extraction and the filtering heuristics
  ocr.py       Tesseract discovery
  server.py    FastAPI app and the progress stream
  cli.py       command-line interface
  static/      the web UI
```
