# Changelog

Notable changes to PdfToMd. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Running header and footer removal.** A line repeated near the top or bottom
  edge of most pages is furniture, not content — the same principle already
  applied to repeated images. On the example paper this removed 13 copies of the
  journal's title strip.
- **`examples/`** — a real 14-page open-access paper converted end to end, with
  measured token figures and an honest account of what the converter handles
  badly.

### Fixed

- A title that wraps onto two lines produced two `# H1` headings instead of one.
- The filename was used as the title even when the document had its own, if a
  metadata strip preceded it — papers led with `# paper` above their real title.

## [0.1.0] — 2026-08-30

First public release.

### Added

- **PDF to Markdown conversion** with heading levels inferred from font size,
  paragraphs rejoined from text blocks, and per-page ordering.
- **Three image modes.** `extract` (default) writes images to a sibling folder
  and links them, so a figure costs ~8 tokens instead of ~1,000; `none` strips
  them; `embed` inlines base64 for a self-contained file.
- **Image filtering.** Icons, divider rules, low-colour images, sub-1%-area
  images, exact duplicates, and anything repeated across most pages are dropped
  before writing. Each result reports how many went and why.
- **Table detection.** Tables are emitted as Markdown pipes rather than left as
  images, and their page regions are excluded from the text pass so the content
  is not written twice.
- **OCR for scanned pages.** Pages with almost no text are rendered at 300 DPI
  and passed to Tesseract. Tesseract is located automatically, including the
  Windows install path that is not on `PATH`. When it is unavailable the file
  still converts and carries a warning naming the affected pages.
- **Local web UI** — drag and drop, folder scanning, live per-file progress over
  server-sent events, result cards with page/token/image/table counts, Markdown
  preview, download, and a light/dark theme that follows the system.
- **Command-line interface** for batch and scripted runs.
- **Windows desktop launcher.** `PdfToMd.vbs` starts the server through
  `pythonw.exe` with no console window; `scripts\install_shortcut.ps1` creates
  the desktop and Start Menu shortcuts.

### Fixed

Found while building, each of which failed quietly rather than loudly:

- OCR silently did nothing when Tesseract was installed but not on `PATH`,
  producing empty Markdown that looked like a successful conversion.
- Table content was written twice — once as garbled text, once as a table —
  which doubled tokens on exactly the content the tool exists to compress.
- The preview overlay rendered on page load, dimming the interface, because a
  class rule beat the `hidden` attribute.
- A document with its own title got two `# H1` headings, one from the filename.
- The server crashed on startup under `pythonw.exe`: with no console,
  `sys.stdout` is `None` and uvicorn's log formatter calls `.isatty()` on it.
- Launching a second instance crashed on the bound port instead of opening the
  running one, and the browser could open before the server was listening.

[Unreleased]: https://github.com/smehri/PdfToMd/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/smehri/PdfToMd/releases/tag/v0.1.0
