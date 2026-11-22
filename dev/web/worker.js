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

function versionId(raw) {
  const id = String(raw || "alpha_01");
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$/.test(id)) {
    throw new Error("Tuntematon versio");
  }
  return id;
}

async function installVersion(fs, raw) {
  const id = versionId(raw);
  const root = new URL(`../versions/${id}/`, import.meta.url);
  report(`Haetaan versiota ${id}…`);
  const metaRes = await fresh(new URL("version.json", root));
  if (!metaRes.ok) throw new Error("Versiota " + id + " ei löydy");
  const meta = await metaRes.json();
  if (meta.id !== id) throw new Error("Version tunniste ei täsmää");
  const cards = meta.cards;
  if (!Array.isArray(cards) || cards.length === 0) {
    throw new Error("Versiolta puuttuvat kortit");
  }
  const cfg = await fresh(new URL("config.py", root));
  if (!cfg.ok) throw new Error("Version asetustiedosto puuttuu");
  mkdirp(fs, `/pkg/versions/${id}/cards`);
  fs.writeFile(`/pkg/versions/${id}/config.py`, await cfg.text());
  fs.writeFile(`/pkg/versions/${id}/version.json`, JSON.stringify(meta));
  for (const name of cards) {
    if (!/^[A-Za-z0-9_.-]+$/.test(name)) throw new Error("Virheellinen korttitiedosto");
    const res = await fresh(new URL("cards/" + name, root));
    if (!res.ok) throw new Error("Puuttuu " + name);
    fs.writeFile(`/pkg/versions/${id}/cards/${name}`, await res.text());
  }
  return id;
}

async function installBots(fs, id) {
  const root = new URL(`../versions/${id}/bots/`, import.meta.url);
  const indexRes = await fresh(new URL("index.json", root));
  if (!indexRes.ok) {
    report("Tässä versiossa ei ole koulutettuja botteja.");
    return;
  }
  const index = await indexRes.json();
  const names = Array.isArray(index.bots) ? index.bots : [];
  mkdirp(fs, `/pkg/versions/${id}/bots`);
  fs.writeFile(`/pkg/versions/${id}/bots/index.json`, JSON.stringify(index));
  for (const name of names) {
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$/.test(name)) {
      throw new Error("Virheellinen botti");
    }
    report(`Ladataan bottia ${name}…`);
    const botRoot = new URL(`${name}/`, root);
    const manifestRes = await fresh(new URL("manifest.json", botRoot));
    if (!manifestRes.ok) throw new Error("Botin kuvaus puuttuu: " + name);
    const manifest = await manifestRes.json();
    const dest = `/pkg/versions/${id}/bots/${name}`;
    mkdirp(fs, `${dest}/cards`);
    fs.writeFile(`${dest}/manifest.json`, JSON.stringify(manifest));
    const weightsName = String(manifest.weights || "weights.npz");
    if (!/^[A-Za-z0-9_.-]+$/.test(weightsName)) throw new Error("Virheelliset painot");
    const weightsRes = await fresh(new URL(weightsName, botRoot));
    if (!weightsRes.ok) throw new Error("Botin painot puuttuvat: " + name);
    fs.writeFile(`${dest}/${weightsName}`, new Uint8Array(await weightsRes.arrayBuffer()));
    const cfg = await fresh(new URL("config.py", botRoot));
    if (cfg.ok) fs.writeFile(`${dest}/config.py`, await cfg.text());
    const cards = Array.isArray(manifest.cards) ? manifest.cards : [];
    for (const card of cards) {
      if (!/^[A-Za-z0-9_.-]+$/.test(card)) throw new Error("Virheellinen korttitiedosto");
      const cardRes = await fresh(new URL(`cards/${card}`, botRoot));
      if (!cardRes.ok) throw new Error("Botin kortti puuttuu: " + card);
      fs.writeFile(`${dest}/cards/${card}`, await cardRes.text());
    }
  }
}

async function boot(rawVersion) {
  report("Haetaan Pyodide-latainta…");
  const { loadPyodide } = await import(PYODIDE_URL);
  report("Käynnistetään Pythonia… tämä lataus kestää hetken.");
  const pyodide = await loadPyodide();
  report("Ladataan NumPya…");
  await pyodide.loadPackage("numpy");
  const fs = pyodide.FS;
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
  const version = await installVersion(fs, rawVersion);
  await installBots(fs, version);
  report("Käynnistetään peliä…");
  const versionLiteral = JSON.stringify(version);
  await pyodide.runPythonAsync(`
import json
import os
import sys
sys.path.insert(0, "/pkg")
os.environ["CONVOY_VERSION"] = ${versionLiteral}
os.environ["CONVOY_VERSIONS"] = "/pkg/versions"
os.environ["CONVOY_CARDS"] = "/pkg/versions/" + ${versionLiteral} + "/cards"
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
    booting = boot(msg.version)
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
