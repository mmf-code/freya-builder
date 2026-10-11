// Compare the mock with expected answers: node test/check.mjs CASES.json [BASE_URL]
// CASES.json is a list of { name, method, path, query?, body?, rawBody?, headers?, status, response | code }.
// With `code` instead of `response`, only the status and result.code are compared (error bodies carry a fresh guid).
// Without BASE_URL, the script calls the Worker's fetch in this process. With BASE_URL (wrangler dev or the
// deployed URL), it sends the requests over HTTP. Status and JSON body must match exactly.
// It also checks that openapi.js and routes.js name the same operations. Exit 1 on a difference.
import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
import worker from "../src/index.js";
import { openapi } from "../src/openapi.js";
import { routes } from "../src/routes.js";

const [casesPath, base] = process.argv.slice(2);
if (!casesPath) {
  console.error("usage: node test/check.mjs CASES.json [BASE_URL]");
  process.exit(2);
}
const cases = JSON.parse(readFileSync(casesPath, "utf8"));
let failed = 0;
for (const c of cases) {
  const url = new URL((base || "http://mock.local").replace(/\/+$/, "") + c.path);
  for (const [k, v] of Object.entries(c.query || {})) url.searchParams.set(k, v);
  const init = { method: c.method, headers: { "content-type": "application/json", ...(c.headers || {}) } };
  if (c.body !== undefined) init.body = JSON.stringify(c.body);
  if (c.rawBody !== undefined) init.body = c.rawBody;
  const res = base ? await fetch(url, init) : await worker.fetch(new Request(url, init), {});
  const text = await res.text();
  let got;
  try {
    got = JSON.parse(text);
  } catch {
    got = text;
  }
  const ok = res.status === c.status && ("code" in c ? got?.result?.code === c.code : isDeepStrictEqual(got, c.response));
  console.log(`${ok ? "PASS" : "FAIL"} ${c.name || ""} ${c.method} ${c.path} -> ${res.status}`);
  if (!ok) {
    failed++;
    console.log(`  want ${c.status} ${JSON.stringify(c.code ?? c.response)}\n  got  ${res.status} ${JSON.stringify(got)}`);
  }
}
console.log(`${cases.length - failed}/${cases.length} match`);

const METHODS = ["get", "put", "post", "delete", "patch"];
const documented = Object.entries(openapi.paths).flatMap(([p, item]) =>
  METHODS.filter((m) => item[m]).map((m) => `${m.toUpperCase()} ${p}`));
const own = Object.keys(routes).filter((k) => !["GET /health", "POST /oauth2/token"].includes(k));
for (const k of documented.filter((k) => !routes[k])) console.log(`FAIL in openapi.js, no route: ${k}`);
for (const k of own.filter((k) => !documented.includes(k))) console.log(`FAIL route not in openapi.js: ${k}`);
failed += documented.filter((k) => !routes[k]).length + own.filter((k) => !documented.includes(k)).length;
process.exit(failed ? 1 : 0);
