/* Pyodide worker: fetch this package, then answer the lobby URLs. */

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.mjs";
const SOURCE_REV = "nocache";

function fresh(url) {
  const target = new URL(url, import.meta.url);
  target.searchParams.set("v", SOURCE_REV);
  return fetch(target, { cache: "no-store" });
}

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

function report(text) {
  self.postMessage({ type: "status", text });
}

async function boot() {
  report("Haetaan Pyodide-latainta…");
  const { loadPyodide } = await import(PYODIDE_URL);
  report("Käynnistetään Pythonia… tämä lataus kestää hetken.");
  const pyodide = await loadPyodide();
  report("Ladataan NumPya…");
  await pyodide.loadPackage("numpy");
  const fs = pyodide.FS;
  report("Ladataan bottia…");
  const botRes = await fresh("bots/curriculum-step1840496.npz");
  if (botRes.ok) {
    mkdirp(fs, "/pkg/bots");
    fs.writeFile(
      "/pkg/bots/curriculum-step1840496.npz",
      new Uint8Array(await botRes.arrayBuffer())
    );
  } else {
    report("Bottia ei löytynyt. Vastustajat ovat satunnaisia.");
  }
  report("Haetaan pelikoodin luetteloa…");
  const files = await fresh("pyodide_files.json").then((res) => {
    if (!res.ok) throw new Error("pyodide_files.json puuttuu");
    return res.json();
  });
  const pkg = new URL("../src/sixtyfivekmconvoy/", import.meta.url);
  mkdirp(fs, "/pkg/sixtyfivekmconvoy");
  for (let i = 0; i < files.length; i++) {
    const rel = files[i];
    report(`Ladataan pelikoodia ${i + 1}/${files.length}: ${rel}`);
    const fileUrl = new URL(rel, pkg);
    fileUrl.searchParams.set("v", SOURCE_REV);
    const res = await fetch(fileUrl, { cache: "no-store" });
    if (!res.ok) throw new Error("Puuttuu " + rel);
    const dest = "/pkg/sixtyfivekmconvoy/" + rel;
    mkdirp(fs, dest.split("/").slice(0, -1).join("/"));
    fs.writeFile(dest, await res.text());
  }
  report("Käynnistetään peliä…");
  await pyodide.runPythonAsync(`
import json
import os
import sys
sys.path.insert(0, "/pkg")
os.environ["CONVOY_CONFIG"] = "retire"
weights = "/pkg/bots/curriculum-step1840496.npz"
if os.path.isfile(weights):
    os.environ["CONVOY_BOT_WEIGHTS"] = weights
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
      const raw = String(
        respond(
          msg.method || "GET",
          msg.url || "/",
          msg.body,
          JSON.stringify(msg.headers || {})
        )
      );
      const parsed = JSON.parse(raw);
      self.postMessage({ id: msg.id, status: parsed.status, text: parsed.text });
    })
    .catch((err) => {
      self.postMessage({ id: msg.id, status: 500, text: String(err) });
    });
};
