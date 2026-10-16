/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import SupportTab from "../SupportTab";

jest.mock("@/lib/supabase/browser", () => ({
    createSupabaseBrowserClient: () => ({
        channel: () => ({ on() { return this; }, subscribe() { return this; } }),
        removeChannel: jest.fn(),
    }),
}));

describe("SupportTab Admin Improvements", () => {
    beforeEach(() => {
        jest.useFakeTimers();
        Object.defineProperty(window, "matchMedia", {
            writable: true,
            value: jest.fn(() => ({
                matches: false,
                media: "",
                addEventListener: jest.fn(),
                removeEventListener: jest.fn(),
            })),
        });
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.restoreAllMocks();
    });

    it("verifies debounced user search, fallback display names, PRO badges, and WhatsApp link normalization", async () => {
        const mockUsers = [
            {
                id: "usr-11112222-3333",
                display_name: "أحمد علي",
                email: "ahmed@example.com",
                whatsapp_number: "01012345678",
                subscription: { plan_id: "pro_lifetime", status: "active" },
            },
            {
                id: "usr-44445555-6666",
                username: "mohammed_trader",
                email: "mohammed@example.com",
                whatsapp_number: "+20 11 9876 5432",
                plan: "Pro Annual",
            },
            {
                id: "usr-77778888-9999",
                full_name: "محمود حسن",
                whatsapp_number: "1234567890",
                is_pro: true,
            },
            {
                id: "usr-aaaa-bbbb-cccc",
                email: "fallback_user@example.com",
                plan: "FREE",
            },
            {
                id: "usr-dddd-eeee-ffff",
            },
        ];

        global.fetch = jest.fn(async (input: any) => {
            const url = String(input);
            if (url.includes("/api/admin/support/chats")) {
                return {
                    ok: true,
                    json: async () => ({ chats: [] }),
                };
            }
            if (url.includes("/api/admin/users")) {
                return {
                    ok: true,
                    json: async () => ({ users: mockUsers }),
                };
            }
            if (url.includes("/api/admin/support/messages")) {
                return {
                    ok: true,
                    json: async () => ({ messages: [] }),
                };
            }
            return {
                ok: true,
                json: async () => ({}),
            };
        }) as any;

        render(<SupportTab />);

        // Open "New Chat" modal
        const newChatBtn = screen.getByRole("button", { name: /\+ بدء محادثة مع عميل جديد/ });
        fireEvent.click(newChatBtn);

        // Verify modal opened
        expect(screen.getByText("بدء محادثة جديدة مع عميل")).toBeTruthy();

        // 3. Issue 3: Verify debounced search
        const searchInput = screen.getByPlaceholderText("ابحث بالاسم، الإيميل، أو رقم الهاتف...");
        fireEvent.change(searchInput, { target: { value: "a" } });
        fireEvent.change(searchInput, { target: { value: "ah" } });
        fireEvent.change(searchInput, { target: { value: "ahm" } });

        // Before timer advances 300ms, fetchUsersForChat should only have been called for initial load
        const callsBeforeTimer = (global.fetch as jest.Mock).mock.calls.filter((c) =>
            String(c[0]).includes("/api/admin/users")
        );
        expect(callsBeforeTimer.length).toBe(1);

        // Advance 300ms
        act(() => {
            jest.advanceTimersByTime(300);
        });

        await waitFor(() => {
            const userCalls = (global.fetch as jest.Mock).mock.calls.filter((c) =>
                String(c[0]).includes("search=ahm")
            );
            expect(userCalls.length).toBe(1);
        });

        // 1. Issue 1: Customer Name Fallbacks
        await waitFor(() => {
            // User 1: display_name
            expect(screen.getByText("أحمد علي")).toBeTruthy();
            // User 2: username
            expect(screen.getByText("mohammed_trader")).toBeTruthy();
            // User 3: full_name
            expect(screen.getByText("محمود حسن")).toBeTruthy();
            // User 4: email prefix
            expect(screen.getByText("fallback_user")).toBeTruthy();
            // User 5: ID fallback
            expect(screen.getByText("عميل (usr-dddd)")).toBeTruthy();
        });

        // 2. Issue 2: Pro Status Detection
        const proBadges = screen.getAllByText("PRO");
        // User 1 (sub: pro_lifetime), User 2 (plan: Pro Annual), User 3 (is_pro: true) -> 3 PRO badges
        expect(proBadges.length).toBe(3);

        // 4. Issue 4: Select user with WhatsApp 01012345678 and check formatted link
        const startChatBtns = screen.getAllByText("بدء المحادثة 💬");
        fireEvent.click(startChatBtns[0]); // User 1: أحمد علي

        // Check header WhatsApp link
        await waitFor(() => {
            const waHeaderLinks = screen.getAllByRole("link");
            const formattedLink = waHeaderLinks.find((l) =>
                l.getAttribute("href") === "https://wa.me/201012345678"
            );
            expect(formattedLink).toBeTruthy();
            // Ensure no duplicate 220
            expect(formattedLink?.getAttribute("href")).not.toContain("220");
        });
    });
});
