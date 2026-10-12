import { parsePortfolioTransaction } from "../portfolio-transactions";
const body = {
  action: "sell",
  symbol: "comi",
  quantity: 2,
  price: 15,
  fees: 1,
  occurredAt: "2026-10-01T10:00:00Z",
  requestId: "12345678-1234-1234-1234-123456789012",
};
it("normalizes explicit trade input and preserves request identity", () => {
  expect(
    parsePortfolioTransaction(body, Date.parse("2026-10-12")),
  ).toMatchObject({
    symbol: "COMI",
    quantity: 2,
    price: 15,
    fees: 1,
    requestId: body.requestId,
  });
});
it.each([
  { quantity: null },
  { price: 0 },
  { fees: -1 },
  { quantity: Infinity },
  { occurredAt: "2030-01-01" },
  { requestId: "bad" },
])("rejects incomplete, infinite or future input: %j", (change) => {
  expect(() =>
    parsePortfolioTransaction({ ...body, ...change }, Date.parse("2026-10-12")),
  ).toThrow();
});
it("rejects a withdrawal with missing amount or extra trade fees", () => {
  expect(() =>
    parsePortfolioTransaction(
      { ...body, action: "withdraw", amount: 10 },
      Date.parse("2026-10-12"),
    ),
  ).toThrow("invalid_cash_amount");
});
