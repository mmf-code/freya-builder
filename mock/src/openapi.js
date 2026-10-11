// The mock's tool API: the seven services of the service contract of 2026-10-01 (sections 3-5).
// The token endpoint (section 2) is left out: the test environment does not check it, so it is no phone agent tool.
// build.py sets `servers` to the mock URL.
const str = { type: "string" };
const int = { type: "integer" };
const num = { type: "number" };
const date = { type: "string", description: "dd.MM.yyyy" };
const obj = (properties, required) => ({ type: "object", properties, ...(required ? { required } : {}) });

const result = obj({
  guid: str, returnCode: { type: "string", description: '"1" on success, else the error code' }, messageText: str,
  code: str, message: str, type: { type: "string", nullable: true, description: "null, ERROR or WARNING" },
  details: obj({ guid: str, rootCause: { type: "string", nullable: true }, errorOrigin: { type: "string", nullable: true } }),
});
const call = obj({ ani: { type: "string", description: "caller's number" }, lang: { type: "string", example: "tr" } });
const debt = obj({
  statementPaymentStatus: { type: "string", enum: ["HAS_DEBT", "NO_DEBT"] }, transferAmount: num, statementDebt: num,
  minPayment: num, remainingDebt: num, remainingMinPayment: num, currentPeriodExpense: num, totalDebt: num,
  totalDebtPaymentStatus: { type: "string", enum: ["HAS_DEBT", "NO_DEBT"] }, remainAutomaticPaymentAmount: num,
});
const errors = {
  400: { description: "INVALID_ARGUMENTS_ERROR: a required field is missing or empty, or no entry in the test data" },
  404: { description: "not found (code per service, contract section 4)" },
  500: { description: "FBE00099: technical error" },
};

function op(summary, data, required, answer, extra = {}) {
  return {
    post: {
      summary,
      requestBody: {
        required: true,
        content: { "application/json": { schema: obj({ data: obj(data, required), call }, ["data"]) } },
      },
      responses: {
        200: { description: "success", content: { "application/json": { schema: obj({ data: obj(answer), result }) } } },
        ...Object.fromEntries(Object.entries(errors).filter(([k]) => !extra.no || !extra.no.includes(k))),
      },
    },
  };
}

const cardNumber = { type: "string", description: "exactly as cards.list returned it" };
const week = { oneOf: [int, str], description: "1 to 4" };

export const openapi = {
  openapi: "3.0.3",
  info: { title: "Freya Bank voice statement and debt services (test environment mock)", version: "2026-10-01" },
  paths: {
    "/voice/v1/cards.list": op("The customer's cards the assistant may talk about",
      { customerNo: { oneOf: [str, int], description: "8-digit customer number" }, aiFlow: { type: "string", example: "CardOps" } },
      ["customerNo"],
      { cards: { type: "array", items: obj({ cardNumber: str, cardNumberLast4: str, productName: str, status: str, isMainCard: { type: "boolean" } }) },
        validCardsCount: int, exitState: { type: "string", enum: ["1_CARD", "MULTI_CARD"] } }),
    "/voice/v1/cards.balance": op("Statement and due dates, debt per currency. A currency block can be missing.",
      { cardNumber }, ["cardNumber"],
      { cardNumber: str, cardNumberLast4: str, productName: str, statementDate: date, lastPayDate: date,
        nextStatementDate: date, nextLastPayDate: date, debtTL: debt, debtUSD: debt, debtEUR: debt, debtGBP: debt,
        statementPaymentStatus: str, totalDebtPaymentStatus: str, automaticPaymentFlag: { type: "string", enum: ["Y", "N"] } }),
    "/voice/v1/statement.week.get": op("The card's current statement week and day, joint statement info",
      { cardNumber }, ["cardNumber"],
      { cardNumber: str, cardNumberLast4: str, productName: str, statementWeek: int, statementDay: int,
        statementDate: date, lastPayDate: date, nextStatementDate: date, nextLastPayDate: date,
        relationType: { type: "string", description: '"" own statement, "M" main card of a shared statement, "C" linked card' },
        relatedCardNumber: str, relatedCardProductName: str }),
    "/voice/v1/statement.week.decide": op("Preview of the dates with the requested week. Does not change the card.",
      { cardNumber, newStatementWeek: week, statementDay: { type: "integer", description: "current statementDay from statement.week.get" } },
      ["cardNumber", "newStatementWeek"],
      { statementDate: date, statementDueDate: date, statementDay: int, responseCode: int, responseMessage: str },
      { no: ["404"] }),
    "/voice/v1/statement.week.change": op("Changes the statement week",
      { cardNumber, newStatementWeek: week, statementDay: { type: "integer", description: "current statementDay from statement.week.get" } },
      ["cardNumber", "newStatementWeek", "statementDay"],
      { responseCode: int, responseMessage: str, statementWeek: str, statementDay: str, exitState: str },
      { no: ["404"] }),
    "/voice/v1/contact.email.get": op("Registered e-mail and phone",
      { customerNo: { oneOf: [str, int] }, intAddressInfoType: { type: "string", enum: ["E", "P", "B"] } },
      ["customerNo", "intAddressInfoType"],
      { communicationType: str, ibanCountryCode: str, ibanAreaCode: str, ibanPhoneNum: str, ibanEmail: str,
        ttsEmail: str, commGramType: str, exitState: str },
      { no: ["404"] }),
    "/voice/v1/statement.pdf.send": op("Sends the statement PDF by e-mail to emailAddress",
      { customerNo: { oneOf: [str, int] }, cardNumber, currencyType: { type: "string", enum: ["TL", "USD", "EUR", "GBP"] },
        statementDate: { type: "string", description: "dd.MM.yyyy, the statementDate from cards.balance" }, emailAddress: str },
      ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"],
      { exitState: str }),
  },
};
