/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import SupportTab from "../SupportTab";

jest.mock("@/lib/supabase/browser", () => ({
    createSupabaseBrowserClient: () => ({
        channel: () => ({ on() { return this; }, subscribe() { return this; } }),
        removeChannel: jest.fn(),
    }),
}));

it("opens support on phones and returns without discarding the selected room or draft", async () => {
    global.fetch = jest.fn(async (input: any) => ({
        ok: true,
        json: async () => String(input).includes("/messages?") ? {
            messages: [{ id: "message-one", session_id: "support-one", sender: "user", content: "محتاج مساعدة", user_name: "عميل الدعم", created_at: "2026-10-11T10:00:00Z" }],
        } : { chats: [{ session_id: "support-one", user_name: "عميل الدعم", last_message: "محتاج مساعدة", last_message_time: "2026-10-11T10:00:00Z" }] },
    })) as any;
    render(<SupportTab />);
    const list = screen.getByTestId("support-session-list");
    const pane = screen.getByTestId("support-conversation");
    const customer = await within(list).findByRole("button", { name: /عميل الدعم/ });
    expect(pane.classList.contains("hidden")).toBe(true);
    fireEvent.click(customer);
    expect(list.classList.contains("hidden")).toBe(true);
    expect(pane.classList.contains("flex")).toBe(true);
    expect(await within(pane).findByText("محتاج مساعدة")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Type support reply..."), { target: { value: "مسودة رد" } });
    fireEvent.click(screen.getByRole("button", { name: "رجوع لمحادثات الدعم" }));
    expect(list.classList.contains("flex")).toBe(true);
    fireEvent.click(customer);
    expect(screen.getByDisplayValue("مسودة رد")).toBeTruthy();
    expect(list.classList.contains("md:flex")).toBe(true);
    expect(pane.classList.contains("md:flex")).toBe(true);
    expect((global.fetch as jest.Mock).mock.calls).toHaveLength(2);
});
