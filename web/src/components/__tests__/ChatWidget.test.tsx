/** @jest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import ChatWidget from "../ChatWidget";
const sendMessage = jest.fn();
let mockUser: {id:string;email:string} | null = {id:"user",email:"test@example.com"};
const chat = {isInitializing: false, accessError: false, retryAccess: jest.fn(),isOpen: true, setIsOpen: jest.fn(), messages: [], sendMessage, stopResponding: jest.fn(), isLoading: false, remainingQuota: 99, sessions: [], selectedModel: "deepseek-chat", setSelectedModel: jest.fn(), setShowUpgradeModal: jest.fn(), isSidebarOpen: false, setIsSidebarOpen: jest.fn()};
jest.mock("@/contexts/ChatContext", () => ({useChat: () => chat, AVAILABLE_AI_MODELS: [{id: "deepseek-chat", name: "DeepSeek"}]}));
jest.mock("@/contexts/AuthContext", () => ({useAuth: () => ({user: mockUser})}));
jest.mock("@/contexts/LanguageContext", () => ({useLanguage: () => ({language: "ar"})}));
let mockPathname = "/";
jest.mock("next/navigation", () => ({useRouter: () => ({push: jest.fn()}), usePathname: () => mockPathname}));
jest.mock("next/image", () => ({__esModule: true, default: ({priority: _priority, ...props}: any) => <img {...props} />}));
jest.mock("@/components/chat/ChatSidebar", () => ({ChatSidebar: () => null}));
jest.mock("@/components/chat/FormattedChatMessage", () => ({FormattedChatMessage: () => null}));
beforeAll(() => { Element.prototype.scrollIntoView = jest.fn(); });
test("ARTORO composer shrinks after clearing long input and after reopening", () => {
    const { rerender } = render(<ChatWidget />);
    const input = screen.getByPlaceholderText("اسأل ARTORO...") as HTMLTextAreaElement;
    expect(screen.getByText("ARTORO")).toBeTruthy();
    expect(screen.getAllByRole("img", {name: "ARTORO V3"}).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", {name: "فتح سجل المحادثات"})).toBeTruthy();
    expect(input.style.height).toBe("40px");
    Object.defineProperty(input, "scrollHeight", {configurable: true, value: 300});
    fireEvent.change(input, {target: {value: "long\nmessage"}});
    expect(input.style.height).toBe("160px");
    fireEvent.change(input, {target: {value: ""}});
    expect(input.style.height).toBe("40px");
    chat.isOpen = false; rerender(<ChatWidget />);
    chat.isOpen = true; rerender(<ChatWidget />);
    expect((screen.getByPlaceholderText("اسأل ARTORO...") as HTMLTextAreaElement).style.height).toBe("40px");
});

test("chat history has one intentional toggle at a time", () => {
    const { rerender } = render(<ChatWidget />);
    expect(screen.getByRole("button", {name: "فتح سجل المحادثات"})).toBeTruthy();

    chat.isSidebarOpen = true;
    rerender(<ChatWidget />);
    expect(screen.queryByRole("button", {name: "فتح سجل المحادثات"})).toBeNull();

    chat.isSidebarOpen = false;
});


test("loading auth and entitlements never flashes login, free quota or a composer", () => {
    chat.isInitializing = true; mockUser = null;
    const {rerender}=render(<ChatWidget />);
    expect(screen.getByRole("status").textContent).toContain("جاري تجهيز الشات");
    expect(screen.queryByText("تسجيل الدخول مطلوب")).toBeNull();
    expect(screen.queryByPlaceholderText("اسأل ARTORO...")).toBeNull();
    mockUser={id:"user",email:"test@example.com"}; rerender(<ChatWidget />);
    expect(screen.queryByText("Unlimited ♾️")).toBeNull();
    expect(screen.queryByPlaceholderText("اسأل ARTORO...")).toBeNull();
    chat.isInitializing=false; rerender(<ChatWidget />);
    expect(screen.getByPlaceholderText("اسأل ARTORO...")).toBeTruthy();
});
test("confirmed guests see login; access failure offers retry rather than login", () => {
    mockUser=null; const {rerender}=render(<ChatWidget />);
    expect(screen.getByText("تسجيل الدخول مطلوب")).toBeTruthy();
    mockUser={id:"user",email:"test@example.com"}; chat.accessError=true; rerender(<ChatWidget />);
    expect(screen.queryByText("تسجيل الدخول مطلوب")).toBeNull();
    expect(screen.queryByPlaceholderText("اسأل ARTORO...")).toBeNull();
    fireEvent.click(screen.getByRole("button",{name:"إعادة المحاولة"}));
    expect(chat.retryAccess).toHaveBeenCalledTimes(1);
    chat.accessError=false;
});

test("scroll-to-bottom button appears when user scrolls up and scrolls to latest message on click", () => {
    (chat as any).messages = [
        { id: "1", role: "user", content: "حلل COMI" },
        { id: "2", role: "assistant", content: "تحليل COMI" },
    ];
    const { container } = render(<ChatWidget />);
    expect(screen.queryByRole("button", { name: "النزول لآخر رسالة" })).toBeNull();

    const scrollContainer = container.querySelector(".neobrutal-grid-bg") as HTMLDivElement;
    Object.defineProperty(scrollContainer, "scrollHeight", { configurable: true, value: 1200 });
    Object.defineProperty(scrollContainer, "clientHeight", { configurable: true, value: 400 });
    Object.defineProperty(scrollContainer, "scrollTop", { configurable: true, value: 100 });
    const scrollToMock = jest.fn();
    scrollContainer.scrollTo = scrollToMock;

    fireEvent.scroll(scrollContainer);
    const btn = screen.getByRole("button", { name: "النزول لآخر رسالة" });
    expect(btn).toBeTruthy();

    fireEvent.click(btn);
    expect(scrollToMock).toHaveBeenCalledWith({ top: 1200, behavior: "smooth" });
    expect(screen.queryByRole("button", { name: "النزول لآخر رسالة" })).toBeNull();
    (chat as any).messages = [];
});

test("quota badge correctly reflects Pro plan quota out of 350 vs Free plan out of 5", () => {
    mockUser = { id: "user", email: "pro@example.com" };
    (chat as any).isPro = true;
    (chat as any).quotaLimit = 350;
    (chat as any).remainingQuota = 84;

    const { rerender } = render(<ChatWidget />);
    expect(screen.getByText("84/350 Left")).toBeTruthy();
    expect(screen.queryByText("84/5 Left")).toBeNull();

    // Free plan test
    (chat as any).isPro = false;
    (chat as any).quotaLimit = 5;
    (chat as any).remainingQuota = 4;
    rerender(<ChatWidget />);
    expect(screen.getByText("4/5 Left")).toBeTruthy();

    // Reset
    (chat as any).isPro = false;
    (chat as any).quotaLimit = 5;
    (chat as any).remainingQuota = 99;
});

test("floating launcher button is not rendered on /chart when closed so it does not block the toolbar", () => {
    mockPathname = "/chart";
    chat.isOpen = false;
    const { rerender } = render(<ChatWidget />);
    expect(screen.queryByRole("button", { name: "افتح ARTORO V3" })).toBeNull();

    mockPathname = "/";
    rerender(<ChatWidget />);
    expect(screen.getByRole("button", { name: "افتح ARTORO V3" })).toBeTruthy();

    chat.isOpen = true;
});

test("active chat renders latest 4 messages and loads 6 older messages per demand", () => {
    const testMessages = Array.from({ length: 12 }, (_, i) => ({
        id: `msg-${i + 1}`,
        role: i % 2 === 0 ? "user" : "assistant",
        content: `Message ${i + 1}`,
    }));
    (chat as any).messages = testMessages;

    render(<ChatWidget />);

    const loadOlderBtn = screen.getByRole("button", { name: "تحميل الرسائل السابقة" });
    expect(loadOlderBtn).toBeTruthy();
    expect(loadOlderBtn.textContent).toContain("8 متبقية");

    fireEvent.click(loadOlderBtn);

    const loadOlderBtnAfterFirst = screen.getByRole("button", { name: "تحميل الرسائل السابقة" });
    expect(loadOlderBtnAfterFirst.textContent).toContain("2 متبقية");

    fireEvent.click(loadOlderBtnAfterFirst);
    expect(screen.queryByRole("button", { name: "تحميل الرسائل السابقة" })).toBeNull();
    (chat as any).messages = [];
});

test("scrolling to top edge or clicking button triggers server-side lazy load when hasMoreHistory is true", async () => {
    const { act } = await import("@testing-library/react");
    jest.useFakeTimers();
    try {
        const loadOlderMessages = jest.fn().mockResolvedValue(4);
        (chat as any).messages = [
            { id: "m-7", role: "user", content: "Q4" },
            { id: "m-8", role: "assistant", content: "A4" },
            { id: "m-9", role: "user", content: "Q5" },
            { id: "m-10", role: "assistant", content: "A5" },
        ];
        (chat as any).hasMoreHistory = true;
        (chat as any).loadOlderMessages = loadOlderMessages;

        const { container } = render(<ChatWidget />);
        const btn = screen.getByRole("button", { name: "تحميل الرسائل السابقة" });
        expect(btn.textContent).toContain("تحميل رسائل أقدم من التاريخ");

        act(() => {
            jest.advanceTimersByTime(450);
        });

        const scrollContainer = container.querySelector(".neobrutal-grid-bg") as HTMLDivElement;
        Object.defineProperty(scrollContainer, "scrollHeight", { configurable: true, value: 1000 });
        Object.defineProperty(scrollContainer, "clientHeight", { configurable: true, value: 400 });
        Object.defineProperty(scrollContainer, "scrollTop", { configurable: true, writable: true, value: 12 });

        await act(async () => {
            fireEvent.scroll(scrollContainer);
            await Promise.resolve();
        });
        expect(loadOlderMessages).toHaveBeenCalledTimes(1);
    } finally {
        (chat as any).messages = [];
        (chat as any).hasMoreHistory = false;
        delete (chat as any).loadOlderMessages;
        jest.useRealTimers();
    }
});

test("switching sessions while loadOlderMessages is in flight resets loading state and ignores stale resolution", async () => {
    const { act } = await import("@testing-library/react");
    let resolvePending!: (v: number) => void;
    const loadOlderMessages = jest.fn(() => new Promise<number>(resolve => { resolvePending = resolve; }));

    try {
        (chat as any).activeSessionId = "sess-1";
        (chat as any).messages = [
            { id: "s1-1", role: "user", content: "S1 Q1" },
            { id: "s1-2", role: "assistant", content: "S1 A1" },
        ];
        (chat as any).hasMoreHistory = true;
        (chat as any).loadOlderMessages = loadOlderMessages;

        const { rerender } = render(<ChatWidget />);
        const btn1 = screen.getByRole("button", { name: "تحميل الرسائل السابقة" }) as HTMLButtonElement;
        fireEvent.click(btn1);
        expect(btn1.disabled).toBe(true);

        // Switch to sess-2 (12 local messages -> initially shows 4 with 8 remaining) before sess-1 resolves
        (chat as any).activeSessionId = "sess-2";
        (chat as any).hasMoreHistory = false;
        (chat as any).messages = Array.from({ length: 12 }, (_, i) => ({
            id: `s2-${i + 1}`,
            role: i % 2 === 0 ? "user" : "assistant",
            content: `S2 Msg ${i + 1}`,
        }));
        rerender(<ChatWidget />);

        const btn2Before = screen.getByRole("button", { name: "تحميل الرسائل السابقة" }) as HTMLButtonElement;
        expect(btn2Before.disabled).toBe(false);
        expect(btn2Before.textContent).toContain("8 متبقية");

        // Stale sess-1 fetch resolves with 6 -> must NOT alter sess-2 visibleCount or stuck-lock button
        await act(async () => {
            resolvePending(6);
            await Promise.resolve();
        });

        const btn2After = screen.getByRole("button", { name: "تحميل الرسائل السابقة" }) as HTMLButtonElement;
        expect(btn2After.disabled).toBe(false);
        expect(btn2After.textContent).toContain("8 متبقية");
    } finally {
        delete (chat as any).activeSessionId;
        (chat as any).messages = [];
        (chat as any).hasMoreHistory = false;
        delete (chat as any).loadOlderMessages;
    }
});

test("mobile layout container uses fixed inset-0 and touch-action pan-y on scroll container", () => {
    const { container } = render(<ChatWidget />);
    const outerContainer = container.firstChild as HTMLElement;
    expect(outerContainer.className).toContain("max-md:fixed");
    expect(outerContainer.className).toContain("max-md:inset-0");
    expect(outerContainer.className).toContain("pt-[env(safe-area-inset-top,0px)]");

    const scrollContainer = container.querySelector(".neobrutal-grid-bg") as HTMLElement;
    expect(scrollContainer.style.touchAction).toBe("pan-y");
    expect(scrollContainer.className).toContain("overscroll-y-contain");
});
