/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AIChatbotTab from "../AIChatbotTab";

jest.mock("@/lib/supabase/browser", () => ({
    createSupabaseBrowserClient: () => ({
        channel: () => ({ on() { return this; }, subscribe() { return this; } }),
        removeChannel: jest.fn(),
    }),
}));

describe("AIChatbotTab Trial User Badge & Filter", () => {
    beforeEach(() => {
        Object.defineProperty(window, "matchMedia", {
            writable: true,
            value: jest.fn(() => ({
                matches: false,
                media: "",
                addEventListener: jest.fn(),
                removeEventListener: jest.fn(),
            })),
        });

        const mockLogs = [
            {
                id: "msg-1",
                session_id: "sess-1",
                session_title: "تحليل أموك",
                user_id: "user-trial-123",
                user_name: "تامر عز الدين",
                message: "حلل سهم أموك",
                reply: "تحليل سهم أموك مكتمل",
                created_at: "2026-11-07T10:00:00Z",
                is_pro: false,
                is_trial: true,
            },
            {
                id: "msg-2",
                session_id: "sess-2",
                session_title: "تحليل فوري",
                user_id: "user-pro-456",
                user_name: "محمد كمال",
                message: "حلل سهم فوري",
                reply: "تحليل سهم فوري مكتمل",
                created_at: "2026-11-07T11:00:00Z",
                is_pro: true,
                is_trial: false,
            },
            {
                id: "msg-3",
                session_id: "sess-3",
                session_title: "تحليل عتاقة",
                user_id: "user-free-789",
                user_name: "علي محمود",
                message: "حلل سهم عتاقة",
                reply: "تحليل سهم عتاقة مكتمل",
                created_at: "2026-11-07T12:00:00Z",
                is_pro: false,
                is_trial: false,
            },
        ];

        global.fetch = jest.fn((url: string | URL | Request) => {
            const u = String(url);
            if (u.includes("/api/admin/ai-chatbot/logs")) {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockLogs),
                } as any);
            }
            if (u.includes("/api/admin/ai-chatbot/usage")) {
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ users: {}, complete: true }),
                } as any);
            }
            return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as any);
        });
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it("displays 'تجريبي' badge for trial users and filters users when clicking 'تجريبي'", async () => {
        render(<AIChatbotTab />);

        // Wait for users to load in user list
        await waitFor(() => {
            expect(screen.getAllByText("تامر عز الدين").length).toBeGreaterThan(0);
            expect(screen.getAllByText("محمد كمال").length).toBeGreaterThan(0);
            expect(screen.getAllByText("علي محمود").length).toBeGreaterThan(0);
        });

        const userList = screen.getByTestId("chat-user-list");

        // Verify trial badge is rendered for trial user
        const trialBadges = screen.getAllByText(/تجريبي/);
        expect(trialBadges.length).toBeGreaterThan(0);

        // Filter button for trial
        const trialFilterBtn = screen.getByTitle("تصفية المحادثات للمستخدمين في الفترة التجريبية (Trial)");
        expect(trialFilterBtn).toBeTruthy();

        // Click trial filter button
        fireEvent.click(trialFilterBtn);

        // Only trial user should be visible in the filtered user list
        expect(screen.getAllByText("تامر عز الدين").length).toBeGreaterThan(0);
        expect(screen.queryByText("محمد كمال")).toBeNull();
        expect(screen.queryByText("علي محمود")).toBeNull();

        // Filter button for PRO
        const proFilterBtn = screen.getByTitle("تصفية المحادثات للمستخدمين المشتركين في Pro");
        fireEvent.click(proFilterBtn);

        // Only PRO user should be visible
        expect(screen.getAllByText("محمد كمال").length).toBeGreaterThan(0);
        expect(screen.queryByText("تامر عز الدين")).toBeNull();
        expect(screen.queryByText("علي محمود")).toBeNull();
    });
});
