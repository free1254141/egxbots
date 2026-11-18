import {
    buildCombinedDailyDataset,
    buildMonthlySubscribersAndRenewals,
    filterByTimeRange,
    withDailyActiveUsers,
} from "../user-chart-data";

it("joins activity by full date across a year boundary and preserves missing versus zero", () => {
    const growth = [{ fullDate: "2025-12-31", count: 2 }, { fullDate: "2026-12-31", count: 3 }, { fullDate: "2027-01-01", count: 4 }, { count: 5 }];
    const usage = [{ fullDate: "2026-12-31", date: "12-31", activeUsers: 0, newActiveUsers: 0, returningActiveUsers: 0, unknownSignupUsers: 0 }];
    expect(withDailyActiveUsers(growth, usage)).toEqual([
        { fullDate: "2025-12-31", count: 2, activeUsers: null },
        { fullDate: "2026-12-31", count: 3, activeUsers: 0 },
        { fullDate: "2027-01-01", count: 4, activeUsers: null },
        { count: 5, activeUsers: null },
    ]);
    expect(growth[1]).not.toHaveProperty("activeUsers");
});

it("filters time series by preset days or custom date range", () => {
    const items = [
        { fullDate: "2026-09-30", value: 1 },
        { fullDate: "2026-10-01", value: 2 },
        { fullDate: "2026-10-15", value: 3 },
        { fullDate: "2026-11-05", value: 4 },
    ];

    expect(filterByTimeRange(items, { days: 2 })).toEqual([
        { fullDate: "2026-10-15", value: 3 },
        { fullDate: "2026-11-05", value: 4 },
    ]);

    expect(filterByTimeRange(items, { days: 2, startDate: "2026-10-01", endDate: "2026-10-31" })).toEqual([
        { fullDate: "2026-10-01", value: 2 },
        { fullDate: "2026-10-15", value: 3 },
    ]);

    expect(filterByTimeRange(items, { days: 2, startDate: "2026-10-15" })).toEqual([
        { fullDate: "2026-10-15", value: 3 },
        { fullDate: "2026-11-05", value: 4 },
    ]);
});

it("classifies first-time subscribers vs renewals across all history before applying date filter", () => {
    const orders = [
        { user_id: "u1", plan_id: "pro", amount_egp: 100, created_at: "2026-09-10T10:00:00Z" },
        { user_id: "u2", plan_id: "pro", amount_egp: 100, created_at: "2026-09-15T10:00:00Z" },
        { user_id: "u1", plan_id: "pro", amount_egp: 100, created_at: "2026-11-10T10:00:00Z" },
        { user_id: "u3", plan_id: "pro", amount_egp: 200, created_at: "2026-11-12T10:00:00Z" },
        { user_id: "u4", plan_id: "pro_renewal", amount_egp: 100, created_at: "2026-11-14T10:00:00Z" },
    ];

    // Full history seeds empty intermediate month (2026-10)
    expect(buildMonthlySubscribersAndRenewals(orders)).toEqual([
        { date: "2026-09", fullDate: "2026-09-01", newSubscribers: 2, renewals: 0, totalSubscribers: 2, revenueEgp: 200 },
        { date: "2026-10", fullDate: "2026-10-01", newSubscribers: 0, renewals: 0, totalSubscribers: 0, revenueEgp: 0 },
        { date: "2026-11", fullDate: "2026-11-01", newSubscribers: 1, renewals: 2, totalSubscribers: 3, revenueEgp: 400 },
    ]);

    // Filtering to November still preserves u1's second payment as a renewal
    expect(buildMonthlySubscribersAndRenewals(orders, { startDate: "2026-11-01", endDate: "2026-11-30" })).toEqual([
        { date: "2026-11", fullDate: "2026-11-01", newSubscribers: 1, renewals: 2, totalSubscribers: 3, revenueEgp: 400 },
    ]);
});

it("joins all overlay chart series by fullDate on the combined daily timeline", () => {
    const growth = [
        { date: "11-01", fullDate: "2026-11-01", count: 4, gatewayPaidCount: 1, cashPaidCount: 0, recommendationsCount: 10, egx30: 31000 },
        { date: "11-05", fullDate: "2026-11-05", count: 7, gatewayPaidCount: 1, cashPaidCount: 1, recommendationsCount: 12, egx30: 31250 },
    ];
    const usage = [
        { fullDate: "2026-11-05", date: "11-05", activeUsers: 19, newActiveUsers: 5, returningActiveUsers: 14, unknownSignupUsers: 0 },
    ];
    const chatUsage = [
        { fullDate: "2026-11-01", chatUsers: 3, questions: 8 },
        { fullDate: "2026-11-05", chatUsers: 6, questions: 15 },
    ];
    const orders = [
        { user_id: "u1", plan_id: "pro", amount_egp: 100, created_at: "2026-11-01T10:00:00Z" },
        { user_id: "u1", plan_id: "pro", amount_egp: 100, created_at: "2026-11-05T10:00:00Z" },
        { user_id: "u2", plan_id: "pro", amount_egp: 200, created_at: "2026-11-05T12:00:00Z" },
    ];

    expect(buildCombinedDailyDataset({ growth, usage, chatUsage, orders })).toEqual([
        {
            date: "11-01",
            fullDate: "2026-11-01",
            count: 4,
            gatewayPaidCount: 1,
            cashPaidCount: 0,
            recommendationsCount: 10,
            egx30: 31000,
            activeUsers: null,
            chatUsers: 3,
            questions: 8,
            newSubscribers: 1,
            renewals: 0,
            totalSubscribers: 1,
        },
        {
            date: "11-05",
            fullDate: "2026-11-05",
            count: 7,
            gatewayPaidCount: 1,
            cashPaidCount: 1,
            recommendationsCount: 12,
            egx30: 31250,
            activeUsers: 19,
            chatUsers: 6,
            questions: 15,
            newSubscribers: 1,
            renewals: 1,
            totalSubscribers: 2,
        },
    ]);
});
