// Filled from the case's service contract after the zip opens. Key: "METHOD /path". A handler gets
// { body, query, headers } and returns a JSON body, or { status, body }.
import { customers } from "./data.js";

export const routes = {
  "GET /health": () => ({ ok: true, customers: Object.keys(customers).length }),
};
