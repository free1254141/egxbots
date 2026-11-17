/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import DailyChatUsageChart from "../DailyChatUsageChart";
import { buildDailyChatUsage, type DailyChatUsage } from "@/lib/admin/user-analytics";

jest.mock("recharts", () => ({
    ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
    ComposedChart: ({ children, data }: any) => <div data-testid="chat-usage-series" data-rows={data.length}>{children}</div>,
    Bar: ({ dataKey }: any) => <span data-testid={dataKey} />,
    Line: ({ dataKey }: any) => <span data-testid={dataKey} />,
    CartesianGrid: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null,
}));

const data: DailyChatUsage[] = Array.from({ length: 90 }, (_, i) => ({
    date: String(i), fullDate: String(i), chatUsers: 5, questions: 12,
}));

describe("daily chat usage chart", () => {
    it("renders both questions and chatUsers series and switches period", () => {
        render(<DailyChatUsageChart data={data} isAr loading={false} complete />);
        expect(screen.getByTestId("chat-usage-series").getAttribute("data-rows")).toBe("30");
        expect(screen.getByTestId("questions")).toBeTruthy();
        expect(screen.getByTestId("chatUsers")).toBeTruthy();
        expect(screen.getByText("الأسئلة: 360")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "3 شهور" }));
        expect(screen.getByTestId("chat-usage-series").getAttribute("data-rows")).toBe("90");
        expect(screen.getByRole("button", { name: "3 شهور" }).getAttribute("aria-pressed")).toBe("true");
    });

    it("handles loading, incomplete, and empty states", () => {
        const { rerender } = render(<DailyChatUsageChart data={[]} isAr={false} loading complete={false} />);
        expect(screen.getByText("Loading chat usage…")).toBeTruthy();
        expect(screen.getByText(/lower bounds/)).toBeTruthy();
        rerender(<DailyChatUsageChart data={[]} isAr={false} loading={false} complete />);
        expect(screen.getByText("Chat usage data is unavailable.")).toBeTruthy();
    });

    it("builds daily chat users and questions excluding admins and assistant messages", () => {
        const now = new Date("2026-11-17T12:00:00Z");
        const series = buildDailyChatUsage({
            profiles: [
                { id: "u1", created_at: "2026-10-01T00:00:00Z" },
                { id: "u2", created_at: "2026-10-01T00:00:00Z" },
                { id: "admin1", created_at: "2026-10-01T00:00:00Z" },
            ],
            chatMessages: [
                { user_id: "u1", role: "user", created_at: "2026-11-17T10:00:00Z" },
                { user_id: "u1", role: "assistant", created_at: "2026-11-17T10:00:05Z" },
                { user_id: "u1", role: "user", created_at: "2026-11-17T10:05:00Z" },
                { user_id: "u2", role: "user", created_at: "2026-11-17T11:00:00Z" },
                { user_id: "admin1", role: "user", created_at: "2026-11-17T11:30:00Z" },
            ],
            excludeUserIds: new Set(["admin1"]),
            now,
        });
        const today = series[series.length - 1];
        expect(today.fullDate).toBe("2026-11-17");
        expect(today.chatUsers).toBe(2);
        expect(today.questions).toBe(3);
    });
});
