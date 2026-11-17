/** @jest-environment jsdom */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import FoundersStatsModal from "../FoundersStatsModal";

describe("FoundersStatsModal", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("fetches /api/admin/users/founders when opened and filters active vs churned members", async () => {
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({
        generated_at: "2026-11-16T09:50:00Z",
        total_founders: 3,
        total_paid_users: 3,
        founders_count: 2,
        non_founder_paid_count: 1,
        active_count: 2,
        renewed_count: 1,
        first_term_active_count: 1,
        expired_count: 1,
        in_grace_72h_count: 1,
        churned_past_grace_count: 0,
        matured_count: 2,
        due_within_3_days_count: 0,
        overall_retention_rate: 66.7,
        matured_retention_rate: 50,
        total_revenue_egp: 350,
        cohort_50: {
          total: 2,
          active: 1,
          renewed: 1,
          first_term_active: 0,
          expired: 1,
          in_grace_72h: 1,
          matured_total: 2,
          overall_retention_rate: 50,
          matured_retention_rate: 50,
        },
        cohort_100: {
          total: 0,
          active: 0,
          renewed: 0,
          first_term_active: 0,
          expired: 0,
          in_grace_72h: 0,
          matured_total: 0,
          overall_retention_rate: 0,
          matured_retention_rate: 0,
        },
        cohort_regular: {
          total: 1,
          active: 1,
          renewed: 0,
          first_term_active: 1,
          expired: 0,
          in_grace_72h: 0,
          matured_total: 0,
          overall_retention_rate: 100,
          matured_retention_rate: 0,
        },
        cohort_lifetime: { total: 0, active: 0, renewed: 0, first_term_active: 0, expired: 0, in_grace_72h: 0, matured_total: 0, overall_retention_rate: 0, matured_retention_rate: 0 },
        cohort_b2b: { total: 0, active: 0, renewed: 0, first_term_active: 0, expired: 0, in_grace_72h: 0, matured_total: 0, overall_retention_rate: 0, matured_retention_rate: 0 },
        founders_only: { total: 2, active: 1, renewed: 1, first_term_active: 0, expired: 1, in_grace_72h: 1, matured_total: 2, overall_retention_rate: 50, matured_retention_rate: 50 },
        non_founders_paid: { total: 1, active: 1, renewed: 0, first_term_active: 1, expired: 0, in_grace_72h: 0, matured_total: 0, overall_retention_rate: 100, matured_retention_rate: 0 },
        members: [
          {
            user_id: "u-1",
            email: "active.founder@example.com",
            display_name: "Active Founder",
            whatsapp_number: "01000000001",
            telegram_chat_id: "111",
            cohort: "50_EGP",
            is_founder: true,
            joined_at: "2026-10-01T00:00:00Z",
            approved_orders_count: 2,
            total_paid_egp: 100,
            plan_id: "pro",
            sub_status: "active",
            provider: "easykash",
            current_period_start: "2026-11-01T00:00:00Z",
            current_period_end: "2026-12-01T00:00:00Z",
            is_active: true,
            is_lifetime: false,
            in_grace_72h: false,
            status: "renewed_active",
            days_until_expiry: 14.6,
            hours_until_expiry: 350,
          },
          {
            user_id: "u-3",
            email: "regular.200@example.com",
            display_name: "Regular Pro User",
            whatsapp_number: null,
            telegram_chat_id: null,
            cohort: "REGULAR",
            is_founder: false,
            joined_at: "2026-11-12T00:00:00Z",
            approved_orders_count: 1,
            total_paid_egp: 200,
            plan_id: "pro",
            sub_status: "active",
            provider: "kashier",
            current_period_start: "2026-11-12T00:00:00Z",
            current_period_end: "2026-12-12T00:00:00Z",
            is_active: true,
            is_lifetime: false,
            in_grace_72h: false,
            status: "active_first_term",
            days_until_expiry: 26,
            hours_until_expiry: 624,
          },
          {
            user_id: "u-2",
            email: "expired.founder@example.com",
            display_name: "Grace Founder",
            whatsapp_number: null,
            telegram_chat_id: null,
            cohort: "50_EGP",
            is_founder: true,
            joined_at: "2026-10-14T00:00:00Z",
            approved_orders_count: 1,
            total_paid_egp: 50,
            plan_id: "pro",
            sub_status: "canceled",
            provider: "easykash",
            current_period_start: "2026-10-14T00:00:00Z",
            current_period_end: "2026-11-14T18:00:00Z",
            is_active: false,
            is_lifetime: false,
            in_grace_72h: true,
            status: "in_grace_72h",
            days_until_expiry: -1.6,
            hours_until_expiry: -40,
          },
        ],
      }),
    })) as unknown as typeof fetch;

    render(<FoundersStatsModal isOpen onClose={jest.fn()} isAr />);

    await waitFor(() => {
      expect(screen.getByText("active.founder@example.com")).toBeTruthy();
      expect(screen.getByText("regular.200@example.com")).toBeTruthy();
      expect(screen.getByText("expired.founder@example.com")).toBeTruthy();
    });

    expect(global.fetch).toHaveBeenCalledWith("/api/admin/users/founders", { cache: "no-store" });
    expect(screen.getAllByText(/50%/).length).toBeGreaterThan(0);

    // Filter to Founders Only scope pill hides regular non-founder 200 EGP subscriber
    fireEvent.click(screen.getByRole("button", { name: /المؤسسون فقط/i }));
    expect(screen.queryByText("regular.200@example.com")).toBeNull();
    expect(screen.getByText("active.founder@example.com")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /كل من دفع/i }));
    expect(screen.getByText("regular.200@example.com")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /لم يجدد/i }));
    expect(screen.queryByText("active.founder@example.com")).toBeNull();
    expect(screen.getByText("expired.founder@example.com")).toBeTruthy();

    // Clicking a founder opens the stacked FounderUserUsageDialog right on top
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/api/admin/users/u-2")) {
        return {
          ok: true,
          json: async () => ({
            profile: { id: "u-2" },
            subscription: { plan_id: "pro", status: "canceled" },
            bot_subscriptions: [],
            open_positions: [],
            usage: {
              pageViews: 50,
              activeDays: 6,
              totalQuotaChats: 14,
              bonusCreditsRemaining: 10,
              topPages: [{ path: "/scanner/backtests?tab=similarity", views: 9 }],
              chatByDay: [{ date: "2026-11-10", chat_count: 4 }],
              recentQuestions: [{ content: "هات كل التوصيات المفتوحه", created_at: "2026-11-07T16:14:59Z" }],
              lastActiveAt: "2026-11-07T16:14:26Z",
            },
            notifications: {
              telegramReminders: [
                { reminder_days: 3, status: "failed", error: "Telegram API HTTP 403", created_at: "2026-11-10T08:08:00Z" },
              ],
              emailLogs: [
                { id: "e1", message_type: "founder_50_grace_reminder", channel: "email", status: "sent", sent_at: "2026-11-15T12:01:41Z", delivered: true, opened: false, clicked: false, bounced: false },
                { id: "e2", message_type: "unconfirmed_campaign", channel: "email", status: "sent", sent_at: "2026-11-16T08:00:00Z", delivered: false, opened: false, clicked: false, bounced: false },
                { id: "e3", message_type: "failed_campaign", channel: "email", status: "failed", sent_at: "2026-11-16T07:00:00Z", delivered: false, opened: false, clicked: false, bounced: false },
              ],
            },
            payments: { attempts: 2, successful: 1, totalPaid: 50, currency: "EGP", recent: [] },
          }),
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${String(url)}`);
    }) as unknown as typeof fetch;

    fireEvent.click(screen.getByText("expired.founder@example.com"));

    await waitFor(() => {
      expect(screen.getByText("هات كل التوصيات المفتوحه")).toBeTruthy();
      expect(screen.getByText("Telegram API HTTP 403")).toBeTruthy();
      expect(screen.getByText("founder_50_grace_reminder")).toBeTruthy();
    });
    expect(screen.getByText("وصل ولم يُفتح")).toBeTruthy();
    expect(screen.getByText("تم الإرسال")).toBeTruthy();
    expect(screen.getByText("فشل")).toBeTruthy();
    expect(screen.getByText(/بونص تليجرام متبقي: 10/)).toBeTruthy();

    // Verify stale request / abort on closing while a fetch is pending
    const fetchMock = global.fetch as jest.Mock;
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ cache: "no-store", signal: expect.any(AbortSignal) })
    );

    // Closing the stacked usage dialog returns to the modal still open behind it
    fireEvent.click(screen.getByTitle("رجوع للقائمة"));
    expect(screen.queryByText("هات كل التوصيات المفتوحه")).toBeNull();
    expect(screen.getByText(/إحصائيات كل المدفوعين والمؤسسين/)).toBeTruthy();
  });

  it("ignores stale responses when switching founders before an earlier request settles", async () => {
    const FounderUserUsageDialog = (await import("../FounderUserUsageDialog")).default;
    let resolveFirst!: (val: Response) => void;
    const firstPromise = new Promise<Response>((res) => { resolveFirst = res; });
    const firstAbortSignals: AbortSignal[] = [];

    global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.signal) firstAbortSignals.push(init.signal);
      if (String(url).includes("/api/admin/users/u-a")) return firstPromise;
      return Promise.resolve({
        ok: true,
        json: async () => ({
          usage: { recentQuestions: [{ content: "Founder B Question", created_at: "2026-11-16T09:00:00Z" }] },
          notifications: { telegramReminders: [], emailLogs: [] },
          payments: { attempts: 1, successful: 1, totalPaid: 100, recent: [] },
        }),
      } as Response);
    }) as unknown as typeof fetch;

    const baseRow = {
      display_name: null,
      whatsapp_number: null,
      telegram_chat_id: null,
      cohort: "50_EGP" as const,
      is_founder: true,
      joined_at: null,
      approved_orders_count: 1,
      total_paid_egp: 50,
      plan_id: "pro",
      sub_status: "active",
      provider: "easykash",
      current_period_start: null,
      current_period_end: "2026-12-01T00:00:00Z",
      is_active: true,
      is_lifetime: false,
      in_grace_72h: false,
      status: "active_first_term" as const,
      days_until_expiry: 15,
      hours_until_expiry: 360,
    };

    const { rerender } = render(
      <FounderUserUsageDialog founder={{ ...baseRow, user_id: "u-a", email: "a@example.com" }} onClose={jest.fn()} isAr />
    );

    rerender(
      <FounderUserUsageDialog founder={{ ...baseRow, user_id: "u-b", email: "b@example.com" }} onClose={jest.fn()} isAr />
    );

    await waitFor(() => {
      expect(screen.getByText("Founder B Question")).toBeTruthy();
    });

    expect(firstAbortSignals[0]?.aborted).toBe(true);

    // Late resolution of first request must never overwrite Founder B
    resolveFirst({
      ok: true,
      json: async () => ({
        usage: { recentQuestions: [{ content: "Stale Founder A Question", created_at: "2026-11-16T08:00:00Z" }] },
        notifications: { telegramReminders: [], emailLogs: [] },
        payments: { attempts: 1, successful: 1, totalPaid: 50, recent: [] },
      }),
    } as Response);

    await Promise.resolve();
    expect(screen.queryByText("Stale Founder A Question")).toBeNull();
    expect(screen.getByText("Founder B Question")).toBeTruthy();
  });
});
