/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import SupportTab from "../SupportTab";

jest.mock("@/lib/supabase/browser", () => ({
    createSupabaseBrowserClient: () => ({
        channel: () => ({ on() { return this; }, subscribe() { return this; } }),
        removeChannel: jest.fn(),
    }),
}));

it("opens support on phones and returns without discarding the selected room or draft", async () => {
    Object.defineProperty(window, "matchMedia", { writable: true, value: jest.fn(() => ({
        matches: true, media: "(max-width: 1023px)", addEventListener: jest.fn(), removeEventListener: jest.fn(),
    })) });
    global.fetch = jest.fn(async (input: any) => ({
        ok: true,
        json: async () => String(input).includes("/messages?") ? {
            messages: [{ id: "message-one", session_id: "support-one", sender: "user", content: "محتاج مساعدة", user_name: "عميل الدعم", created_at: "2026-10-11T10:00:00Z" }],
        } : { chats: [{ session_id: "support-one", user_name: "عميل الدعم", last_message: "محتاج مساعدة", last_message_time: "2026-10-11T10:00:00Z" }] },
    })) as any;
    render(<SupportTab />);
    const list = screen.getByTestId("support-session-list");
    expect(screen.queryByRole("dialog")).toBeNull();
    const customer = await within(list).findByRole("button", { name: /عميل الدعم/ });

    fireEvent.click(customer);
    const pane = await screen.findByRole("dialog");
    expect(await within(pane).findByText("محتاج مساعدة")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Type support reply..."), { target: { value: "مسودة رد" } });
    fireEvent.click(screen.getByRole("button", { name: "رجوع لمحادثات الدعم" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(customer);
    expect(await screen.findByDisplayValue("مسودة رد")).toBeTruthy();
    expect(list.classList.contains("lg:flex")).toBe(true);

    expect((global.fetch as jest.Mock).mock.calls).toHaveLength(2);
});
