/** @jest-environment jsdom */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import UsersEngagementModal from "../UsersEngagementModal";

describe("UsersEngagementModal", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("loads engagement & 350/mo cap stats and opens stacked user usage dialog when clicking a chatter row", async () => {
    global.fetch = jest.fn(async (url: RequestInfo | URL) => {
      if (String(url).includes("/api/admin/users/engagement")) {
        return {
          ok: true,
          json: async () => ({
            generated_at: "2026-11-16T10:00:00Z",
            total_users: 650,
            subscribers: {
              active_paid_count: 19,
              active_paid_pct: 2.9,
              paid_ever_count: 28,
              paid_ever_pct: 4.3,
              active_trial_count: 13,
              active_trial_pct: 2.0,
            },
            interests: {
              chat_messaged_count: 305,
              chat_messaged_pct: 46.9,
              chat_interested_count: 314,
              chat_interested_pct: 48.3,
              recs_interested_count: 235,
              recs_interested_pct: 36.2,
              recs_web_scanner_count: 196,
              recs_web_scanner_pct: 30.2,
              recs_bot_or_vip_count: 78,
              recs_bot_or_vip_pct: 12.0,
            },
            overlap: {
              both_count: 145,
              both_pct: 22.3,
              chat_only_count: 169,
              chat_only_pct: 26.0,
              recs_only_count: 90,
              recs_only_pct: 13.8,
              neither_count: 246,
              neither_pct: 37.8,
            },
            paid_breakdown: {
              active_paid_chat_count: 19,
              active_paid_chat_pct: 100,
              active_paid_recs_count: 19,
              active_paid_recs_pct: 100,
              active_paid_both_count: 19,
              paid_ever_chat_count: 26,
              paid_ever_chat_pct: 92.9,
              paid_ever_recs_count: 28,
              paid_ever_recs_pct: 100,
            },
            chat_limit_350: {
              monthly_limit: 350,
              hit_350_months_count: 0,
              users_ever_hit_350_count: 0,
              approached_150_users_count: 1,
              approached_50_users_count: 5,
              max_month_chats_ever: 172,
              max_month_messages_ever: 98,
              max_month_leader: {
                user_id: "u-top",
                email: "goda01108@gmail.com",
                display_name: "Goda",
                month: "2026-11",
                chats: 172,
              },
              peak_buckets: [
                { id: "zero", label_ar: "0 رسالة", label_en: "0 chats", count: 346, pct: 53.2 },
                { id: "350_plus", label_ar: "وصل 350+ (الحد الأقصى)", label_en: "350+ (Hit Cap)", count: 0, pct: 0 },
              ],
              top_monthly_chatters: [
                {
                  user_id: "u-top",
                  email: "goda01108@gmail.com",
                  display_name: "Goda",
                  month: "2026-11",
                  month_chats: 172,
                  all_time_chats: 183,
                  is_active_paid: true,
                  is_paid_ever: true,
                  pct_of_350: 49.1,
                },
              ],
              top_all_time_chatters: [
                {
                  user_id: "u-top",
                  email: "goda01108@gmail.com",
                  display_name: "Goda",
                  month: "2026-11",
                  month_chats: 172,
                  all_time_chats: 183,
                  is_active_paid: true,
                  is_paid_ever: true,
                  pct_of_350: 49.1,
                },
              ],
            },
          }),
        } as Response;
      }
      if (String(url).includes("/api/admin/users/u-top")) {
        return {
          ok: true,
          json: async () => ({
            usage: {
              pageViews: 40,
              activeDays: 9,
              totalQuotaChats: 183,
              recentQuestions: [{ content: "تحليل سهم TMGH", created_at: "2026-11-15T10:00:00Z" }],
            },
            notifications: { telegramReminders: [], emailLogs: [] },
            payments: { attempts: 1, successful: 1, totalPaid: 50, currency: "EGP", recent: [] },
          }),
        } as Response;
      }
      throw new Error(`Unexpected fetch: ${String(url)}`);
    }) as unknown as typeof fetch;

    render(<UsersEngagementModal isOpen onClose={jest.fn()} isAr />);

    await waitFor(() => {
      expect(screen.getByText(/لم يصل أي مستخدم \(0\)/)).toBeTruthy();
      expect(screen.getByText("goda01108@gmail.com")).toBeTruthy();
    });

    expect(screen.getByText("48.3%")).toBeTruthy();
    expect(screen.getByText("36.2%")).toBeTruthy();

    fireEvent.click(screen.getByText("goda01108@gmail.com"));
    await waitFor(() => {
      expect(screen.getByText("تحليل سهم TMGH")).toBeTruthy();
    });
  });
});
