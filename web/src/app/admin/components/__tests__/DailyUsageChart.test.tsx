/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import DailyUsageChart from "../DailyUsageChart";
import type { DailyActiveUsage } from "@/lib/admin/user-analytics";

jest.mock("recharts", () => ({
    ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
    ComposedChart: ({ children, data }: any) => <div data-testid="usage-series" data-rows={data.length}>{children}</div>,
    Line: ({ dataKey }: any) => <span data-testid={dataKey} />,
    Area: ({ dataKey }: any) => <span data-testid={dataKey} />,
    CartesianGrid: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null,
}));

const data: DailyActiveUsage[] = Array.from({ length: 90 }, (_, i) => ({
    date: String(i), fullDate: String(i), activeUsers: 3, newActiveUsers: 1, returningActiveUsers: 2, unknownSignupUsers: 0,
}));

describe("daily site usage chart", () => {
    it("shows one activity chart with total, new, and existing users and switches its period", () => {
        render(<DailyUsageChart data={data} isAr loading={false} complete />);
        expect(screen.getAllByTestId("usage-series")).toHaveLength(1);
        expect(screen.getByTestId("usage-series").getAttribute("data-rows")).toBe("30");
        for (const key of ["activeUsers", "newActiveUsers", "returningActiveUsers"]) expect(screen.getByTestId(key)).toBeTruthy();
        expect(screen.getByText("نشطون قدامى")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "90 يوم" }));
        expect(screen.getByTestId("usage-series").getAttribute("data-rows")).toBe("90");
        expect(screen.getByRole("button", { name: "90 يوم" }).getAttribute("aria-pressed")).toBe("true");
    });

    it("distinguishes incomplete or unavailable data from a zero activity day", () => {
        const { rerender } = render(<DailyUsageChart data={[]} isAr={false} loading complete={false} />);
        expect(screen.getByText("Loading activity…")).toBeTruthy();
        expect(screen.getByText(/lower bounds/)).toBeTruthy();
        expect(screen.queryByTestId("usage-series")).toBeNull();
        rerender(<DailyUsageChart data={[]} isAr={false} loading={false} complete />);
        expect(screen.getByText("Activity data is unavailable.")).toBeTruthy();
        rerender(<DailyUsageChart data={[{ ...data[0], activeUsers: 0, newActiveUsers: 0, returningActiveUsers: 0 }]} isAr={false} loading={false} complete />);
        expect(screen.getByTestId("usage-series")).toBeTruthy();
        expect(screen.queryByText("Activity data is unavailable.")).toBeNull();
    });
});
