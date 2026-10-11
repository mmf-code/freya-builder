// Filled from the case's service contract after the zip opens. Key: "METHOD /path". A segment {name} is a path
// parameter. A handler gets { body, query, params, headers } and returns { status, body }. status defaults to 200.
// A bare body is not allowed: bank answers can have their own `status` field.
import { customers } from "./data.js";

export const routes = {
  "GET /health": () => ({ body: { ok: true, customers: Object.keys(customers).length } }),
};
