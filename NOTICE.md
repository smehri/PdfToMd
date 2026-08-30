# Third-party notices

PdfToMd is licensed under the GNU Affero General Public License v3.0 — see
[LICENSE](LICENSE). This file records the components it builds on and the terms
they carry.

## Why this project is AGPL-3.0

PdfToMd uses **PyMuPDF** for PDF parsing, which is licensed under AGPL-3.0.
That license is copyleft: a work that links against it must be released under
AGPL-3.0 as well. PdfToMd therefore carries the same license, and so must any
fork or derivative.

The practical consequence, which AGPL adds over ordinary GPL: **if you run a
modified version as a network service, you must offer its source to the people
using that service.** Running it locally for yourself carries no such
obligation — using the tool and converting your own documents is unrestricted.

If you need a permissively licensed build, PyMuPDF can be replaced with
[pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (BSD-3-Clause /
Apache-2.0), at the cost of the table detection that PyMuPDF provides.
PyMuPDF is also available under a commercial license from Artifex.

## Python dependencies

| Package | Version | License | Used for |
|---|---|---|---|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | 1.24.10 | **AGPL-3.0** | PDF parsing, text/image extraction, page rendering, table detection |
| [PyMuPDFb](https://github.com/pymupdf/PyMuPDF) | 1.24.10 | **AGPL-3.0** | MuPDF binary support library for PyMuPDF |
| [Pillow](https://github.com/python-pillow/Pillow) | 10.4.0 | HPND | Image inspection for the filtering heuristics |
| [pytesseract](https://github.com/madmaze/pytesseract) | 0.3.13 | Apache-2.0 | Tesseract wrapper used for OCR |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.115.0 | MIT | Web framework behind the local UI |
| [Starlette](https://github.com/encode/starlette) | 0.38.6 | BSD-3-Clause | ASGI toolkit underlying FastAPI |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.13.5 | MIT | Request/response models |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.30.6 | BSD-3-Clause | ASGI server |
| [python-multipart](https://github.com/Kludex/python-multipart) | 0.0.9 | Apache-2.0 | Multipart parsing for file uploads |

`uvicorn[standard]` also pulls in httptools, uvloop, watchfiles, websockets,
python-dotenv and PyYAML — all MIT or BSD-3-Clause.

## External programs

| Program | License | Notes |
|---|---|---|
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | Optional. Invoked as a separate process, not linked. Only used for pages with no text layer. |

Tesseract is not bundled with this project and is not required to run it.
Without it, PDFs still convert; pages that are scanned images carry a warning
instead of OCR text.

## Fonts and assets

The icon in `assets/` and the interface in `pdftomd/static/` were produced for
this project and are covered by its AGPL-3.0 license. The UI uses the operating
system's own font stack and bundles no font files. It loads nothing from a CDN
and makes no network requests beyond the local server.

## Your documents

PdfToMd runs entirely on your machine. PDFs are read locally, Markdown is
written locally, and nothing is uploaded anywhere. The local server binds to
`127.0.0.1`, so it is not reachable from other machines on your network.
