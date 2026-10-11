// Write the expected answers for every entry of test-customers.json, plus the contract's error cases:
// node test/build-cases.mjs > cases.json, then node test/check.mjs cases.json [BASE_URL].
import testData from "../src/test-customers.json" with { type: "json" };

const call = { ani: "5000000000", lang: "tr" };
const post = (name, svc, data, expect) => ({ name, method: "POST", path: `/voice/v1/${svc}`, body: { data, call }, ...expect });
const exact = (entry) => ({ status: entry.http, response: entry.response });
const cases = [];

for (const c of testData.customers) {
  const s = c.services;
  const no = c.customerNo;
  cases.push(post(`${no} list`, "cards.list", { customerNo: no, aiFlow: "CardOps" }, exact(s["cards.list"])));
  cases.push(post(`${no} list as number`, "cards.list", { customerNo: Number(no) }, exact(s["cards.list"])));
  for (const [card, e] of Object.entries(s["cards.balance"] || {})) cases.push(post(`${no} balance ${card}`, "cards.balance", { cardNumber: card }, exact(e)));
  for (const [card, e] of Object.entries(s["statement.week.get"] || {})) cases.push(post(`${no} week.get ${card}`, "statement.week.get", { cardNumber: card }, exact(e)));
  for (const svc of ["statement.week.decide", "statement.week.change"]) {
    for (const [card, weeks] of Object.entries(s[svc] || {})) {
      for (const [w, e] of Object.entries(weeks)) {
        cases.push(post(`${no} ${svc} ${card} w${w}`, svc, { cardNumber: card, newStatementWeek: Number(w), statementDay: 5 }, exact(e)));
      }
    }
  }
  cases.push(post(`${no} email`, "contact.email.get", { customerNo: Number(no), intAddressInfoType: "E" }, exact(s["contact.email.get"])));
  const card = Object.keys(s["cards.balance"] || {})[0] || "540000******0000";
  const pdf = { customerNo: no, cardNumber: card, currencyType: "TL", statementDate: "05.10.2026", emailAddress: "x@freyabank.example" };
  cases.push(post(`${no} pdf`, "statement.pdf.send", pdf, s["statement.pdf.send"] ? exact(s["statement.pdf.send"]) : { status: 404, code: "FB_IVR_CHANNEL_107" }));
}

const first = testData.customers[0];
const firstCard = Object.keys(first.services["cards.balance"])[0];
const current = Object.keys(first.services["statement.week.get"][firstCard] ? first.services["statement.week.decide"][firstCard] : {});
const currentWeek = ["1", "2", "3", "4"].find((w) => !current.includes(w));
cases.push(
  post("unknown customer list", "cards.list", { customerNo: "11111111" }, { status: 404, code: "FB_IVR_CHANNEL_102" }),
  post("unknown card balance", "cards.balance", { cardNumber: "540000******0000" }, { status: 404, code: "FB_IVR_CHANNEL_120" }),
  post("balance-form number", "cards.balance", { cardNumber: "5400********1234" }, { status: 404, code: "FB_IVR_CHANNEL_120" }),
  post("unknown card week.get", "statement.week.get", { cardNumber: "540000******0000" }, { status: 404, code: "FB_IVR_CHANNEL_121" }),
  post("unknown card decide", "statement.week.decide", { cardNumber: "540000******0000", newStatementWeek: 1 }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("current week decide", "statement.week.decide", { cardNumber: firstCard, newStatementWeek: currentWeek, statementDay: 5 }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("change without statementDay", "statement.week.change", { cardNumber: firstCard, newStatementWeek: 2 }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("empty card number", "cards.balance", { cardNumber: "" }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("email without type", "contact.email.get", { customerNo: first.customerNo }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("unknown customer email", "contact.email.get", { customerNo: "11111111", intAddressInfoType: "E" }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("pdf without address", "statement.pdf.send", { customerNo: first.customerNo, cardNumber: firstCard, currencyType: "TL", statementDate: "05.10.2026" }, { status: 400, code: "INVALID_ARGUMENTS_ERROR" }),
  post("template customer", "cards.list", { customerNo: "{{customerNumber}}" }, exact(first.services["cards.list"])),
  post("template card", "cards.balance", { cardNumber: "{{cardNumber}}" }, exact(first.services["cards.balance"][firstCard])),
  { name: "no data object", method: "POST", path: "/voice/v1/cards.list", body: { customerNo: first.customerNo }, status: 400, code: "INVALID_ARGUMENTS_ERROR" },
  { name: "body not JSON", method: "POST", path: "/voice/v1/cards.list", rawBody: "customerNo=1", status: 400, code: "INVALID_ARGUMENTS_ERROR" },
  { name: "token", method: "POST", path: "/oauth2/token", rawBody: "grant_type=client_credentials&scope=voice.statement",
    headers: { "content-type": "application/x-www-form-urlencoded" }, status: 200,
    response: { access_token: "test-environment-token", token_type: "Bearer", expires_in: 1800 } },
  { name: "GET on a service", method: "GET", path: "/voice/v1/cards.list", status: 404, response: { ok: false, error: "not found" } },
);
console.log(JSON.stringify(cases, null, 1));
