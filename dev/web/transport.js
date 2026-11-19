/* Page I/O. The server page uses fetch. The Pyodide page sets
   window.CONVOY_LOCAL and answers the same URLs from a worker. */
(() => {
  function fakeResponse(status, text) {
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => text,
      json: async () => JSON.parse(text),
    };
  }

  async function httpTransport(url, options) {
    return fetch(url, options);
  }

  let nextId = 1;

  function localTransport(url, options) {
    const ready = window.__convoyWorkerReady;
    if (!ready) {
      return Promise.resolve(fakeResponse(503, "Peli ei ole vielä käynnissä."));
    }
    const opts = options || {};
    return ready.then(
      () =>
        new Promise((resolve, reject) => {
          const id = nextId++;
          const worker = window.__convoyWorker;
          const onMessage = (event) => {
            const msg = event.data || {};
            if (msg.id !== id) return;
            worker.removeEventListener("message", onMessage);
            if (msg.error) {
              reject(new Error(msg.error));
              return;
            }
            resolve(fakeResponse(msg.status, msg.text || ""));
          };
          worker.addEventListener("message", onMessage);
          worker.postMessage({
            id,
            url,
            method: opts.method || "GET",
            headers: opts.headers || {},
            body: opts.body || null,
          });
        })
    );
  }

  window.convoyTransport = window.CONVOY_LOCAL ? localTransport : httpTransport;
})();
