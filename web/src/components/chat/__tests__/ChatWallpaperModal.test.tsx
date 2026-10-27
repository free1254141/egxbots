/** @jest-environment jsdom */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatWallpaperModal } from "../ChatWallpaperModal";
import {
  CHAT_WALLPAPERS,
  DEFAULT_WALLPAPER_ID,
  DEFAULT_WALLPAPER_OPACITY,
  getSavedWallpaperConfig,
  saveWallpaperConfig,
} from "@/lib/chat-wallpapers";

describe("Chat Wallpaper Settings", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it("loads default wallpaper configuration when localStorage is empty", () => {
    const config = getSavedWallpaperConfig();
    expect(config.id).toBe(DEFAULT_WALLPAPER_ID);
    expect(config.opacity).toBe(DEFAULT_WALLPAPER_OPACITY);
  });

  it("persists and retrieves wallpaper configuration in localStorage", () => {
    saveWallpaperConfig("trading_doodle", 70);
    const config = getSavedWallpaperConfig();
    expect(config.id).toBe("trading_doodle");
    expect(config.opacity).toBe(70);
  });

  it("renders wallpaper modal with presets when open", () => {
    const onApply = jest.fn();
    const onClose = jest.fn();

    render(
      <ChatWallpaperModal
        isOpen={true}
        onClose={onClose}
        currentId="grid"
        currentOpacity={80}
        onApply={onApply}
        isAr={true}
      />
    );

    expect(screen.getByText("خلفية المحادثة (ورق حائط)")).toBeTruthy();
    expect(screen.getByText("رسومات وأنماط")).toBeTruthy();
    expect(screen.getByText("ألوان داكنة")).toBeTruthy();
    expect(screen.getByText("صورة مخصصة")).toBeTruthy();
    expect(screen.getByText("رسومات البورصة والتداول")).toBeTruthy();
  });

  it("selects wallpaper and applies it on save", () => {
    const onApply = jest.fn();
    const onClose = jest.fn();

    render(
      <ChatWallpaperModal
        isOpen={true}
        onClose={onClose}
        currentId="grid"
        currentOpacity={80}
        onApply={onApply}
        isAr={true}
      />
    );

    const tradingDoodleBtn = screen.getByText("رسومات البورصة والتداول").closest("button");
    expect(tradingDoodleBtn).toBeTruthy();
    fireEvent.click(tradingDoodleBtn!);

    const saveBtn = screen.getByText("تطبيق وحفظ");
    fireEvent.click(saveBtn);

    expect(onApply).toHaveBeenCalledWith("trading_doodle", 80, undefined);
    expect(onClose).toHaveBeenCalled();

    const stored = getSavedWallpaperConfig();
    expect(stored.id).toBe("trading_doodle");
  });
});
