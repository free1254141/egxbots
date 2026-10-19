/** @jest-environment jsdom */
import React from "react";
import "@testing-library/jest-dom";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SocialReportsTab from "../SocialReportsTab";

// Mock sonner toast
jest.mock("sonner", () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const mockData = {
  bucket: "social-reports",
  stats: {
    total_images: 2,
    total_bytes: 204800,
    total_mb: 0.2,
    total_dates: 1,
    latest_date: "2026-10-19",
  },
  dates: ["2026-10-19"],
  images: [
    {
      id: "img-1",
      name: "stock-v4-abc.png",
      path: "2026-10-19/stock-v4-abc.png",
      session_date: "2026-10-19",
      kind: "stock",
      symbol: "CCAP",
      url: "https://mock.supabase.co/stock.png",
      size: 102400,
      created_at: "2026-10-19T14:00:00Z",
      last_modified: "2026-10-19T14:00:00Z",
      social_title: "تحليل سهم القلعة",
      social_caption: "تفاصيل تحليل سهم القلعة",
      social_hashtags: ["#EGXBOTS", "#CCAP"],
      content: "تقرير كامل",
      image_status: "ready",
    },
    {
      id: "img-2",
      name: "market-v4-def.png",
      path: "2026-10-19/market-v4-def.png",
      session_date: "2026-10-19",
      kind: "market",
      symbol: null,
      url: "https://mock.supabase.co/market.png",
      size: 102400,
      created_at: "2026-10-19T14:05:00Z",
      last_modified: "2026-10-19T14:05:00Z",
      social_title: "وضع السوق المصري",
      social_caption: "تفاصيل وضع السوق اليوم",
      social_hashtags: ["#EGXBOTS", "#EGX"],
      content: "تقرير السوق",
      image_status: "ready",
    },
  ],
};

describe("SocialReportsTab Component", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    }) as any;
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders metrics, cost explainer, and images from the bucket", async () => {
    render(<SocialReportsTab />);

    // Wait for data load
    await waitFor(() => {
      expect(screen.getByText("تحليل سهم القلعة")).toBeInTheDocument();
    });

    // Verify stats
    expect(screen.getByText("إجمالي الصور")).toBeInTheDocument();
    expect(screen.getAllByText("$0.00").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/ضمن باقة Supabase المجانية/)).toBeInTheDocument();

    // Verify cost & generator explanation section
    expect(screen.getByText(/من الذي يصنع هذه الصور وكم تكلفنا؟/)).toBeInTheDocument();
    expect(screen.getByText(/Python Pillow/)).toBeInTheDocument();
    expect(screen.getByText(/daily_bot/)).toBeInTheDocument();

    // Verify images rendered
    expect(screen.getByText("تحليل سهم القلعة")).toBeInTheDocument();
    expect(screen.getByText("وضع السوق المصري")).toBeInTheDocument();
    expect(screen.getByText("CCAP")).toBeInTheDocument();
  });

  it("filters images when kind button is clicked", async () => {
    render(<SocialReportsTab />);

    await waitFor(() => {
      expect(screen.getByText("تحليل سهم القلعة")).toBeInTheDocument();
    });

    // Click on "وضع السوق" filter
    const marketButton = screen.getByRole("button", { name: /وضع السوق/i });
    fireEvent.click(marketButton);

    // CCAP stock card should be hidden, Market should remain
    expect(screen.queryByText("تحليل سهم القلعة")).not.toBeInTheDocument();
    expect(screen.getByText("وضع السوق المصري")).toBeInTheDocument();
  });

  it("opens modal lightbox on image click", async () => {
    render(<SocialReportsTab />);

    await waitFor(() => {
      expect(screen.getByText("تحليل سهم القلعة")).toBeInTheDocument();
    });

    // Click on details/caption button
    const detailButtons = screen.getAllByRole("button", { name: /التفاصيل والكابشن/i });
    fireEvent.click(detailButtons[0]);

    // Check lightbox modal content
    expect(screen.getByText("نص المنشور الجاهز (Social Caption)")).toBeInTheDocument();
    expect(screen.getByText("تفاصيل تحليل سهم القلعة")).toBeInTheDocument();
    expect(screen.getByText("نسخ رابط الصورة المباشر")).toBeInTheDocument();
  });
});
