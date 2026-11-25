/** @jest-environment jsdom */

import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import MyPortfolioSection from "../components/MyPortfolioSection";

let mockAuthLoading = true;

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-123" }, loading: mockAuthLoading }),
}));

jest.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "ar" }),
}));

const makePos = (sym: string, val: number, pct: number) => ({
  id: sym,
  symbol: sym,
  name: `${sym} Corp`,
  quantity: 100,
  entry_price: 10,
  last_price: val / 100,
  market_value: val,
  cost_basis: 1000,
  profit_value: val - 1000,
  profit_pct: pct,
  price_updated_at: "2026-11-25",
});

const mockSnapshot = {
  ok: true,
  cash_balance: 5000,
  positions: [
    makePos("COMI", 5000, 10),
    makePos("FWRY", 2000, 5),
    makePos("TMGH", 9000, 25),
    makePos("SWDY", 3000, -4),
    makePos("ABUK", 7000, 15),
    makePos("HRHO", 1500, -12),
  ],
  totals: {
    positions_count: 6,
    cost_basis: 6000,
    market_value: 27500,
    profit_value: 21500,
    profit_pct: 8.5,
    equity: 32500,
  },
};

jest.mock("@/contexts/PortfolioContext", () => ({
  usePortfolio: () => ({ snapshot: mockSnapshot, loading: false, refresh: jest.fn(async () => {}) }),
}));

jest.mock("../components/usePortfolioReport", () => ({
  usePortfolioReport: () => ({ report: null, loading: false, error: false, refresh: jest.fn() }),
}));

jest.mock("../components/PortfolioOverview", () => ({
  __esModule: true,
  default: () => <div data-testid="overview-stub" />,
}));

jest.mock("../components/PortfolioPerformanceDashboard", () => ({
  __esModule: true,
  default: () => <div data-testid="perf-stub" />,
}));

jest.mock("../components/PortfolioTransactions", () => ({
  __esModule: true,
  default: () => <div data-testid="tx-stub" />,
}));

jest.mock("../components/PortfolioRebalancerModal", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/components/dividends/PortfolioDividendsCard", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

describe("MyPortfolioSection Hook Safety & Bento Filtering", () => {
  beforeEach(() => {
    mockAuthLoading = true;
  });

  it("transitions cleanly from authLoading=true to authLoading=false without Rules of Hooks errors and filters holdings", () => {
    const { rerender, container } = render(<MyPortfolioSection hideCollapseToggle />);
    expect(container.firstChild).toBeNull();

    mockAuthLoading = false;
    rerender(<MyPortfolioSection hideCollapseToggle />);

    expect(screen.getByText("الحيازات الحالية")).toBeTruthy();
    expect(screen.getByText("COMI")).toBeTruthy();
    expect(screen.getByText("HRHO")).toBeTruthy();

    const search = screen.getByPlaceholderText("بحث بالرمز...");
    fireEvent.change(search, { target: { value: "HRH" } });
    expect(screen.getByText("HRHO")).toBeTruthy();
    expect(screen.queryByText("COMI")).toBeNull();
  });
});
