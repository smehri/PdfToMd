"""Local web UI for PDF to Markdown conversion."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import uuid
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import ocr as ocr_status
from .convert import convert_pdf, find_pdfs

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_OUTPUT = Path.cwd() / "output"

app = FastAPI(title="PdfToMd")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Uploaded files live here until the process exits.
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "pdftomd-uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# Job id -> the conversion settings, handed from POST /scan to GET /convert.
JOBS: dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/status")
async def status() -> JSONResponse:
    """Tell the UI whether OCR is usable, so it can warn before a run."""
    return JSONResponse({"ocr": ocr_status.status()})


@app.post("/api/scan")
async def scan(payload: dict) -> JSONResponse:
    """Resolve a typed path (file or folder) into a list of PDFs."""
    raw = (payload.get("path") or "").strip().strip('"')
    if not raw:
        return JSONResponse({"error": "Enter a path to a PDF or a folder."}, status_code=400)

    target = Path(raw).expanduser()
    if not target.exists():
        return JSONResponse({"error": f"Path not found: {target}"}, status_code=400)

    pdfs = find_pdfs([target], recursive=bool(payload.get("recursive", True)))
    if not pdfs:
        return JSONResponse({"error": "No PDF files found there."}, status_code=400)

    return JSONResponse(
        {
            "files": [
                {"path": str(p), "name": p.name, "size": p.stat().st_size} for p in pdfs
            ],
            "default_output": str(
                (target if target.is_dir() else target.parent) / "markdown"
            ),
        }
    )


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)) -> JSONResponse:
    """Accept drag-and-dropped PDFs and stage them on disk."""
    batch = UPLOAD_ROOT / uuid.uuid4().hex[:12]
    batch.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        if not (f.filename or "").lower().endswith(".pdf"):
            continue
        dest = batch / Path(f.filename).name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append({"path": str(dest), "name": dest.name, "size": dest.stat().st_size})

    if not saved:
        return JSONResponse({"error": "No PDF files in that drop."}, status_code=400)

    return JSONResponse({"files": saved, "default_output": str(DEFAULT_OUTPUT)})


@app.post("/api/job")
async def create_job(payload: dict) -> JSONResponse:
    """Register a conversion so the browser can stream its progress."""
    files = [Path(p) for p in payload.get("files", [])]
    if not files:
        return JSONResponse({"error": "No files selected."}, status_code=400)

    output = Path((payload.get("output") or "").strip().strip('"') or DEFAULT_OUTPUT)
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "files": files,
        "output": output.expanduser(),
        "image_mode": payload.get("image_mode", "extract"),
        "ocr": bool(payload.get("ocr", True)),
        "tables": bool(payload.get("tables", True)),
    }
    return JSONResponse({"job_id": job_id})


@app.get("/api/convert/{job_id}")
async def convert_stream(job_id: str) -> StreamingResponse:
    """Run the conversion, streaming one server-sent event per file."""
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "Unknown job."}, status_code=404)

    async def events():
        files: list[Path] = job["files"]
        total = len(files)
        done = 0
        summary = {"ok": 0, "failed": 0, "chars": 0, "images": 0, "tables": 0, "ocr": 0}

        yield _sse({"type": "start", "total": total})

        for pdf in files:
            yield _sse({"type": "file_start", "name": pdf.name, "index": done})

            # Conversion is CPU-bound; keep the event loop free for the stream.
            result = await asyncio.to_thread(
                convert_pdf,
                pdf,
                job["output"],
                job["image_mode"],
                job["ocr"],
                job["tables"],
            )
            done += 1

            if result.ok:
                summary["ok"] += 1
                summary["chars"] += result.chars
                summary["images"] += result.images_kept
                summary["tables"] += result.tables_found
                summary["ocr"] += len(result.ocr_pages)
            else:
                summary["failed"] += 1

            yield _sse(
                {
                    "type": "file_done",
                    "index": done,
                    "total": total,
                    "name": pdf.name,
                    "ok": result.ok,
                    "error": result.error,
                    "pages": result.page_count,
                    "chars": result.chars,
                    "images_kept": result.images_kept,
                    "image_report": result.image_report,
                    "tables": result.tables_found,
                    "ocr_pages": result.ocr_pages,
                    "warning": result.warning,
                    "markdown_path": str(result.markdown_path or ""),
                }
            )

        yield _sse({"type": "complete", "summary": summary, "output": str(job["output"])})
        JOBS.pop(job_id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/preview")
async def preview(path: str) -> JSONResponse:
    """Return the first slice of a converted file for the results panel."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".md":
        return JSONResponse({"error": "Not found."}, status_code=404)

    text = p.read_text(encoding="utf-8")
    return JSONResponse(
        {"text": text[:20000], "truncated": len(text) > 20000, "chars": len(text)}
    )


@app.get("/api/download", response_model=None)
async def download(path: str) -> FileResponse | JSONResponse:
    p = Path(path)
    if not p.exists():
        return JSONResponse({"error": "Not found."}, status_code=404)
    return FileResponse(p, filename=p.name, media_type="text/markdown")


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def main() -> None:
    import uvicorn

    host, port = "127.0.0.1", 8765
    url = f"http://{host}:{port}"
    print(f"\n  PdfToMd running at {url}\n  Press Ctrl+C to stop.\n")

    # Open the browser once the server is about to accept connections.
    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
