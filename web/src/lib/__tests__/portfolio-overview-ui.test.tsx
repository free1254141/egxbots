/** @jest-environment jsdom */
import React from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import MyPortfolioSection from "../../app/profile/components/MyPortfolioSection";
import { buildPortfolioPerformance } from "../portfolio-performance";
import { fetchPortfolioPerformance } from "../api";
jest.mock("../api", () => ({ fetchPortfolioPerformance: jest.fn() }));
jest.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "free-owner" }, loading: false }),
}));
jest.mock("../../contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "ar" }),
}));
let snapshot: any;
const refresh = jest.fn(async () => {});
jest.mock("../../contexts/PortfolioContext", () => ({
  usePortfolio: () => ({ snapshot, loading: false, refresh }),
}));
jest.mock("next/dynamic", () => () => () => <div>Comparison chart</div>);
jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
const prices = [
  { date: "2026-10-07", close: 10, adjusted_close: 10 },
  { date: "2026-10-08", close: 11, adjusted_close: 11 },
];
const report = buildPortfolioPerformance(
  [
    {
      id: "p1",
      symbol: "COMI",
      quantity: 10,
      entry_price: 8,
      status: "open",
      sector: "Banks",
    },
  ],
  [],
  { COMI: prices },
  prices,
);
beforeEach(() => {
  jest.clearAllMocks();
  (fetchPortfolioPerformance as jest.Mock).mockResolvedValue(report);
  snapshot = {
    is_pro: false,
    cash_balance: 200,
    market_symbols: [{ symbol: "COMI", name: "CIB" }],
    positions: [
      {
        id: "p1",
        symbol: "COMI",
        quantity: 10,
        entry_price: 8,
        last_price: 11,
        market_value: 110,
        cost_basis: 80,
        profit_value: 30,
        profit_pct: 37.5,
        price_updated_at: "2026-10-08",
      },
    ],
    totals: {
      market_value: 110,
      profit_value: 30,
      profit_pct: 37.5,
      equity: 310,
    },
  };
  global.fetch = jest.fn(async () => ({
    ok: true,
    json: async () => ({ ok: true }),
  })) as any;
  Object.defineProperty(global.crypto, "randomUUID", {
    configurable: true,
    value: () => "12345678-1234-1234-1234-123456789012",
  });
});
it("renders new tools for a Free account and shocks shares while leaving cash unchanged without a write", async () => {
  render(<MyPortfolioSection />);
  await screen.findByText("متاح لكل الحسابات");
  await waitFor(() =>
    expect(screen.getAllByText("11.00").length).toBeGreaterThan(0),
  );
  fireEvent.click(screen.getByRole("button", { name: "−20%" }));
  expect(screen.getByText("22.00")).toBeTruthy();
  expect(screen.getByText("288.00")).toBeTruthy();
  expect(global.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "لوحة أداء المحفظة" }));
  expect(fetchPortfolioPerformance).toHaveBeenCalledTimes(1);
});
it("records an explicit partial sale with execution price and fees, never the implicit last-close sale", async () => {
  render(<MyPortfolioSection />);
  await waitFor(() => expect(fetchPortfolioPerformance).toHaveBeenCalled());
  fireEvent.click(screen.getByTitle("تسجيل بيع"));
  fireEvent.change(screen.getByLabelText("الكمية المنفذة"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("سعر التنفيذ — ج.م"), {
    target: { value: "15" },
  });
  fireEvent.change(screen.getByLabelText("إجمالي العمولات — ج.م"), {
    target: { value: "1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "تأكيد تسجيل العملية" }));
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
  expect(url).toBe("/api/portfolio/transactions");
  expect(JSON.parse(options.body)).toMatchObject({
    action: "sell",
    quantity: "2",
    price: "15",
    fees: "1",
    symbol: "COMI",
  });
});
it("does not convert missing snapshot prices or cost into a green zero profit", async () => {
  snapshot = {
    ...snapshot,
    totals: {
      ...snapshot.totals,
      profit_value: null,
      profit_pct: null,
      market_value: null,
      equity: null,
    },
    positions: [
      {
        ...snapshot.positions[0],
        profit_value: null,
        profit_pct: null,
        last_price: null,
        market_value: null,
      },
    ],
  };
  render(<MyPortfolioSection />);
  await waitFor(() =>
    expect(screen.queryByText("تحميل ملخص الحيازات…")).toBeNull(),
  );
  expect(screen.queryByText("+—")).toBeNull();
  expect(screen.queryByText("+0.00")).toBeNull();
});
