/* Pyodide worker: fetch this package, then answer the lobby URLs. */

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.mjs";

function mkdirp(fs, path) {
  const parts = path.split("/").filter(Boolean);
  let current = "";
  for (const part of parts) {
    current += "/" + part;
    try {
      fs.mkdir(current);
    } catch (err) {
      /* already there */
    }
  }
}

async function boot() {
  self.postMessage({ type: "status", text: "Ladataan Pyodidea…" });
  const { loadPyodide } = await import(PYODIDE_URL);
  const pyodide = await loadPyodide();
  self.postMessage({ type: "status", text: "Ladataan pelikoodia…" });
  const listUrl = new URL("pyodide_files.json", import.meta.url);
  const files = await fetch(listUrl).then((res) => {
    if (!res.ok) throw new Error("pyodide_files.json puuttuu");
    return res.json();
  });
  const pkg = new URL("../src/sixtyfivekmconvoy/", import.meta.url);
  const fs = pyodide.FS;
  mkdirp(fs, "/pkg/sixtyfivekmconvoy");
  for (const rel of files) {
    const res = await fetch(new URL(rel, pkg));
    if (!res.ok) throw new Error("Puuttuu " + rel);
    const dest = "/pkg/sixtyfivekmconvoy/" + rel;
    mkdirp(fs, dest.split("/").slice(0, -1).join("/"));
    fs.writeFile(dest, await res.text());
  }
  await pyodide.runPythonAsync(`
import json
import os
import sys
sys.path.insert(0, "/pkg")
os.environ["CONVOY_CONFIG"] = "retire"
from sixtyfivekmconvoy.play import LocalLobby
lobby = LocalLobby()

def respond(method, url, body_text, headers_text):
    body = json.loads(body_text) if body_text else None
    headers = json.loads(headers_text or "{}")
    status, payload = lobby.handle(method, url, body, headers)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return json.dumps({"status": int(status), "text": text})
`);
  return pyodide.globals.get("respond");
}

let respond = null;
let booting = null;

self.onmessage = (event) => {
  const msg = event.data || {};
  if (msg.type === "boot") {
    booting = boot()
      .then((fn) => {
        respond = fn;
        self.postMessage({ type: "ready" });
      })
      .catch((err) => {
        self.postMessage({ type: "failed", text: String(err) });
      });
    return;
  }
  if (msg.id == null) return;
  Promise.resolve(booting)
    .then(() => {
      const raw = String(respond(
        msg.method || "GET",
        msg.url || "/",
        msg.body,
        JSON.stringify(msg.headers || {})
      );
      const parsed = JSON.parse(raw);
      self.postMessage({ id: msg.id, status: parsed.status, text: parsed.text });
    })
    .catch((err) => {
      self.postMessage({ id: msg.id, status: 500, text: String(err) });
    });
};
