// Bank API mock for the final, on Cloudflare Workers. Not part of the builder.
// The case-specific parts live in ./routes.js (handlers from the service contract), ./data.js (the test customers
// from the case zip) and ./openapi.js (the tool API the builder reads at MOCK_URL/openapi.json). This file only
// routes requests, answers JSON and keeps a best-effort request log per isolate for our own tests. The log is
// served at GET /_log only with the header `x-log-token` equal to the LOG_TOKEN secret (`wrangler secret put
// LOG_TOKEN`); without that secret the route does not exist. Error answers carry no internals.
import { routes } from "./routes.js";
import { openapi } from "./openapi.js";

const log = [];

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });
}

export default {
  async fetch(request, env = {}) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (request.method === "GET" && path === "/openapi.json") return json(openapi);
    if (request.method === "GET" && path === "/_log") {
      const token = env.LOG_TOKEN;
      if (!token || request.headers.get("x-log-token") !== token) return json({ ok: false, error: "not found" }, 404);
      return json(log.slice(-200));
    }
    if (request.method === "GET" && path === "/") return json({ ok: true });

    const handler = routes[`${request.method} ${path}`];
    let body = {};
    if (request.method !== "GET") {
      const text = await request.text();
      try {
        body = text ? JSON.parse(text) : {};
      } catch {
        return json({ ok: false, error: "body is not JSON" }, 400);
      }
    }
    const query = Object.fromEntries(url.searchParams);
    if (!handler) {
      log.push({ t: new Date().toISOString(), method: request.method, path, body, status: 404 });
      return json({ ok: false, error: "not found" }, 404);
    }
    let status = 200;
    let out;
    try {
      const r = await handler({ body, query, headers: request.headers });
      status = r.status ?? 200;
      out = r.body ?? r;
    } catch (e) {
      status = 500;
      out = { ok: false, error: "internal error" };
      log.push({ t: new Date().toISOString(), method: request.method, path, error: String(e) });
    }
    log.push({ t: new Date().toISOString(), method: request.method, path, body, status, out });
    if (log.length > 1000) log.splice(0, log.length - 1000);
    return json(out, status);
  },
};
