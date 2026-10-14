import { todayInCairo } from "./cairo-date";

function cairoDate(value: unknown): string | null {
    if (!value) return null;
    const date = new Date(String(value));
    if (!Number.isFinite(date.getTime())) return null;
    return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo" }).format(date);
}

/**
 * Supabase is authoritative only after the daily job actually completed and
 * wrote the current session's daily prices. The clock alone is not evidence.
 */
export async function isDailySyncComplete(supabase: any, expectedDate?: string, symbol?: string): Promise<boolean> {
    if (!supabase) return false;
    try {
        const jobQuery = await supabase
            .from("daily_job_runs")
            .select("status,started_at,completed_at,steps")
            .eq("job_type", "daily_bot")
            .order("started_at", { ascending: false })
            .limit(1);
        const job = jobQuery?.data?.[0];
        if (jobQuery.error || !job || job.status !== "completed") return false;

        let steps: any[] = [];
        if (Array.isArray(job.steps)) steps = job.steps;
        else if (typeof job.steps === "string") {
            try {
                let decoded = JSON.parse(job.steps);
                if (typeof decoded === "string") decoded = JSON.parse(decoded);
                steps = Array.isArray(decoded) ? decoded : [];
            } catch { steps = []; }
        }
        const priceSteps = steps.filter((step) => step?.name === "sync_prices" || step?.step === "sync_prices");
        if (!priceSteps.length) return false;
        const priceStep = priceSteps[priceSteps.length - 1];
        const hasStartedStep = priceSteps.slice(0, -1).some((step) => step.status === "started" || step.status === "running");
        if (priceSteps.length < 2 || !hasStartedStep) return false;
        if (priceStep.status !== "completed" && priceStep.status !== "success" && priceStep.ok !== true) return false;

        const runDate = cairoDate(job.completed_at || job.started_at);
        if (!runDate) return false;

        // Daily sync is only complete if the completed job matches the target session date
        const targetDate = expectedDate || todayInCairo();
        if (targetDate && runDate !== targetDate) return false;

        let prices = supabase
            .from("stock_prices")
            .select("date")
            .eq("exchange", "EGX");
        if (symbol) prices = prices.eq("symbol", symbol);
        const latestQuery = await prices
            .order("date", { ascending: false })
            .limit(1);
        if (latestQuery.error) return false;
        const latestDate = String(latestQuery?.data?.[0]?.date || "").slice(0, 10);
        return Boolean(latestDate && latestDate === runDate);
    } catch (error) {
        console.warn("[SYNC_GATE] Unable to prove daily sync completion:", error);
        return false;
    }
}

export function shouldPreferLiveBeforeSync(now = new Date()): boolean {
    const cairo = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Africa/Cairo",
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    }).formatToParts(now);
    const parts = Object.fromEntries(cairo.map((part) => [part.type, part.value]));
    const weekday = parts.weekday;
    if (weekday === "Fri" || weekday === "Sat") return false;
    const minutes = Number(parts.hour) * 60 + Number(parts.minute);
    return minutes >= 10 * 60;
}

