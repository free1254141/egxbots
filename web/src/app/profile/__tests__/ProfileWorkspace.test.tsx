/** @jest-environment jsdom */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProfilePage from "../page";
import PortfolioTransactions from "../components/PortfolioTransactions";
import { fetchUserQuotaCached } from "@/lib/user-quota-client";

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockRefreshProInvite = jest.fn(async () => {});
const mockUpdateSymbol = jest.fn(async () => true);
const mockRemoveSymbol = jest.fn(async () => true);

let mockMarketState = {
  isSaudi: false,
  isGccChatOnly: false,
  currencyLabel: "ج.م",
};

let mockInviteState = {
  is_pro: true,
  bot_active: true,
  invite_link: "https://t.me/+egxvip",
  saudi_invite_link: "https://t.me/+tasivip",
  telegram_chat_id: "12345",
  invite_expires_at: "2026-12-31T00:00:00Z",
};

let mockWatchlist = [
  { id: "w1", symbol: "COMI", name: "CIB Egypt", metadata: { exchange: "EGX" } },
  { id: "w2", symbol: "FWRY", name: "Fawry", metadata: { exchange: "EGX" } },
  { id: "w3", symbol: "TMGH", name: "Talaat Moustafa", metadata: { exchange: "EGX" } },
  { id: "w4", symbol: "SWDY", name: "Elsewedy Electric", metadata: { exchange: "EGX" } },
  { id: "w5", symbol: "ABUK", name: "Abu Qir", metadata: { exchange: "EGX" } },
];

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, prefetch: _prefetch, ...rest }: any) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "user-123", email: "trader@example.com", user_metadata: { full_name: "Test Trader" } },
    loading: false,
  }),
}));

jest.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "ar", t: (k: string) => k }),
}));

jest.mock("@/contexts/MarketContext", () => ({
  useMarket: () => mockMarketState,
}));

jest.mock("@/contexts/WatchlistContext", () => ({
  useWatchlist: () => ({
    watchlist: mockWatchlist,
    updateSymbol: mockUpdateSymbol,
    removeSymbol: mockRemoveSymbol,
  }),
}));

jest.mock("@/contexts/TelegramProContext", () => ({
  useTelegramPro: () => ({
    invite: mockInviteState,
    loading: false,
    error: null,
    refresh: mockRefreshProInvite,
  }),
}));

jest.mock("@/contexts/PortfolioContext", () => ({
  usePortfolio: () => ({
    snapshot: {
      ok: true,
      cash_balance: 10000,
      positions: [{ id: "p1", symbol: "COMI" }, { id: "p2", symbol: "FWRY" }],
      totals: { equity: 85000, profit_pct: 12.4, market_value: 75000, profit_value: 8300, cost_basis: 66700, positions_count: 2 },
    },
    loading: false,
    refresh: jest.fn(async () => {}),
  }),
}));

jest.mock("@/lib/supabase/browser", () => ({
  createSupabaseBrowserClient: () => ({
    from: () => ({
      select: () => ({
        eq: () => ({
          maybeSingle: async () => ({
            data: { username: "TestTrader", telegram_chat_id: "12345", whatsapp_number: "01012345678" },
          }),
        }),
      }),
    }),
  }),
}));

jest.mock("@/lib/user-quota-client", () => ({
  fetchUserQuotaCached: jest.fn(),
  invalidateUserQuotaCache: jest.fn(),
}));

jest.mock("../components/MyPortfolioSection", () => ({
  __esModule: true,
  default: () => <div data-testid="mock-portfolio-section">MyPortfolioSection</div>,
}));

jest.mock("../components/ScheduledAutomationsCard", () => ({
  __esModule: true,
  default: ({ isPro }: { isPro?: boolean }) => (
    <div data-testid="mock-automations-card">ScheduledAutomationsCard:{String(isPro)}</div>
  ),
}));

jest.mock("../components/PlanQuotaCard", () => ({
  __esModule: true,
  default: () => <div data-testid="mock-plan-quota-card">PlanQuotaCard</div>,
}));

jest.mock("../components/FoundingMemberBanner", () => ({
  __esModule: true,
  default: () => <div data-testid="mock-founding-banner" />,
}));

jest.mock("../components/PaymentWelcomeModal", () => ({
  __esModule: true,
  default: () => null,
}));

const mockedFetchQuota = fetchUserQuotaCached as jest.Mock;

