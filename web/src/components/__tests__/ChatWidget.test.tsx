/** @jest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import ChatWidget from "../ChatWidget";
const sendMessage = jest.fn();
let mockUser: {id:string;email:string} | null = {id:"user",email:"test@example.com"};
const chat = {isInitializing: false, accessError: false, retryAccess: jest.fn(),isOpen: true, setIsOpen: jest.fn(), messages: [], sendMessage, stopResponding: jest.fn(), isLoading: false, remainingQuota: 99, sessions: [], selectedModel: "deepseek-chat", setSelectedModel: jest.fn(), setShowUpgradeModal: jest.fn(), isSidebarOpen: false, setIsSidebarOpen: jest.fn()};
jest.mock("@/contexts/ChatContext", () => ({useChat: () => chat, AVAILABLE_AI_MODELS: [{id: "deepseek-chat", name: "DeepSeek"}]}));
jest.mock("@/contexts/AuthContext", () => ({useAuth: () => ({user: mockUser})}));
jest.mock("@/contexts/LanguageContext", () => ({useLanguage: () => ({language: "ar"})}));
jest.mock("next/navigation", () => ({useRouter: () => ({push: jest.fn()}), usePathname: () => "/"}));
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
