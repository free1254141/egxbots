"use client";

import { useState } from "react";
import { Activity } from "lucide-react";
import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import type { DailyActiveUsage } from "@/lib/admin/user-analytics";

export default function DailyUsageChart({ data, isAr, loading, complete }: {
    data: DailyActiveUsage[];
    isAr: boolean;
    loading: boolean;
    complete: boolean;
}) {
    const [days, setDays] = useState<30 | 90>(30);
    const visibleData = data.slice(-days);
    return (
        <section aria-label={isAr ? "الاستخدام اليومي للموقع" : "Daily site usage"} className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 p-4 mb-6 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h3 className="font-black text-xs tracking-widest flex items-center gap-2 text-black dark:text-white">
                    <Activity className="w-4 h-4 text-cyan-500" />
                    {isAr ? "الاستخدام اليومي للموقع" : "DAILY SITE USAGE"}
                </h3>
                <div className="flex gap-2">
                    {([30, 90] as const).map((period) => (
                        <button key={period} type="button" aria-pressed={days === period} onClick={() => setDays(period)} className={`border-2 border-black dark:border-white px-3 py-1 text-xs font-black ${days === period ? "bg-cyan-500 text-black" : "bg-white dark:bg-zinc-950 text-zinc-500"}`}>
                            {period} {isAr ? "يوم" : "days"}
                        </button>
                    ))}
                </div>
            </div>
            <p className="text-[10px] text-zinc-500 font-bold mb-3">
                {isAr ? "عدد المستخدمين النشطين كل يوم: المستخدم المسجل الذي فتح صفحة أو أرسل رسالة يُحسب مرة واحدة، بتوقيت القاهرة، مع استبعاد الأدمن." : "Daily active users: each registered user who viewed a page or sent a message counts once per Cairo day. Admin accounts are excluded."}
            </p>
            {!complete && <p role="status" className="mb-3 border-2 border-amber-500 p-2 text-[10px] font-bold text-amber-700 dark:text-amber-300">{isAr ? "بيانات النشاط جزئية؛ الأعداد المعروضة حد أدنى." : "Activity data is incomplete; displayed counts are lower bounds."}</p>}
            {loading ? <div role="status" className="h-56 flex items-center justify-center text-xs text-zinc-500">{isAr ? "جاري تحميل النشاط…" : "Loading activity…"}</div>
                : !data.length ? <div className="h-56 flex items-center justify-center text-xs text-zinc-500">{isAr ? "بيانات النشاط غير متاحة." : "Activity data is unavailable."}</div>
                    : <div className="h-56 w-full" dir="ltr">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart data={visibleData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} accessibilityLayer>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#71717a" opacity={0.2} />
                                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#71717a" }} minTickGap={20} />
                                <YAxis allowDecimals={false} domain={[0, "auto"]} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#71717a" }} />
                                <Tooltip<ValueType, NameType> contentStyle={{ backgroundColor: "#18181b", border: "2px solid #fff", fontSize: "11px" }} labelStyle={{ color: "#fbbf24" }} itemStyle={{ color: "#fff" }}
                                    labelFormatter={(_, payload) => payload?.[0]?.payload?.fullDate || ""}
                                    formatter={(value) => [complete ? value : `≥ ${value}`, isAr ? "عدد النشطين" : "Active users"]} />
                                <Line type="linear" dataKey="activeUsers" name="activeUsers" stroke="#06b6d4" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>}
        </section>
    );
}
