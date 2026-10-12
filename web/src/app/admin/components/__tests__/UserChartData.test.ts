import { withDailyActiveUsers } from "../user-chart-data";

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
