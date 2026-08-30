const $ = (id) => document.getElementById(id);

const state = {
  files: [],          // [{path, name, size}]
  imageMode: "extract",
  converting: false,
};

/* ---------------- Theme ---------------- */
const savedTheme = (() => {
  try { return localStorage.getItem("pdftomd-theme"); } catch { return null; }
})();
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
document.documentElement.dataset.theme = savedTheme || (prefersDark ? "dark" : "light");

$("themeToggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("pdftomd-theme", next); } catch {}
});

/* ---------------- Helpers ---------------- */
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 2600);
}

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function fmtNum(n) {
  return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k" : String(n);
}

/* Roughly 4 characters per token for English prose. */
const estTokens = (chars) => Math.round(chars / 4);

/* ---------------- File list ---------------- */
function addFiles(items) {
  const seen = new Set(state.files.map((f) => f.path));
  for (const it of items) if (!seen.has(it.path)) state.files.push(it);
  renderFiles();
}

function renderFiles() {
  const list = $("fileList");
  const n = state.files.length;

  if (!n) {
    list.hidden = true;
    $("convertBtn").disabled = true;
    $("hint").textContent = "Add at least one PDF to start.";
    return;
  }

  list.hidden = false;
  $("fileCount").textContent = n === 1 ? "1 file" : `${n} files`;
  $("fileItems").innerHTML = state.files
    .map(
      (f) =>
        `<li><span class="fname" title="${esc(f.path)}">${esc(f.name)}</span>` +
        `<span class="fsize">${fmtSize(f.size)}</span></li>`
    )
    .join("");

  $("convertBtn").disabled = state.converting;
  $("hint").textContent = state.converting
    ? "Converting…"
    : `Ready to convert ${n === 1 ? "1 file" : n + " files"}.`;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

$("clearFiles").addEventListener("click", () => {
  state.files = [];
  renderFiles();
});

/* ---------------- Drag & drop / browse ---------------- */
const dz = $("dropzone");

["dragenter", "dragover"].forEach((ev) =>
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    dz.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dz.addEventListener(ev, (e) => {
    e.preventDefault();
    if (ev === "dragleave" && dz.contains(e.relatedTarget)) return;
    dz.classList.remove("drag");
  })
);

dz.addEventListener("drop", (e) => uploadFiles([...e.dataTransfer.files]));
dz.addEventListener("click", () => $("fileInput").click());
dz.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("fileInput").click(); }
});
$("browseBtn").addEventListener("click", (e) => { e.stopPropagation(); $("fileInput").click(); });
$("fileInput").addEventListener("change", (e) => {
  uploadFiles([...e.target.files]);
  e.target.value = "";
});

async function uploadFiles(fileObjs) {
  const pdfs = fileObjs.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) return toast("Only PDF files are supported.");

  const fd = new FormData();
  pdfs.forEach((f) => fd.append("files", f));

  try {
    const res = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) return toast(data.error || "Upload failed.");
    addFiles(data.files);
    if (!$("outputInput").value) $("outputInput").value = data.default_output;
    toast(`Added ${data.files.length} file${data.files.length > 1 ? "s" : ""}.`);
  } catch {
    toast("Upload failed.");
  }
}

/* ---------------- Folder scan ---------------- */
$("scanBtn").addEventListener("click", scanPath);
$("pathInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") scanPath();
});

async function scanPath() {
  const path = $("pathInput").value.trim();
  if (!path) return toast("Enter a path first.");

  try {
    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, recursive: $("recursive").checked }),
    });
    const data = await res.json();
    if (!res.ok) return toast(data.error || "Scan failed.");
    addFiles(data.files);
    if (!$("outputInput").value) $("outputInput").value = data.default_output;
    toast(`Found ${data.files.length} PDF${data.files.length > 1 ? "s" : ""}.`);
  } catch {
    toast("Scan failed.");
  }
}

/* ---------------- Image mode ---------------- */
$("imageMode").addEventListener("click", (e) => {
  const btn = e.target.closest(".seg");
  if (!btn) return;
  [...$("imageMode").children].forEach((b) => b.classList.toggle("active", b === btn));
  state.imageMode = btn.dataset.mode;
});

/* ---------------- Convert ---------------- */
$("convertBtn").addEventListener("click", convert);

