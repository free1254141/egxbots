"use client";

import { useState } from "react";
import { Activity } from "lucide-react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DailyActiveUsage } from "@/lib/admin/user-analytics";

export default function DailyUsageChart({ data, isAr, loading, complete }: {
    data: DailyActiveUsage[];
    isAr: boolean;
    loading: boolean;
    complete: boolean;
}) {
    const [days, setDays] = useState<30 | 90>(30);
    const visibleData = data.slice(-days);
    const labels: Record<string, string> = {
        activeUsers: isAr ? "إجمالي النشطين" : "Total active users",
        newActiveUsers: isAr ? "نشطون جدد" : "New active users",
        returningActiveUsers: isAr ? "نشطون قدامى" : "Existing active users",
    };
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
                {isAr ? "كل مستخدم مسجل فتح صفحة أو أرسل رسالة يُحسب مرة واحدة يوميًا. الجديد سجّل واستخدم في نفس اليوم؛ القديم سجّل قبل ذلك. بتوقيت القاهرة، مع استبعاد الأدمن." : "Each registered user who viewed a page or sent a message counts once per Cairo day. New users signed up that day; existing users signed up earlier. Admin accounts are excluded."}
            </p>
            {!complete && <p role="status" className="mb-3 border-2 border-amber-500 p-2 text-[10px] font-bold text-amber-700 dark:text-amber-300">{isAr ? "بيانات النشاط جزئية؛ الأعداد المعروضة حد أدنى." : "Activity data is incomplete; displayed counts are lower bounds."}</p>}
            {visibleData.some((row) => row.unknownSignupUsers > 0) && <p className="mb-3 text-[10px] text-amber-700 dark:text-amber-300">{isAr ? "بعض الحسابات تاريخ تسجيلها غير متاح؛ تدخل في الإجمالي دون تقسيمها لجديدة أو قديمة." : "Some signup dates are unavailable; those users count toward the total without a new/existing classification."}</p>}
            <div className="flex flex-wrap gap-4 text-[10px] font-black mb-3 text-black dark:text-white">
                {[["activeUsers", "#06b6d4"], ["newActiveUsers", "#3b82f6"], ["returningActiveUsers", "#8b5cf6"]].map(([key, color]) => (
                    <span key={key} className="flex items-center gap-1.5"><span className="w-3 h-3" style={{ backgroundColor: color }} />{labels[key]}</span>
                ))}
            </div>
            {loading ? <div role="status" className="h-56 flex items-center justify-center text-xs text-zinc-500">{isAr ? "جاري تحميل النشاط…" : "Loading activity…"}</div>
                : !data.length ? <div className="h-56 flex items-center justify-center text-xs text-zinc-500">{isAr ? "بيانات النشاط غير متاحة." : "Activity data is unavailable."}</div>
                    : <div className="h-56 w-full" dir="ltr">
                        <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart data={visibleData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} accessibilityLayer>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#71717a" opacity={0.2} />
                                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#71717a" }} minTickGap={20} />
                                <YAxis allowDecimals={false} domain={[0, "auto"]} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#71717a" }} />
                                <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "2px solid #fff", fontSize: "11px" }} labelStyle={{ color: "#fbbf24" }} itemStyle={{ color: "#fff" }}
                                    labelFormatter={(_, payload) => payload?.[0]?.payload?.fullDate || ""}
                                    formatter={(value, name) => [complete ? value : `≥ ${value}`, labels[String(name)] || name]} />
                                <Area type="linear" dataKey="newActiveUsers" name="newActiveUsers" stackId="activity" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} isAnimationActive={false} />
                                <Area type="linear" dataKey="returningActiveUsers" name="returningActiveUsers" stackId="activity" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.3} isAnimationActive={false} />
                                <Line type="linear" dataKey="activeUsers" name="activeUsers" stroke="#06b6d4" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                            </ComposedChart>
                        </ResponsiveContainer>
                    </div>}
        </section>
    );
}
