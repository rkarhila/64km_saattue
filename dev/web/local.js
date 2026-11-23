/* Loads the same page as the server, then talks to the Pyodide worker. */

const status = document.getElementById("bootStatus");
let lastText = status ? status.textContent : "";
let lastChange = Date.now();

function say(text) {
  lastText = text;
  lastChange = Date.now();
  if (status) status.textContent = text;
}

setInterval(() => {
  if (!status || !status.isConnected) return;
  const seconds = Math.floor((Date.now() - lastChange) / 1000);
  if (seconds >= 2) status.textContent = `${lastText} (${seconds} s)`;
}, 1000);

async function chooseVersion() {
  const url = new URL(window.location.href);
  const existing = url.searchParams.get("version");
  if (existing) return existing;
  let versions = [
    { id: "alpha_01", title: "Alpha 01", summary: "Julkaistu peli." },
    { id: "minimal", title: "Minimal gameplay loop", summary: "Lyhyt pelisilmukka." },
  ];
  try {
    const res = await fetch(new URL("../versions/index.json", import.meta.url), { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.versions) && data.versions.length) versions = data.versions;
    }
  } catch (err) {
    /* the two buttons above still work */
  }
  if (status) status.hidden = true;
  const box = document.createElement("div");
  box.style.cssText = "font-family: sans-serif; padding: 2rem; max-width: 40rem; color: #f4efe4;";
  const lead = document.createElement("p");
  lead.textContent = "Valitse peliversio.";
  box.appendChild(lead);
  const list = document.createElement("div");
  list.style.cssText = "display: grid; gap: 0.75rem;";
  const picked = new Promise((resolve) => {
    for (const version of versions) {
      const id = String(version.id || "");
      if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$/.test(id)) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.style.cssText = "display: block; width: 100%; text-align: left; padding: 0.9rem 1rem; border-radius: 0.6rem; background: #2a1b16; color: inherit; border: 1px solid #6b5344; cursor: pointer;";
      const title = document.createElement("strong");
      title.textContent = version.title || id;
      title.style.cssText = "display: block; margin-bottom: 0.25rem; color: #c0b083;";
      const summary = document.createElement("span");
      summary.textContent = version.summary || "";
      summary.style.cssText = "display: block; line-height: 1.35;";
      button.append(title, summary);
      button.addEventListener("click", () => resolve(id));
      list.appendChild(button);
    }
  });
  box.appendChild(list);
  document.body.appendChild(box);
  const id = await picked;
  const next = new URL(window.location.href);
  next.searchParams.set("version", id);
  history.replaceState({}, "", next);
  box.remove();
  if (status) status.hidden = false;
  return id;
}

const worker = new Worker(new URL("worker.js?v=nocache", import.meta.url), { type: "module" });
worker.addEventListener("error", (event) => {
  say("Työntekijä kaatui: " + (event.message || "tuntematon virhe"));
  console.error(event);
});
window.__convoyWorker = worker;

let markReady = () => {};
window.__convoyWorkerReady = new Promise((resolve) => {
  markReady = resolve;
});

worker.addEventListener("message", (event) => {
  const msg = event.data || {};
  if (msg.type === "status") say(msg.text || "");
  if (msg.type === "failed") say(msg.text || "Pelin lataus epäonnistui.");
  if (msg.type === "ready") markReady();
});

const version = await chooseVersion();
say("Ladataan versiota " + version + "…");
worker.postMessage({ type: "boot", version });

try {
  await window.__convoyWorkerReady;
  say("Avataan pelilauta…");
  const pageUrl = new URL("index.html", import.meta.url);
  const raw = await fetch(pageUrl).then((res) => {
    if (!res.ok) throw new Error("index.html puuttuu");
    return res.text();
  });
  const rulesRes = await window.convoyTransport("/rules/placeholders");
  if (!rulesRes.ok) throw new Error(await rulesRes.text());
  const rules = await rulesRes.json();
  const parsed = new DOMParser().parseFromString(raw, "text/html");
  document.title = parsed.title;
  for (const link of parsed.querySelectorAll('link[rel="stylesheet"]')) {
    const href = (link.getAttribute("href") || "").replace(/^\/static\//, "");
    const el = document.createElement("link");
    el.rel = "stylesheet";
    el.href = new URL(href, import.meta.url).href;
    document.head.appendChild(el);
  }
  let html = parsed.body.innerHTML.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, "");
  for (const [key, value] of Object.entries(rules)) {
    html = html.split("{" + key + "}").join(String(value));
  }
  const holder = document.createElement("div");
  holder.innerHTML = html;
  const versionGate = holder.querySelector("#versionGate");
  if (versionGate) versionGate.remove();
  const passwordGate = holder.querySelector("#passwordGate");
  if (passwordGate) passwordGate.classList.remove("hidden");
  document.body.replaceChildren(holder);
  const script = document.createElement("script");
  script.src = new URL("app.js?v=pick1", import.meta.url).href;
  document.body.appendChild(script);
} catch (err) {
  say("Pelin lataus epäonnistui: " + err);
}
