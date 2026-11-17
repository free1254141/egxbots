/** @jest-environment jsdom */
import React, { act } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import TrialSuccessModal from "../TrialSuccessModal";
import {
  TRIAL_SUCCESS_EVENT,
  TRIAL_AUTOSTART_EVENT,
  triggerTrialSuccessModal,
} from "@/lib/trial-onboarding";

// Mock language context
jest.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({
    language: "ar",
  }),
}));

describe("TrialSuccessModal", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("does not render when closed", () => {
    const { container } = render(<TrialSuccessModal />);
    expect(container.firstChild).toBeNull();
  });

  it("opens upon receiving TRIAL_SUCCESS_EVENT and displays VIP invite link", () => {
    render(<TrialSuccessModal />);

    act(() => {
      triggerTrialSuccessModal({
        invite_link: "https://t.me/+mock_vip_link",
        expires_at: "2026-11-20T00:00:00.000Z",
        telegram_sent: true,
      });
    });

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(/أهلاً بك في باقة Stokscan Pro/i)).toBeTruthy();

    const joinBtn = screen.getByRole("link", { name: /انضم الآن لقناة توصيات VIP/i });
    expect(joinBtn).toBeTruthy();
    expect(joinBtn.getAttribute("href")).toBe("https://t.me/+mock_vip_link");

    expect(screen.getByText(/تم إرسال رابط القناة أيضاً إلى محادثتك على بوت تليجرام/i)).toBeTruthy();
  });

  it("dispatches TRIAL_AUTOSTART_EVENT when AI chat button is clicked", () => {
    const autostartSpy = jest.fn();
    window.addEventListener(TRIAL_AUTOSTART_EVENT, autostartSpy);

    render(<TrialSuccessModal />);

    act(() => {
      triggerTrialSuccessModal({
        invite_link: "https://t.me/+mock_vip_link",
        expires_at: "2026-11-20T00:00:00.000Z",
      });
    });

    const aiChatBtn = screen.getByRole("button", { name: /ابدأ تجربة شات الذكاء الاصطناعي/i });
    act(() => {
      fireEvent.click(aiChatBtn);
    });

    expect(autostartSpy).toHaveBeenCalledTimes(1);
    window.removeEventListener(TRIAL_AUTOSTART_EVENT, autostartSpy);
  });
});
