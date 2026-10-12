/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import AIChatbotTab from "../AIChatbotTab";
import UsersTab from "../UsersTab";
import AdminHeader from "../AdminHeader";

jest.mock("@/contexts/LanguageContext", () => ({ useLanguage: () => ({ language: "ar" }) }));
jest.mock("../SupportTab", () => () => <div>دعم العملاء المباشر</div>);
jest.mock("@/components/chat/FormattedChatMessage", () => ({ FormattedChatMessage: ({ content }: any) => <div>{content}</div> }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const users = [{
    id: "user-one", display_name: "عميل الاختبار", email: "long-address@example.test",
    created_at: "2026-10-10T10:00:00Z", subscription: null, bot_subscriptions: [],
}];
const logs = [
    { id: "message-one", user_id: "user-one", user_name: "عميل الاختبار", session_id: "room-one", session_title: "تحليل الأسهم", message: "حلل السهم", reply: "نتيجة التحليل", created_at: "2026-10-11T10:00:00Z", is_pro: true },
    { id: "message-two", user_id: "user-two", user_name: "عميل آخر", session_id: "room-two", message: "مقارنة الأسهم", reply: "نتيجة المقارنة", created_at: "2026-10-11T09:00:00Z", is_pro: false },
];

beforeEach(() => {
    Object.defineProperty(window, "matchMedia", { writable: true, value: jest.fn(() => ({
        matches: true, media: "(max-width: 767px)", addEventListener: jest.fn(), removeEventListener: jest.fn(),
    })) });
    localStorage.clear();
    global.fetch = jest.fn(async (input: any) => ({
        ok: true,
        json: async () => String(input).includes("ai-chatbot/logs") ? logs
            : String(input).includes("ai-chatbot/usage") ? { users: {}, complete: true }
                : { users, total: 101 },
    })) as any;
});
afterEach(() => jest.restoreAllMocks());

it("opens the chosen user in a phone dialog, closes it, and keeps the list filters", async () => {
    render(<AIChatbotTab />);
    const list = await screen.findByTestId("chat-user-list");
    expect(screen.queryByRole("dialog")).toBeNull();
    const customer = within(list).getByRole("button", { name: /عميل آخر/ });
    customer.focus();
    fireEvent.click(customer);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("نتيجة المقارنة")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "رجوع للمستخدمين" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(customer));
    fireEvent.change(screen.getByPlaceholderText("بحث باسم العميل، الإيميل، أو نص..."), { target: { value: "الاختبار" } });
    expect(within(list).queryByRole("button", { name: /عميل آخر/ })).toBeNull();
    fireEvent.click(within(list).getByRole("button", { name: /عميل الاختبار/ }));
    expect(within(await screen.findByRole("dialog")).getByText("نتيجة التحليل")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

it("keeps directory cell labels and edit/search/pagination actions on the mobile cards", async () => {
    render(<UsersTab />);
    const row = (await screen.findByText("long-address@example.test")).closest("tr")!;
    expect(Array.from(row.querySelectorAll("td")).map((td) => td.dataset.label)).toEqual([
        "المستخدم", "خطة الاشتراك", "البوتات", "اللغة", "التسجيل", "نهاية الاشتراك", "إجراءات",
    ]);
    fireEvent.click(within(row).getByTitle("تعديل المستخدم"));
    expect(screen.getByDisplayValue("عميل الاختبار")).toBeTruthy();
    // Editing opens locally; it must not trigger a detail fetch or a mutation.
    expect((global.fetch as jest.Mock).mock.calls.every(([url]) => String(url).includes("page_size="))).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("ابحث باسم المستخدم أو البريد..."), { target: { value: "example.test" } });
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("search=example.test")));
    fireEvent.click(screen.getByRole("button", { name: /التالي/ }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("page=1&")));
});

it("keeps navigation on one mobile row and exposes the active tab", () => {
    const select = jest.fn();
    render(<AdminHeader activeMainTab="users" setActiveMainTab={select} />);
    const current = screen.getByRole("button", { name: "USERS" });
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(current.parentElement?.classList.contains("flex-nowrap")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "SUPPORT & AI" }));
    expect(select).toHaveBeenCalledWith("support");
});
