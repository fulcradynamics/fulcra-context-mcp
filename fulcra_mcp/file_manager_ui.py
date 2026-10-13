"""The file manager panel (an MCP App) that ``open_file_manager`` shows.

Plain HTML and JavaScript speaking the MCP Apps postMessage protocol directly,
so it needs no build step and no external scripts. It talks only to the host,
which relays to this server:

* ``tools/call list_files`` to browse folders;
* ``tools/call start_file_upload`` / ``upload_file_chunk`` to upload, in chunks;
* ``resources/read fulcra://files/...`` and ``ui/download-file`` to download,
  or ``get_file_download_link`` and ``ui/open-link`` where the host can't
  download files itself or the file is too large for one message.

Kept in a Python module rather than a data file so it ships in the wheel.
"""

FILE_MANAGER_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fulcra files</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: var(--color-background-primary, light-dark(#ffffff, #1b1b1b));
    --fg: var(--color-text-primary, light-dark(#1b1b1b, #f2f2f2));
    --muted: var(--color-text-secondary, light-dark(#666666, #a3a3a3));
    --line: var(--color-border-primary, light-dark(#e2e2e2, #3a3a3a));
    --accent: light-dark(#2f5bd3, #8aa8ff);
    --danger: light-dark(#b42318, #ff8a80);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 12px; background: var(--bg); color: var(--fg);
    font: 14px/1.4 var(--font-sans, system-ui, sans-serif);
  }
  header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .crumbs button { background: none; border: 0; color: var(--accent); cursor: pointer; padding: 0 2px; font: inherit; }
  .crumbs span { color: var(--muted); }
  #drop {
    border: 1.5px dashed var(--line); border-radius: 8px; padding: 14px;
    text-align: center; color: var(--muted); margin-bottom: 10px; cursor: pointer;
  }
  #drop.over { border-color: var(--accent); color: var(--fg); }
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: flex; align-items: center; gap: 8px; padding: 6px 2px; border-top: 1px solid var(--line); }
  li .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li .size { color: var(--muted); font-variant-numeric: tabular-nums; }
  button.link { background: none; border: 0; color: var(--accent); cursor: pointer; font: inherit; padding: 0; }
  button.action {
    border: 1px solid var(--line); border-radius: 6px; background: none; color: var(--fg);
    padding: 3px 8px; cursor: pointer; font: inherit;
  }
  progress { width: 120px; }
  .status { color: var(--muted); margin: 6px 0; min-height: 1.2em; }
  .error { color: var(--danger); }
  .empty { color: var(--muted); padding: 8px 2px; }
  a { color: var(--accent); word-break: break-all; }
</style>
</head>
<body>
<header>
  <strong>Fulcra files</strong>
  <nav class="crumbs" id="crumbs"></nav>
</header>
<div id="drop">Drop files here to upload them to this folder, or click to choose files.</div>
<input id="picker" type="file" multiple hidden>
<div class="status" id="status"></div>
<ul id="uploads"></ul>
<ul id="listing"></ul>
<script>
"use strict";
const MAX_INLINE_DOWNLOAD = 20 * 1024 * 1024;  // file_transfer.MAX_RESOURCE_BYTES
let nextId = 1;
const pending = new Map();
let host = {};
let currentPath = "/";

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
  const vars = context && context.styles && context.styles.variables;
  if (!vars) return;
  for (const [name, value] of Object.entries(vars)) {
    if (value) document.documentElement.style.setProperty(name, value);
  }
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
    for (const folder of listing.folders || []) {
      const name = typeof folder === "string" ? folder : (folder.name || folder.path);
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.className = "link name";
      b.textContent = name.split("/").filter(Boolean).pop() + "/";
      b.onclick = () => { currentPath = join(currentPath, b.textContent); refresh(); };
      li.append(b);
      list.append(li);
    }
    for (const file of listing.files || []) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = file.name;
      const size = document.createElement("span");
      size.className = "size";
      size.textContent = formatSize(file.size);
      const download = document.createElement("button");
      download.className = "action";
      download.textContent = "Download";
      download.onclick = () => downloadFile(join(currentPath, file.name), file);
      li.append(name, size, download);
      list.append(li);
    }
    if (!list.children.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "This folder is empty.";
      list.append(li);
    }
  } catch (e) {
    list.replaceChildren();
    setStatus(e.message, true);
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
      const link = await callTool("get_file_download_link", { path });
      if (link.saved_to) setStatus(`Saved ${file.name} to ${link.saved_to}.`);
      else showLink(file, link.url, "The download didn't complete.");
      return;
    }
    // The host can't save files for us, or the file is too large for one
    // message: fall back to a short-lived link.
    const link = await callTool("get_file_download_link", { path });
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
  const li = document.createElement("li");
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = file.name;
  const bar = document.createElement("progress");
  bar.max = Math.max(file.size, 1); bar.value = 0;
  li.append(name, bar);
  document.getElementById("uploads").append(li);
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
      bar.value = offset;
      if (sent.done) break;
    } while (offset < file.size);
    bar.replaceWith(Object.assign(document.createElement("span"), { className: "size", textContent: "Uploaded" }));
  } catch (e) {
    bar.replaceWith(Object.assign(document.createElement("span"), { className: "error", textContent: e.message }));
  }
}

async function uploadAll(files) {
  for (const file of files) await uploadFile(file);
  refresh();
}

const drop = document.getElementById("drop");
const picker = document.getElementById("picker");
drop.onclick = () => picker.click();
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
