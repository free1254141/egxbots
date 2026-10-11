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
    localStorage.clear();
    global.fetch = jest.fn(async (input: any) => ({
        ok: true,
        json: async () => String(input).includes("ai-chatbot/logs") ? logs
            : String(input).includes("ai-chatbot/usage") ? { users: {}, complete: true }
                : { users, total: 101 },
    })) as any;
});
afterEach(() => jest.restoreAllMocks());

it("opens the chosen chat on phones, returns to the list, and keeps filtering and desktop panes", async () => {
    render(<AIChatbotTab />);
    const list = await screen.findByTestId("chat-user-list");
    const conversation = screen.getByTestId("chat-conversation");
    expect(list.classList.contains("flex")).toBe(true);
    expect(conversation.classList.contains("hidden")).toBe(true);
    fireEvent.click(within(list).getByRole("button", { name: /عميل آخر/ }));
    expect(list.classList.contains("hidden")).toBe(true);
    expect(conversation.classList.contains("flex")).toBe(true);
    expect(within(conversation).getByText("نتيجة المقارنة")).toBeTruthy();
    expect(list.classList.contains("md:flex")).toBe(true);
    expect(conversation.classList.contains("md:flex")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "رجوع للمستخدمين" }));
    expect(list.classList.contains("flex")).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("بحث باسم العميل، الإيميل، أو نص..."), { target: { value: "الاختبار" } });
    expect(within(list).queryByRole("button", { name: /عميل آخر/ })).toBeNull();
    fireEvent.click(within(list).getByRole("button", { name: /عميل الاختبار/ }));
    expect(within(conversation).getByText("نتيجة التحليل")).toBeTruthy();
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