async function convert() {
  if (state.converting || !state.files.length) return;

  let jobId;
  try {
    const res = await fetch("/api/job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        files: state.files.map((f) => f.path),
        output: $("outputInput").value.trim(),
        image_mode: state.imageMode,
        ocr: $("ocr").checked,
        tables: $("tables").checked,
      }),
    });
    const data = await res.json();
    if (!res.ok) return toast(data.error || "Could not start.");
    jobId = data.job_id;
  } catch {
    return toast("Could not reach the server.");
  }

  // Enter the converting state.
  state.converting = true;
  $("convertBtn").disabled = true;
  $("convertBtn").querySelector(".btn-label").textContent = "Converting…";
  $("emptyState").hidden = true;
  $("progressWrap").hidden = false;
  $("summary").hidden = true;
  $("resultList").innerHTML = "";
  $("progressBar").style.width = "0%";
  $("hint").textContent = "Converting…";

  const totals = { files: 0, chars: 0, images: 0, tables: 0 };
  const source = new EventSource(`/api/convert/${jobId}`);

  source.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);

    if (msg.type === "start") {
      $("progressCount").textContent = `0 / ${msg.total}`;
    } else if (msg.type === "file_start") {
      $("currentFile").textContent = msg.name;
    } else if (msg.type === "file_done") {
      $("progressCount").textContent = `${msg.index} / ${msg.total}`;
      $("progressBar").style.width = (msg.index / msg.total) * 100 + "%";
      if (msg.ok) {
        totals.files++;
        totals.chars += msg.chars;
        totals.images += msg.images_kept;
        totals.tables += msg.tables;
      }
      addResult(msg);
    } else if (msg.type === "complete") {
      source.close();
      finish(totals, msg);
    }
  };

  source.onerror = () => {
    source.close();
    state.converting = false;
    $("convertBtn").querySelector(".btn-label").textContent = "Convert";
    renderFiles();
    toast("Connection to the server was lost.");
  };
}

function finish(totals, msg) {
  state.converting = false;
  $("convertBtn").querySelector(".btn-label").textContent = "Convert";
  renderFiles();

  $("progressLabel").textContent = "Done";
  $("currentFile").textContent = `Saved to ${msg.output}`;

  $("statFiles").textContent = totals.files;
  $("statTokens").textContent = fmtNum(estTokens(totals.chars));
  $("statImages").textContent = totals.images;
  $("statTables").textContent = totals.tables;
  $("summary").hidden = false;

  const s = msg.summary;
  toast(s.failed ? `Done — ${s.ok} converted, ${s.failed} failed.` : `Done — ${s.ok} converted.`);
}

function addResult(msg) {
  const li = document.createElement("li");
  li.className = "result-item";

  if (!msg.ok) {
    li.innerHTML =
      `<div class="result-top"><span class="result-name">${esc(msg.name)}</span>` +
      `<span class="badge err">failed</span></div>` +
      `<p class="result-err">${esc(msg.error)}</p>`;
    $("resultList").prepend(li);
    return;
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  const chips = [plural(msg.pages, "page"), `~${fmtNum(estTokens(msg.chars))} tokens`];
  if (msg.images_kept) {
    const dropped = (msg.image_report && msg.image_report.dropped) || 0;
    chips.push(plural(msg.images_kept, "image") + (dropped ? ` (${dropped} filtered)` : ""));
  } else if (msg.image_report && msg.image_report.dropped) {
    chips.push(`${plural(msg.image_report.dropped, "image")} filtered`);
  }
  if (msg.tables) chips.push(plural(msg.tables, "table"));
  if (msg.ocr_pages && msg.ocr_pages.length) chips.push(`OCR ×${msg.ocr_pages.length}`);

  li.innerHTML =
    `<div class="result-top"><span class="result-name" title="${esc(msg.name)}">${esc(msg.name)}</span>` +
    `<span class="badge ok">done</span></div>` +
    `<div class="result-meta">${chips.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div>` +
    (msg.warning ? `<p class="result-warn">${esc(msg.warning)}</p>` : "") +
    `<div class="result-actions">` +
    `<button class="btn btn-ghost btn-sm" data-preview="${esc(msg.markdown_path)}">Preview</button>` +
    `<a class="btn btn-ghost btn-sm" href="/api/download?path=${encodeURIComponent(msg.markdown_path)}">Download</a>` +
    `</div>`;

  $("resultList").prepend(li);
}

/* ---------------- Preview ---------------- */
$("resultList").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-preview]");
  if (!btn) return;

  const path = btn.dataset.preview;
  try {
    const res = await fetch(`/api/preview?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (!res.ok) return toast(data.error || "Could not read the file.");

    $("previewTitle").textContent = path.split(/[\\/]/).pop();
    $("previewBody").textContent =
      data.text + (data.truncated ? "\n\n… truncated for preview." : "");
    $("previewOverlay").hidden = false;
  } catch {
    toast("Could not read the file.");
  }
});

$("closePreview").addEventListener("click", closePreview);
$("previewOverlay").addEventListener("click", (e) => {
  if (e.target === $("previewOverlay")) closePreview();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePreview();
});

function closePreview() {
  $("previewOverlay").hidden = true;
}

$("copyBtn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("previewBody").textContent);
    toast("Copied to clipboard.");
  } catch {
    toast("Copy failed.");
  }
});

/* ---------------- OCR availability ---------------- */
/* Checked up front so a missing engine is visible before a run, not after. */
(async () => {
  try {
    const res = await fetch("/api/status");
    const { ocr } = await res.json();
    const note = $("ocrNote");
    if (ocr.available) {
      note.textContent = `pages with no text layer — Tesseract ${ocr.version} ready`;
    } else {
      note.textContent = "unavailable — " + ocr.error;
      note.style.color = "var(--err)";
      $("ocr").checked = false;
    }
  } catch {
    /* Status is advisory; conversion still works without it. */
  }
})();

renderFiles();
