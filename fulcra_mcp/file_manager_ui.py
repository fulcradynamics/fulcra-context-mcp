"""The file manager panel (an MCP App) that ``open_file_manager`` shows.

Plain HTML and JavaScript speaking the MCP Apps postMessage protocol directly,
so it needs no build step and no external scripts. It talks only to the host,
which relays to this server:

* ``tools/call list_files`` to browse folders;
* ``tools/call start_file_upload`` / ``upload_file_chunk`` to upload, in chunks;
* ``resources/read fulcra://files/...`` and ``ui/download-file`` to download,
  or ``read_file(as_link=True)`` and ``ui/open-link`` where the host can't
  download files itself or the file is too large for one message.

Kept in a Python module rather than a data file so it ships in the wheel.
"""

FILE_MANAGER_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fulcra files</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rubik:wght@400;500;600&display=swap">
<style>
  /* Fulcra's portal palette (portal tailwind.config.cjs): dark by default, as in
     the portal, with a light variant when the host is in light mode. */
  :root {
    color-scheme: dark;
    --page: #16161d;          /* fulcra-black */
    --card: #222227;          /* fulcra-black-50 */
    --line: #38383a;          /* fulcra-black-20 */
    --text: #ffffff;
    --muted: #8a8a8e;         /* fulcra-gray */
    --teal: #56d6b7;
    --purple: #7b61ff;
    --error: #ff3b30;
    --tile: #16161d;
    --hover: rgba(22, 22, 29, 0.4);
  }
  :root[data-theme="light"] {
    color-scheme: light;
    --page: #ffffff;
    --card: #ffffff;
    --line: #e4e4e7;
    --text: #16161d;
    --muted: #6b6b70;
    --teal: #1f9e80;
    --tile: #f4f4f5;
    --hover: rgba(22, 22, 29, 0.03);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px; background: var(--page); color: var(--text);
    font: 14px/1.4 Rubik, var(--font-sans, system-ui), sans-serif;
  }
  button { font: inherit; }
  svg { width: 1em; height: 1em; fill: currentColor; flex: none; }

  header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
  header strong { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }
  .crumbs { display: flex; align-items: center; gap: 2px; flex-wrap: wrap; font-size: 13px; }
  .crumbs button {
    background: none; border: 0; color: var(--teal); cursor: pointer; padding: 2px 4px; border-radius: 6px;
  }
  .crumbs button:hover { background: color-mix(in srgb, var(--teal) 10%, transparent); }
  .crumbs span { color: var(--muted); opacity: 0.5; }

  /* Cards: rounded, bordered rows, as in the portal's files and data-types lists. */
  .card { border: 1px solid var(--line); background: var(--card); border-radius: 12px; overflow: hidden; }
  .card + .card, #drop + .status { margin-top: 12px; }

  #drop {
    display: flex; align-items: center; gap: 14px; padding: 14px 16px; cursor: pointer;
    border: 1px dashed var(--line); border-radius: 12px; background: var(--card);
    color: var(--muted); font-size: 13px; transition: border-color 0.15s, background 0.15s;
  }
  #drop:hover, #drop.over { border-color: var(--teal); }
  #drop.over { background: color-mix(in srgb, var(--teal) 6%, var(--card)); }

  /* Icon tiles: teal for folders and uploads, neutral for files. */
  .tile {
    display: flex; align-items: center; justify-content: center; flex: none;
    width: 36px; height: 36px; border-radius: 8px; font-size: 14px;
    background: var(--tile); color: var(--muted);
  }
  .tile.teal { background: color-mix(in srgb, var(--teal) 10%, transparent); color: var(--teal); }
  .tile.error { background: color-mix(in srgb, var(--error) 10%, transparent); color: var(--error); }

  ul { list-style: none; margin: 0; padding: 0; }
  ul:empty { display: none; }
  li {
    display: flex; align-items: center; gap: 14px; padding: 14px 16px;
    border-bottom: 1px solid color-mix(in srgb, var(--line) 60%, transparent);
  }
  li:last-child { border-bottom: 0; }
  li:hover { background: var(--hover); }
  .rise { animation: rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
  @media (prefers-reduced-motion: reduce) { .rise { animation: none; } }

  .main { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
  .name {
    font-size: 15px; font-weight: 500; letter-spacing: -0.01em; color: var(--text);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  button.name {
    background: none; border: 0; padding: 0; text-align: left; cursor: pointer; color: var(--teal);
  }
  li:hover button.name { text-decoration: underline; }
  .sub { font-size: 12px; color: color-mix(in srgb, var(--muted) 60%, transparent); }
  .sub.error { color: var(--error); }

  /* The stacked stat on the right: small uppercase label over the value. */
  .stat { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.25; flex: none; }
  .stat .label {
    font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em;
    color: color-mix(in srgb, var(--muted) 50%, transparent);
  }
  .stat .value { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }

  /* Small square action buttons and pill buttons, tinted with the accent. */
  .icon-button, .pill {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex: none;
    border: 0; border-radius: 6px; cursor: pointer; transition: background 0.15s;
    background: color-mix(in srgb, var(--teal) 10%, transparent); color: var(--teal);
  }
  .icon-button { width: 28px; height: 28px; font-size: 12px; }
  .pill { padding: 6px 12px; font-size: 13px; font-weight: 500; }
  .icon-button:hover, .pill:hover { background: color-mix(in srgb, var(--teal) 20%, transparent); }

  .bar { width: 120px; height: 4px; border-radius: 2px; background: var(--line); overflow: hidden; flex: none; }
  .bar > div { height: 100%; width: 0; background: var(--teal); transition: width 0.2s; }
  .done { font-size: 12px; font-weight: 500; color: var(--teal); flex: none; }

  .state { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 24px; text-align: center; }
  .state .tile { width: 48px; height: 48px; border-radius: 12px; font-size: 18px; }
  .state p { margin: 0; max-width: 28rem; font-size: 13px; color: var(--muted); }

  .status { font-size: 13px; color: var(--muted); min-height: 1.2em; margin-bottom: 12px; }
  .status.error { color: var(--error); }
  .status:empty { display: none; }
  a { color: var(--teal); word-break: break-all; }
</style>
</head>
<body>
<header>
  <strong>Fulcra files</strong>
  <nav class="crumbs" id="crumbs"></nav>
</header>
<div id="drop" role="button" tabindex="0">
  <div class="tile teal" id="drop-icon"></div>
  <div>Drop files here to upload them to this folder, or click to choose files.</div>
</div>
<input id="picker" type="file" multiple hidden>
<div class="status" id="status"></div>
<ul id="uploads" class="card"></ul>
<ul id="listing" class="card"></ul>
<script>
"use strict";
const MAX_INLINE_DOWNLOAD = 20 * 1024 * 1024;  // file_transfer.MAX_RESOURCE_BYTES
let nextId = 1;
const pending = new Map();
let host = {};
let currentPath = "/";

// Simple inline icons, so the panel loads nothing but its font.
const ICONS = {
  folder: '<svg viewBox="0 0 16 16"><path d="M1.5 3.5A1.5 1.5 0 0 1 3 2h3.4l1.6 1.6H13a1.5 1.5 0 0 1 1.5 1.5v7.4A1.5 1.5 0 0 1 13 14H3a1.5 1.5 0 0 1-1.5-1.5z"/></svg>',
  file: '<svg viewBox="0 0 16 16"><path d="M3.5 1.5A1.5 1.5 0 0 1 5 0h5l4 4v10.5A1.5 1.5 0 0 1 12.5 16h-8A1.5 1.5 0 0 1 3 14.5zM10 1v3.5h3.5z" transform="translate(-0.5 0)"/></svg>',
  download: '<svg viewBox="0 0 16 16"><path d="M7 1h2v7.2l2.6-2.6 1.4 1.4L8 12 3 7l1.4-1.4L7 8.2zM2 13h12v2H2z"/></svg>',
  upload: '<svg viewBox="0 0 16 16"><path d="M4.5 13A3.5 3.5 0 0 1 4 6.03 4.5 4.5 0 0 1 12.7 5 3.5 3.5 0 0 1 12 13H9V9.8l1.3 1.3 1.4-1.4L8 6 4.3 9.7l1.4 1.4L7 9.8V13z"/></svg>',
  warning: '<svg viewBox="0 0 16 16"><path d="M8 1 15.5 14.5h-15zM7.2 6v4.2h1.6V6zm0 5.4V13h1.6v-1.6z"/></svg>',
};

// An element with a class, optional text, and children.
function el(tag, className, text, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  node.append(...children);
  return node;
}

function tile(icon, tone) {
  const node = el("div", "tile" + (tone ? " " + tone : ""));
  node.innerHTML = ICONS[icon];
  return node;
}

function stat(label, value) {
  return el("div", "stat", null, el("span", "label", label), el("span", "value", value || "—"));
}

// The portal's staggered entrance, capped so a long list doesn't crawl in.
function rise(node, index) {
  node.classList.add("rise");
  node.style.animationDelay = Math.min(index, 12) * 40 + "ms";
  return node;
}

function formatDate(ts) {
  if (!ts) return "";
  return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// --- MCP Apps messaging -----------------------------------------------------
function request(method, params) {
  const id = nextId++;
  window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
function notify(method, params) {
  window.parent.postMessage({ jsonrpc: "2.0", method, params }, "*");
}
window.addEventListener("message", (event) => {
  const msg = event.data;
  if (!msg || msg.jsonrpc !== "2.0") return;
  if (msg.id !== undefined && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(msg.error.message || "Request failed"));
    else resolve(msg.result);
    return;
  }
  if (msg.method === "ui/notifications/tool-input") {
    const path = msg.params && msg.params.arguments && msg.params.arguments.path;
    if (path) currentPath = normalize(path);
    refresh();
  } else if (msg.method === "ui/notifications/host-context-changed") {
    applyStyles(msg.params);
  }
});

function applyStyles(context) {
  // The panel keeps Fulcra's own colors and font; it only follows the host's light or dark theme.
  const theme = context && context.theme;
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
}

// A tool's result: its structured content, or the JSON in its text.
async function callTool(name, args) {
  const result = await request("tools/call", { name, arguments: args });
  const text = (result.content || []).map((c) => c.text || "").join("\n");
  if (result.isError) throw new Error(text || `${name} failed`);
  const structured = result.structuredContent;
  // A tool returning plain text comes wrapped as {"result": "<text>"}.
  const wrapped = structured && Object.keys(structured).length === 1 && typeof structured.result === "string";
  if (structured && !wrapped) return structured;
  const start = text.search(/[\[{]/);
  if (start < 0) throw new Error(text);
  return JSON.parse(text.slice(start));
}

// --- browsing -----------------------------------------------------------------
function normalize(path) {
  const parts = path.split("/").filter((p) => p && p !== ".");
  return "/" + parts.join("/");
}
function join(folder, name) {
  return normalize(folder + "/" + name);
}
function formatSize(bytes) {
  if (bytes == null) return "";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes, i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + " " + units[i];
}
function setStatus(text, isError) {
  const el = document.getElementById("status");
  el.textContent = text || "";
  el.className = "status" + (isError ? " error" : "");
}

function renderCrumbs() {
  const nav = document.getElementById("crumbs");
  nav.replaceChildren();
  const parts = currentPath.split("/").filter(Boolean);
  const add = (label, path) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = () => { currentPath = path; refresh(); };
    nav.append(b);
  };
  add("/", "/");
  parts.forEach((part, i) => {
    const sep = document.createElement("span");
    sep.textContent = i ? "/" : "";
    nav.append(sep);
    add(part, "/" + parts.slice(0, i + 1).join("/"));
  });
}

async function refresh() {
  renderCrumbs();
  const list = document.getElementById("listing");
  try {
    const listing = await callTool("list_files", { path: currentPath });
    list.replaceChildren();
    let index = 0;
    for (const folder of listing.folders || []) {
      const name = (typeof folder === "string" ? folder : (folder.name || folder.path)).split("/").filter(Boolean).pop();
      const open = el("button", "name", name);
      open.onclick = () => { currentPath = join(currentPath, name); refresh(); };
      const li = el("li", null, null, tile("folder", "teal"), el("div", "main", null, open, el("div", "sub", "Folder")));
      li.onclick = (e) => { if (e.target === li) open.click(); };
      list.append(rise(li, index++));
    }
    for (const file of listing.files || []) {
      const download = el("button", "icon-button");
      download.innerHTML = ICONS.download;
      download.title = "Download";
      download.setAttribute("aria-label", "Download " + file.name);
      download.onclick = () => downloadFile(join(currentPath, file.name), file);
      const when = file.uploaded_at || file.created_at;
      const main = el("div", "main", null, el("div", "name", file.name));
      if (when) main.append(el("div", "sub", "Uploaded " + formatDate(when)));
      list.append(rise(el("li", null, null, tile("file"), main, stat("Size", formatSize(file.size)), download), index++));
    }
    if (!list.children.length) {
      const upload = el("button", "pill");
      upload.innerHTML = ICONS.upload;
      upload.append(" Upload");
      upload.onclick = () => picker.click();
      list.append(el("li", "state", null, tile("upload", "teal"),
        el("p", null, "This folder is empty. Upload files to keep them in Fulcra, where your agents can read them and you can share them."),
        upload));
    }
  } catch (e) {
    list.replaceChildren(el("li", "state", null, tile("warning", "error"), el("p", null, e.message)));
  }
}

// --- downloading --------------------------------------------------------------
function resourceUri(path) {
  return "fulcra://files/" + path.split("/").filter(Boolean).map(encodeURIComponent).join("/");
}

// Show a download link for the user to click or copy.
function showLink(file, url, note) {
  const status = document.getElementById("status");
  status.className = "status";
  status.replaceChildren(`${note ? note + " " : ""}Download ${file.name} (link works for 10 minutes): `);
  const a = document.createElement("a");
  a.href = url; a.target = "_blank"; a.rel = "noopener"; a.textContent = url;
  status.append(a);
}

// The host answers some requests with {isError: true} rather than an error.
async function hostSucceeded(method, params) {
  try {
    const result = await request(method, params);
    return !(result && result.isError);
  } catch (e) {
    return false;
  }
}

async function downloadFile(path, file) {
  setStatus(`Preparing ${file.name}…`);
  try {
    const caps = host.hostCapabilities || {};
    if (caps.downloadFile && caps.serverResources && (file.size || 0) <= MAX_INLINE_DOWNLOAD) {
      const read = await request("resources/read", { uri: resourceUri(path) });
      const content = read.contents[0];
      const saved = await hostSucceeded("ui/download-file", {
        contents: [{
          type: "resource",
          resource: {
            uri: "file:///" + encodeURIComponent(file.name),
            mimeType: content.mimeType,
            ...(content.blob !== undefined ? { blob: content.blob } : { text: content.text }),
          },
        }],
      });
      if (saved) {
        setStatus(`Downloaded ${file.name}.`);
        return;
      }
      // The user may have cancelled, or the host refused: offer a link to
      // click rather than opening one unasked.
      const link = await callTool("read_file", { path, as_link: true });
      if (link.saved_to) setStatus(`Saved ${file.name} to ${link.saved_to}.`);
      else showLink(file, link.url, "The download didn't complete.");
      return;
    }
    // The host can't save files for us, or the file is too large for one
    // message: fall back to a short-lived link.
    const link = await callTool("read_file", { path, as_link: true });
    if (link.saved_to) {
      // A server running on the user's computer saves the file there instead.
      setStatus(`Saved ${file.name} to ${link.saved_to}.`);
    } else if (caps.openLinks && await hostSucceeded("ui/open-link", { url: link.url })) {
      setStatus(`Opened a download link for ${file.name}.`);
    } else {
      showLink(file, link.url, caps.openLinks ? "The link couldn't be opened here." : "");
    }
  } catch (e) {
    setStatus(`Couldn't download ${file.name}: ${e.message}`, true);
  }
}

// --- uploading ----------------------------------------------------------------
function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

async function uploadFile(file) {
  const fill = el("div");
  const bar = el("div", "bar", null, fill);
  const sub = el("div", "sub", "Uploading…");
  const li = el("li", null, null, tile("upload", "teal"), el("div", "main", null, el("div", "name", file.name), sub), stat("Size", formatSize(file.size)), bar);
  document.getElementById("uploads").append(rise(li, 0));
  try {
    const started = await callTool("start_file_upload", {
      path: join(currentPath, file.name),
      size: file.size,
      ...(file.type ? { content_type: file.type } : {}),
    });
    let offset = 0;
    do {
      const end = Math.min(offset + started.chunk_size, file.size);
      const data = toBase64(await file.slice(offset, end).arrayBuffer());
      const sent = await callTool("upload_file_chunk", { upload_id: started.upload_id, offset, data });
      offset = sent.received;
      fill.style.width = (100 * offset / Math.max(file.size, 1)) + "%";
      if (sent.done) break;
    } while (offset < file.size);
    sub.textContent = "Saved to " + join(currentPath, file.name);
    bar.replaceWith(el("span", "done", "Uploaded"));
  } catch (e) {
    sub.textContent = e.message;
    sub.className = "sub error";
    bar.remove();
  }
}

async function uploadAll(files) {
  for (const file of files) await uploadFile(file);
  refresh();
}

const drop = document.getElementById("drop");
document.getElementById("drop-icon").innerHTML = ICONS.upload;
const picker = document.getElementById("picker");
drop.onclick = () => picker.click();
drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); } };
picker.onchange = () => { uploadAll([...picker.files]); picker.value = ""; };
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  uploadAll([...e.dataTransfer.files]);
});

if (window.ResizeObserver) {
  new ResizeObserver(() => {
    notify("ui/notifications/size-changed", {
      width: document.documentElement.scrollWidth,
      height: document.documentElement.scrollHeight,
    });
  }).observe(document.body);
}

// --- start ----------------------------------------------------------------------
(async () => {
  try {
    host = await request("ui/initialize", {
      appInfo: { name: "Fulcra files", version: "1.0.0" },
      appCapabilities: { availableDisplayModes: ["inline"] },
      protocolVersion: "2026-01-26",
    });
    applyStyles(host.hostContext);
  } catch (e) {
    setStatus("This client couldn't start the file manager: " + e.message, true);
  }
  notify("ui/notifications/initialized", {});
  refresh();
})();
</script>
</body>
</html>
"""
