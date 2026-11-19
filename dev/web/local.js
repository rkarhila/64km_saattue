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

worker.postMessage({ type: "boot" });

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
  document.body.replaceChildren(holder);
  const script = document.createElement("script");
  script.src = new URL("app.js?v=bot-wait", import.meta.url).href;
  document.body.appendChild(script);
} catch (err) {
  say("Pelin lataus epäonnistui: " + err);
}
