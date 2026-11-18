import type { DailyActiveUsage, DailyChatUsage } from "@/lib/admin/user-analytics";

export type ChartLayerKey = "growth" | "paid" | "monthly" | "market" | "chat";

export const ALL_CHART_LAYERS: ChartLayerKey[] = ["growth", "paid", "monthly", "market", "chat"];

export interface ChartTimeFilter {
    days: number;
    startDate?: string;
    endDate?: string;
}

export interface ApprovedOrderInput {
    user_id?: string | null;
    plan_id?: string | null;
    amount_egp?: number | string | null;
    created_at?: string | null;
}

export interface MonthlySubscribersPoint {
    date: string;
    fullDate: string;
    newSubscribers: number;
    renewals: number;
    totalSubscribers: number;
    revenueEgp: number;
}

interface ClassifiedOrder {
    ms: number;
    cairoDate: string;
    month: string;
    uid: string;
    planId: string;
    amount: number;
    isRenewal: boolean;
}

const CAIRO_DATE_FORMATTER = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Cairo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
});

function toCairoDateKey(value?: string | null): string | null {
    if (!value) return null;
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) return null;
    const parts = Object.fromEntries(CAIRO_DATE_FORMATTER.formatToParts(ms).map((p) => [p.type, p.value]));
    return `${parts.year}-${parts.month}-${parts.day}`;
}

function nextYearMonth(ym: string): string {
    const [yStr, mStr] = ym.split("-");
    const y = Number(yStr);
    const m = Number(mStr);
    if (m === 12) return `${String(y + 1).padStart(4, "0")}-01`;
    return `${String(y).padStart(4, "0")}-${String(m + 1).padStart(2, "0")}`;
}

// Join by the full calendar date, never MM-DD (which repeats across years).
export function withDailyActiveUsers<T extends { fullDate?: string }>(growth: T[], usage: DailyActiveUsage[]) {
    const byDate = new Map(usage.map((day) => [day.fullDate, day.activeUsers]));
    return growth.map((day) => ({
        ...day,
        activeUsers: day.fullDate ? (byDate.get(day.fullDate) ?? null) : null,
    }));
}

export function filterByTimeRange<T extends { fullDate?: string }>(items: T[], filter: ChartTimeFilter): T[] {
    const start = String(filter.startDate || "").trim();
    const end = String(filter.endDate || "").trim();
    if (start || end) {
        return items.filter((item) => {
            const fullDate = item.fullDate;
            if (!fullDate) return false;
            if (start && fullDate < start) return false;
            if (end && fullDate > end) return false;
            return true;
        });
    }
    return items.slice(-filter.days);
}

function classifyOrdersChronologically(orders: ApprovedOrderInput[]): ClassifiedOrder[] {
    const validOrders = (orders || [])
        .map((order) => {
            const ms = order.created_at ? Date.parse(order.created_at) : NaN;
            const cairoDate = toCairoDateKey(order.created_at);
            if (!Number.isFinite(ms) || !cairoDate) return null;
            const amount = Number(order.amount_egp ?? 0);
            return {
                ms,
                cairoDate,
                month: cairoDate.slice(0, 7),
                uid: String(order.user_id || "").trim(),
                planId: String(order.plan_id || "").toLowerCase().trim(),
                amount: Number.isFinite(amount) ? amount : 0,
            };
        })
        .filter((item): item is NonNullable<typeof item> => item !== null)
        .sort((a, b) => a.ms - b.ms);

    const seenUsers = new Set<string>();
    return validOrders.map((order) => {
        const isRenewal = (order.uid ? seenUsers.has(order.uid) : false) || order.planId === "pro_renewal";
        if (order.uid) seenUsers.add(order.uid);
        return { ...order, isRenewal };
    });
}

export function buildMonthlySubscribersAndRenewals(
    orders: ApprovedOrderInput[],
    options?: {
        cutoffDate?: string;
        startDate?: string;
        endDate?: string;
    }
): MonthlySubscribersPoint[] {
    const classified = classifyOrdersChronologically(orders);

    const start = String(options?.startDate || "").trim();
    const end = String(options?.endDate || "").trim();
    const cutoffMonth = options?.cutoffDate ? String(options.cutoffDate).slice(0, 7) : "";

    const filtered = classified.filter((order) => {
        if (start || end) {
            if (start && order.cairoDate < start) return false;
            if (end && order.cairoDate > end) return false;
            return true;
        }
        if (cutoffMonth && order.month < cutoffMonth) return false;
        return true;
    });

    if (filtered.length === 0) return [];

    const firstMonth = filtered[0].month;
    const lastMonth = filtered[filtered.length - 1].month;
    const buckets = new Map<string, { newSubscribers: number; renewals: number; revenueEgp: number }>();

    let cursor = firstMonth;
    let safety = 0;
    while (cursor <= lastMonth && safety < 240) {
        buckets.set(cursor, { newSubscribers: 0, renewals: 0, revenueEgp: 0 });
        cursor = nextYearMonth(cursor);
        safety += 1;
    }

    for (const order of filtered) {
        const bucket = buckets.get(order.month) ?? { newSubscribers: 0, renewals: 0, revenueEgp: 0 };
        if (order.isRenewal) {
            bucket.renewals += 1;
        } else {
            bucket.newSubscribers += 1;
        }
        bucket.revenueEgp += order.amount;
        buckets.set(order.month, bucket);
    }

    return Array.from(buckets.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([month, bucket]) => ({
            date: month,
            fullDate: `${month}-01`,
            newSubscribers: bucket.newSubscribers,
            renewals: bucket.renewals,
            totalSubscribers: bucket.newSubscribers + bucket.renewals,
            revenueEgp: Math.round(bucket.revenueEgp * 100) / 100,
        }));
}

export function buildCombinedDailyDataset<T extends { date: string; fullDate?: string }>(params: {
    growth: T[];
    usage: DailyActiveUsage[];
    chatUsage: Pick<DailyChatUsage, "fullDate" | "chatUsers" | "questions">[];
    orders: ApprovedOrderInput[];
}) {
    const usageByDate = new Map(params.usage.map((day) => [day.fullDate, day.activeUsers]));
    const chatByDate = new Map(
        params.chatUsage.map((day) => [day.fullDate, { chatUsers: day.chatUsers, questions: day.questions }])
    );
    const ordersByDate = new Map<string, { newSubscribers: number; renewals: number }>();
    for (const order of classifyOrdersChronologically(params.orders)) {
        const bucket = ordersByDate.get(order.cairoDate) ?? { newSubscribers: 0, renewals: 0 };
        if (order.isRenewal) bucket.renewals += 1;
        else bucket.newSubscribers += 1;
        ordersByDate.set(order.cairoDate, bucket);
    }

    return params.growth.map((day) => {
        const key = day.fullDate || "";
        const chat = key ? chatByDate.get(key) : undefined;
        const subs = key ? ordersByDate.get(key) : undefined;
        const newSubscribers = subs?.newSubscribers ?? 0;
        const renewals = subs?.renewals ?? 0;
        return {
            ...day,
            activeUsers: key ? (usageByDate.get(key) ?? null) : null,
            chatUsers: chat?.chatUsers ?? 0,
            questions: chat?.questions ?? 0,
            newSubscribers,
            renewals,
            totalSubscribers: newSubscribers + renewals,
        };
    });
}
