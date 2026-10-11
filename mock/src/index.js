// Bank API mock for the final, on Cloudflare Workers. It is not part of the builder.
// The case-specific parts are in ./routes.js (handlers from the service contract and the test customers) and
// ./openapi.js (the tool API that the builder reads at MOCK_URL/openapi.json).
// This file routes requests, answers JSON and keeps a request log per isolate for our own tests.
// GET /_log serves the log only when the header `x-log-token` equals the LOG_TOKEN secret
// (`wrangler secret put LOG_TOKEN`). Without that secret, the route does not exist. Error answers carry no internals.
import { routes } from "./routes.js";
import { openapi } from "./openapi.js";

const log = [];

function record(entry) {
  log.push({ t: new Date().toISOString(), ...entry });
  if (log.length > 1000) log.splice(0, log.length - 1000);
}

function decode(segment) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

// An exact key wins over a template. A {name} segment matches one non-empty segment.
function match(method, path) {
  const exact = routes[`${method} ${path}`];
  if (exact) return { handler: exact, params: {} };
  const parts = path.split("/");
  for (const [key, handler] of Object.entries(routes)) {
    const [m, tpl] = key.split(" ");
    const segs = tpl.split("/");
    if (m !== method || segs.length !== parts.length) continue;
    const params = {};
    const ok = segs.every((s, i) => {
      if (!/^\{\w+\}$/.test(s)) return s === parts[i];
      if (!parts[i]) return false;
      params[s.slice(1, -1)] = decode(parts[i]);
      return true;
    });
    if (ok) return { handler, params };
  }
  return { handler: null, params: {} };
}

const CORS = { "access-control-allow-origin": "*" };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "content-type": "application/json; charset=utf-8" } });
}

export default {
  async fetch(request, env = {}) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...CORS, "access-control-allow-methods": "GET, POST, OPTIONS", "access-control-allow-headers": "*" } });
    }
    if (request.method === "GET" && path === "/openapi.json") return json(openapi);
    if (request.method === "GET" && path === "/_log") {
      const token = env.LOG_TOKEN;
      if (!token || request.headers.get("x-log-token") !== token) return json({ ok: false, error: "not found" }, 404);
      return json(log.slice(-200));
    }
    if (request.method === "GET" && path === "/") return json({ ok: true });

    const { handler, params } = match(request.method, path);
    if (!handler) {
      record({ method: request.method, path, status: 404 });
      return json({ ok: false, error: "not found" }, 404);
    }
    // A body that is not JSON (the token request is a form) reaches the handler as null.
    const body = request.method === "GET" ? null : await request.json().catch(() => null);
    const query = Object.fromEntries(url.searchParams);
    let status, out, error;
    try {
      ({ status = 200, body: out } = await handler({ body, query, params, headers: request.headers }));
      if (!Number.isInteger(status) || status < 200 || status > 599) throw new Error(`bad status ${status}`);
    } catch (e) {
      [status, out, error] = [500, { ok: false, error: "internal error" }, String(e)];
    }
    record({ method: request.method, path, ua: request.headers.get("user-agent"), body, status, out, error });
    return json(out, status);
  },
};
