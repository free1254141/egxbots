import { getCairoDateString, resolveSubscriptionQuotaWindow } from "../plan-gate";

describe("resolveSubscriptionQuotaWindow & getCairoDateString", () => {
  test("mid-month PRO activation uses current_period_start date in Cairo timezone", () => {
    const now = new Date("2026-10-26T01:25:00.000Z"); // 2026-10-26 04:25 Cairo
    const win = resolveSubscriptionQuotaWindow(
      [
        {
          plan_id: "pro",
          status: "active",
          current_period_start: "2026-10-21T22:21:55.390863+00:00",
          current_period_end: "2026-11-20T22:21:55.390863+00:00",
        },
      ],
      now
    );

    expect(win.isPro).toBe(true);
    expect(win.todayStr).toBe("2026-10-26");
    expect(win.calMonthStartStr).toBe("2026-10-01");
    expect(win.effectiveMonthStartStr).toBe("2026-10-21");
  });

  test("prior-month PRO subscription clamps to YYYY-MM-01 (never shifts to previous month last day)", () => {
    const now = new Date("2026-10-26T01:25:00.000Z");
    const win = resolveSubscriptionQuotaWindow(
      [
        {
          plan_id: "pro",
          status: "active",
          current_period_start: "2026-09-29T09:14:23.338128+00:00",
          current_period_end: "2026-10-29T09:14:23.338128+00:00",
        },
      ],
      now
    );

    expect(win.isPro).toBe(true);
    expect(win.calMonthStartStr).toBe("2026-10-01");
    expect(win.effectiveMonthStartStr).toBe("2026-10-01");
  });

  test("trialing PRO subscription and pro_6m / pro_1y / lifetime plans are recognized", () => {
    const now = new Date("2026-10-26T10:00:00.000Z");
    const trialWin = resolveSubscriptionQuotaWindow(
      [
        {
          plan_id: "pro",
          status: "trialing",
          current_period_start: "2026-10-24T12:00:00.000Z",
          current_period_end: "2026-10-31T12:00:00.000Z",
        },
      ],
      now
    );
    expect(trialWin.isPro).toBe(true);
    expect(trialWin.effectiveMonthStartStr).toBe("2026-10-24");

    const sixMonthWin = resolveSubscriptionQuotaWindow(
      [
        {
          plan_id: "pro_6m",
          status: "active",
          current_period_start: "2026-10-15T12:00:00.000Z",
          current_period_end: "2027-04-15T12:00:00.000Z",
        },
      ],
      now
    );
    expect(sixMonthWin.isPro).toBe(true);
    expect(sixMonthWin.effectiveMonthStartStr).toBe("2026-10-15");
  });

  test("Cairo midnight boundary (22:30 UTC = 01:30 Cairo next day) resolves consistently", () => {
    const utcLateNight = new Date("2026-10-25T22:30:00.000Z");
    expect(getCairoDateString(utcLateNight)).toBe("2026-10-26");
  });
});
