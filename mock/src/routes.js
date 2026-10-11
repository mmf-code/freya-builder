// Freya Bank voice services from the service contract of 2026-10-01 (case folder, sources/documents/).
// Every answer comes from test-customers.json (case folder, test-environment/), copied unchanged.
// Contract section 6: a customer, card or week without an entry gets the 404 of that service from section 4.
// A service without a 404 in section 4 answers 400 INVALID_ARGUMENTS_ERROR.
// A handler returns { status, body }. A bare body is not allowed: bank answers can have their own `status` field.
import testData from "./test-customers.json" with { type: "json" };

const ORIGIN = "ivr-gateway-test:ivr-channel-v0";
const NOT_FOUND = "com.freyabank.ivrgateway.ivrchannel.rest.exception.NotFoundException";
const CARD_SERVICES = ["cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change"];

const byCustomer = new Map(testData.customers.map((c) => [c.customerNo, c.services]));
const byCard = new Map();
for (const c of testData.customers) {
  for (const svc of CARD_SERVICES) for (const card of Object.keys(c.services[svc] || {})) byCard.set(card, c.services);
}
const firstCustomer = testData.customers[0];
const firstCard = Object.keys(firstCustomer.services["cards.balance"])[0];

function result(code, message, type, rootCause) {
  const guid = crypto.randomUUID().replaceAll("-", "");
  return { guid, returnCode: code, messageText: message, code, message, type, details: { guid, rootCause, errorOrigin: ORIGIN } };
}

const invalid = (message) => ({
  status: 400,
  body: { result: result("INVALID_ARGUMENTS_ERROR", message, "ERROR", "InvalidArgumentsException") },
});
const notFound = (code, message) => ({ status: 404, body: { result: result(code, message, "WARNING", NOT_FOUND) } });

const NOT_FOUND_ANSWER = {
  "cards.list": () => notFound("FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."),
  "cards.balance": () => notFound("FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"),
  "statement.week.get": () => notFound("FB_IVR_CHANNEL_121", "Kart bulunamadı"),
  "statement.pdf.send": () => notFound("FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"),
};

// Fields that must be present, in the order of the contract's request examples (aiFlow is not checked in test).
const REQUIRED = {
  "cards.list": ["customerNo"],
  "cards.balance": ["cardNumber"],
  "statement.week.get": ["cardNumber"],
  "statement.week.decide": ["cardNumber", "newStatementWeek"],
  "statement.week.change": ["cardNumber", "newStatementWeek", "statementDay"],
  "contact.email.get": ["customerNo", "intAddressInfoType"],
  "statement.pdf.send": ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"],
};
const LABEL = { customerNo: "customer number", cardNumber: "card number" };

const text = (v) => (v === undefined || v === null ? "" : String(v).trim());

// The Freya panel's "Test API Request" sends a variable unfilled, e.g. "{{customerNumber}}" (cloudflare-mock README).
// Such a value gets the first test customer's record, as in the case's example Worker.
const isTemplate = (v) => typeof v === "string" && (v.startsWith("{{") || v.startsWith("%7B%7B"));

async function answer(entry) {
  if (entry.delaySeconds) await new Promise((r) => setTimeout(r, entry.delaySeconds * 1000));
  return { status: entry.http, body: entry.response };
}

function service(svc) {
  return async ({ body }) => {
    const data = body && typeof body.data === "object" && body.data !== null ? body.data : null;
    if (!data) return invalid("data cannot be empty");
    for (const f of REQUIRED[svc]) if (!text(data[f])) return invalid(`${LABEL[f] || f} cannot be empty`);
    const missing = NOT_FOUND_ANSWER[svc] || (() => invalid(`${CARD_SERVICES.includes(svc) ? "card number" : "customer number"} is not valid`));

    if (!CARD_SERVICES.includes(svc)) {
      const no = isTemplate(data.customerNo) ? firstCustomer.customerNo : text(data.customerNo);
      const entry = byCustomer.get(no)?.[svc];
      return entry ? answer(entry) : missing();
    }
    const card = isTemplate(data.cardNumber) ? firstCard : text(data.cardNumber);
    const perCard = byCard.get(card)?.[svc]?.[card];
    if (!perCard) return missing();
    if (svc === "cards.balance" || svc === "statement.week.get") return answer(perCard);
    const week = isTemplate(data.newStatementWeek) ? Object.keys(perCard)[0] : text(data.newStatementWeek);
    return perCard[week] ? answer(perCard[week]) : invalid("newStatementWeek is not valid");
  };
}

export const routes = {
  "GET /health": () => ({ body: { ok: true, customers: byCustomer.size } }),
  // Contract section 2. The test environment does not check the token; the mock gives one so a flow can send it.
  "POST /oauth2/token": () => ({ body: { access_token: "test-environment-token", token_type: "Bearer", expires_in: 1800 } }),
  ...Object.fromEntries(Object.keys(REQUIRED).map((svc) => [`POST /voice/v1/${svc}`, service(svc)])),
};
