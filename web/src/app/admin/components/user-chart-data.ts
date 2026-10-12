import type { DailyActiveUsage } from "@/lib/admin/user-analytics";

// Join by the full calendar date, never MM-DD (which repeats across years).
export function withDailyActiveUsers<T extends { fullDate?: string }>(growth: T[], usage: DailyActiveUsage[]) {
    const byDate = new Map(usage.map((day) => [day.fullDate, day.activeUsers]));
    return growth.map((day) => ({
        ...day,
        activeUsers: day.fullDate ? (byDate.get(day.fullDate) ?? null) : null,
    }));
}
