# Contributing

Thanks for taking a look. Issues and pull requests are both welcome.

## Setting up

```bash
git clone https://github.com/smehri/PdfToMd.git
cd PdfToMd
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt
python scripts/make_test_pdfs.py
```

That last command creates `test-pdfs/` with three fixtures — a text document
with an embedded figure and a decorative icon, one with a ruled table, and a
scanned page with no text layer. Between them they cover every code path.

## Checking a change

There is no test suite yet. Run the converter over the fixtures and read the
output:

```bash
python -m pdftomd.cli test-pdfs -o output
cat output/sample-text.md output/sample-table.md output/sample-scan.md
```

What each fixture should show:

| Fixture | Expected |
|---|---|
| `sample-text` | one `# Quarterly Report` heading, the 16×16 icon filtered out, the figure linked |
| `sample-table` | a Markdown pipe table, and the same rows **not** repeated as loose text |
| `sample-scan` | OCR text (`SCANNED INVOICE 4471`), or a warning if Tesseract is missing |

Then check the UI end to end — `python -m pdftomd`, scan the `test-pdfs`
folder, convert, open a preview.

CI runs the same conversion on every push and fails if a file errors or an
expected string goes missing.

## House style

The code aims to read like one person wrote it:

- Comments explain **why**, not what. If a threshold or a workaround is not
  obvious, say what would go wrong without it.
- Failures should be visible. The OCR path is the model here: when Tesseract is
  missing, the file still converts and says which pages were affected, rather
  than silently producing a blank document.
- No frontend build step. The UI is plain HTML, CSS and JavaScript, served as
  static files, with no framework and no CDN.
- Keep it offline. Nothing should make a network request.

## Areas that would help

- **Vector graphics.** Charts drawn as PDF instructions are not extracted.
  Rendering the page region to PNG would fix this and is the most-wanted gap.
- **A real test suite.** `pytest` over the fixtures, asserting the table above.
- **Better token estimates.** The current figure is `chars / 4`, which
  under-counts tables and non-Latin scripts. A real tokenizer would be exact.
- **Multi-column layouts.** Text is read in block order, which interleaves
  columns on academic papers.
- **Non-English OCR.** Tesseract takes a `lang` parameter that is not yet
  exposed.

## Pull requests

Keep them focused — one change per PR. Say what you tested; if it touches
conversion, paste the before/after Markdown for the affected fixture. New
behaviour that changes output should come with a note in `CHANGELOG.md`.

## License

Contributions are accepted under [AGPL-3.0](LICENSE), the project's license.
See [NOTICE.md](NOTICE.md) for why it is AGPL and what that means in practice.
