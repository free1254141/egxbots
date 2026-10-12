/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import MobileConversation from "../MobileConversation";

it("keeps the conversation inline on desktop without a modal", () => {
    Object.defineProperty(window, "matchMedia", { writable: true, value: jest.fn(() => ({
        matches: false, addEventListener: jest.fn(), removeEventListener: jest.fn(),
    })) });
    render(<MobileConversation open onClose={jest.fn()} title="Customer" closeLabel="Close" className="flex-1" testId="conversation">Messages</MobileConversation>);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("conversation").textContent).toBe("Messages");
});

it("closes a mobile dialog with Escape and unsubscribes from screen-size changes", () => {
    const remove = jest.fn();
    Object.defineProperty(window, "matchMedia", { writable: true, value: jest.fn(() => ({
        matches: true, addEventListener: jest.fn(), removeEventListener: remove,
    })) });
    const close = jest.fn();
    const view = render(<MobileConversation open onClose={close} title="Customer" closeLabel="Close" className="flex-1" testId="conversation">Messages</MobileConversation>);
    expect(screen.getByRole("dialog").textContent).toContain("Messages");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(remove).toHaveBeenCalledWith("change", expect.any(Function));
});