describe("ProfilePage Workspace Tabs, Capability Isolation & Capped Lists", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.location.hash = "";
    window.HTMLElement.prototype.scrollIntoView = jest.fn();
    mockMarketState = { isSaudi: false, isGccChatOnly: false, currencyLabel: "ج.م" };
    mockInviteState = {
      is_pro: true,
      bot_active: true,
      invite_link: "https://t.me/+egxvip",
      saudi_invite_link: "https://t.me/+tasivip",
      telegram_chat_id: "12345",
      invite_expires_at: "2026-12-31T00:00:00Z",
    };
    mockedFetchQuota.mockResolvedValue({
      ok: true,
      plan: {
        id: "pro",
        label: "PRO",
        is_pro: true,
        has_chat_pro: true,
        has_vip_access: true,
        is_founding_member: false,
      },
      quota: {
        chat_messages: { used: 12, limit: 350, remaining: 338, percent: 3, period: "monthly" },
        portfolio_stocks: { used: 2, limit: 15, remaining: 13, percent: 13 },
        signals: { delay_days: 0, is_instant: true },
      },
    });
  });

  it("renders Portfolio tab by default and switches tabs cleanly without stacking sections", async () => {
    render(<ProfilePage />);

    await waitFor(() => expect(screen.getByTestId("mock-portfolio-section")).toBeTruthy());
    expect(screen.queryByTestId("mock-automations-card")).toBeNull();
    expect(screen.queryByTestId("mock-plan-quota-card")).toBeNull();

    // Switch to Automations tab
    fireEvent.click(screen.getByRole("tab", { name: /الأتمتة اليومية/ }));
    expect(screen.getByTestId("mock-automations-card")).toBeTruthy();
    expect(screen.queryByTestId("mock-portfolio-section")).toBeNull();

    // Switch to Watchlist tab & filter >4 items
    fireEvent.click(screen.getByRole("tab", { name: /قائمة المراقبة/ }));
    expect(screen.getByText("COMI")).toBeTruthy();
    expect(screen.getByText("ABUK")).toBeTruthy();

    const searchInput = screen.getByPlaceholderText("ابحث داخل قائمة المراقبة...");
    fireEvent.change(searchInput, { target: { value: "ABU" } });
    expect(screen.getByText("ABUK")).toBeTruthy();
    expect(screen.queryByText("COMI")).toBeNull();

    // Switch to Account & Telegram tab
    fireEvent.click(screen.getByRole("tab", { name: /الحساب والباقة وتليجرام/ }));
    expect(screen.getByTestId("mock-plan-quota-card")).toBeTruthy();
    expect(screen.getByText(/بوت التليجرام الخاص/)).toBeTruthy();
  });

  it("activates the Account & Telegram tab automatically when #telegram hash is present", async () => {
    window.location.hash = "#telegram";
    render(<ProfilePage />);

    await waitFor(() => expect(screen.getByTestId("mock-plan-quota-card")).toBeTruthy());
    expect(screen.queryByTestId("mock-portfolio-section")).toBeNull();
  });

  it("fails closed before quota resolves and isolates chat_only from VIP channel invites", async () => {
    let resolveQuota: (val: any) => void;
    mockedFetchQuota.mockImplementationOnce(
      () =>
        new Promise((res) => {
          resolveQuota = res;
        })
    );

    render(<ProfilePage />);
    fireEvent.click(screen.getByRole("tab", { name: /الأتمتة اليومية/ }));
    // Before quota resolves, fail closed: ScheduledAutomationsCard must receive isPro=false even when proInvite.is_pro is true
    expect(screen.getByTestId("mock-automations-card").textContent).toBe("ScheduledAutomationsCard:false");

    // Resolve as chat_only -> Automations enabled, VIP links hidden
    resolveQuota!({
      ok: true,
      plan: { id: "chat_only", is_pro: true, has_chat_pro: true, has_vip_access: false },
      quota: { chat_messages: { used: 5, limit: 350, percent: 1 }, portfolio_stocks: { used: 0, limit: 15, percent: 0 } },
    });

    await waitFor(() =>
      expect(screen.getByTestId("mock-automations-card").textContent).toBe("ScheduledAutomationsCard:true")
    );

    fireEvent.click(screen.getByRole("tab", { name: /الحساب والباقة وتليجرام/ }));
    expect(screen.queryByText("https://t.me/+egxvip")).toBeNull();
    expect(screen.queryByText("دخول قناة Pro")).toBeNull();
  });

  it("isolates vip_only from ScheduledAutomationsCard while allowing VIP channel links", async () => {
    mockedFetchQuota.mockResolvedValueOnce({
      ok: true,
      plan: { id: "vip_only", is_pro: true, has_chat_pro: false, has_vip_access: true },
      quota: { chat_messages: { used: 1, limit: 10, percent: 10 }, portfolio_stocks: { used: 0, limit: 5, percent: 0 } },
    });

    render(<ProfilePage />);
    await waitFor(() => expect(mockedFetchQuota).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("tab", { name: /الأتمتة اليومية/ }));
    expect(screen.getByTestId("mock-automations-card").textContent).toBe("ScheduledAutomationsCard:false");

    fireEvent.click(screen.getByRole("tab", { name: /الحساب والباقة وتليجرام/ }));
    expect(screen.getByText("https://t.me/+egxvip")).toBeTruthy();
  });

  it("hides Telegram channel promos and bot warning strip in GCC chat-only mode", async () => {
    mockMarketState = { isSaudi: false, isGccChatOnly: true, currencyLabel: "د.إ" };
    mockInviteState = { ...mockInviteState, bot_active: false };
    window.location.hash = "#telegram";

    render(<ProfilePage />);

    await waitFor(() => expect(screen.getByTestId("mock-plan-quota-card")).toBeTruthy());
    expect(screen.queryByText(/قنوات إشارات التليجرام/)).toBeNull();
    expect(screen.queryByText(/فعّل بوت التليجرام في الخاص/)).toBeNull();
    expect(screen.getByText(/هذا السوق مخصص حالياً لمساعد الذكاء الاصطناعي/)).toBeTruthy();
  });

  it("caps PortfolioTransactions to 4 items by default and expands when requested", () => {
    const events = Array.from({ length: 6 }, (_, i) => ({
      id: `ev-${i + 1}`,
      event_type: "portfolio_buy",
      event_at: `2026-11-2${i}T10:00:00Z`,
      payload: { symbol: `SYM${i + 1}`, quantity: 100, price: 10 + i },
    }));

    render(
      <PortfolioTransactions
        snapshot={null}
        events={events as any}
        isAr
        onSaved={jest.fn(async () => {})}
      />
    );

    expect(screen.getByText(/SYM1/)).toBeTruthy();
    expect(screen.getByText(/SYM4/)).toBeTruthy();
    expect(screen.queryByText(/SYM5/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "عرض كل العمليات (6)" }));
    expect(screen.getByText(/SYM5/)).toBeTruthy();
    expect(screen.getByText(/SYM6/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "عرض أقل" }));
    expect(screen.queryByText(/SYM5/)).toBeNull();
  });
});
