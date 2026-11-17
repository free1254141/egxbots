"use client";

import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { NameType, ValueType } from "recharts/types/component/DefaultTooltipContent";
import type { DailyChatUsage } from "@/lib/admin/user-analytics";

export default function DailyChatUsageChart({ data, isAr, loading, complete }: {
    data: DailyChatUsage[];
    isAr: boolean;
    loading: boolean;
    complete: boolean;
}) {
    const [days, setDays] = useState<30 | 90 | 180>(30);
    const visibleData = data.slice(-days);
    const totalQuestions = visibleData.reduce((sum, item) => sum + item.questions, 0);
    const peakChatUsers = visibleData.reduce((max, item) => Math.max(max, item.chatUsers), 0);

    return (
        <section
            aria-label={isAr ? "مستخدمو الشات وعدد الأسئلة يومياً" : "Daily chat users and questions"}
            className="border-4 border-black dark:border-white bg-zinc-50 dark:bg-zinc-900 p-4 mb-6 shadow-[4px_4px_0px_rgba(0,0,0,1)] dark:shadow-[4px_4px_0px_rgba(255,255,255,1)]"
        >
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div className="flex flex-wrap items-center gap-3">
                    <h3 className="font-black text-xs tracking-widest flex items-center gap-2 text-black dark:text-white">
                        <MessageSquare className="w-4 h-4 text-violet-500" />
                        {isAr ? "مستخدمو الشات وعدد الأسئلة" : "DAILY CHAT USERS & QUESTIONS"}
                    </h3>
                    {!loading && visibleData.length > 0 && (
                        <div className="flex items-center gap-2 text-[10px] font-black">
                            <span className="border-2 border-black dark:border-white bg-amber-400/20 text-amber-700 dark:text-amber-300 px-2 py-0.5">
                                {isAr ? `الأسئلة: ${totalQuestions.toLocaleString("en-US")}` : `Questions: ${totalQuestions.toLocaleString("en-US")}`}
                            </span>
                            <span className="border-2 border-black dark:border-white bg-violet-500/20 text-violet-700 dark:text-violet-300 px-2 py-0.5">
                                {isAr ? `ذروة المستخدمين: ${peakChatUsers}` : `Peak Users: ${peakChatUsers}`}
                            </span>
                        </div>
                    )}
                </div>
                <div className="flex gap-2">
                    {([30, 90, 180] as const).map((period) => (
                        <button
                            key={period}
                            type="button"
                            aria-pressed={days === period}
                            onClick={() => setDays(period)}
                            className={`border-2 border-black dark:border-white px-3 py-1 text-xs font-black ${days === period ? "bg-violet-500 text-white" : "bg-white dark:bg-zinc-950 text-zinc-500"}`}
                        >
                            {period === 180
                                ? (isAr ? "6 شهور" : "6m")
                                : period === 90
                                ? (isAr ? "3 شهور" : "3m")
                                : isAr
                                ? `${period} يوم`
                                : `${period}d`}
                        </button>
                    ))}
                </div>
            </div>
            <p className="text-[10px] text-zinc-500 font-bold mb-3">
                {isAr
                    ? "الأعمدة: إجمالي أسئلة المستخدمين يومياً • الخط: عدد مستخدمي الشات الفريدين كل يوم (بتوقيت القاهرة، مع استبعاد الأدمن)."
                    : "Bars: daily user questions • Line: unique daily chat users (Cairo time, admin accounts excluded)."}
            </p>
            {!complete && (
                <p role="status" className="mb-3 border-2 border-amber-500 p-2 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                    {isAr ? "بيانات الشات جزئية؛ الأعداد المعروضة حد أدنى." : "Chat data is incomplete; displayed counts are lower bounds."}
                </p>
            )}
            {loading ? (
                <div role="status" className="h-56 flex items-center justify-center text-xs text-zinc-500">
                    {isAr ? "جاري تحميل بيانات الشات…" : "Loading chat usage…"}
                </div>
            ) : !data.length ? (
                <div className="h-56 flex items-center justify-center text-xs text-zinc-500">
                    {isAr ? "بيانات الشات غير متاحة." : "Chat usage data is unavailable."}
                </div>
            ) : (
                <div className="h-56 w-full" dir="ltr">
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} accessibilityLayer>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#71717a" opacity={0.2} />
                            <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#71717a" }} minTickGap={20} />
                            <YAxis yAxisId="left" allowDecimals={false} domain={[0, "auto"]} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#f59e0b" }} />
                            <YAxis yAxisId="right" orientation="right" allowDecimals={false} domain={[0, "auto"]} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#8b5cf6" }} />
                            <Tooltip<ValueType, NameType>
                                contentStyle={{ backgroundColor: "#18181b", border: "2px solid #fff", fontSize: "11px" }}
                                labelStyle={{ color: "#fbbf24" }}
                                itemStyle={{ color: "#fff" }}
                                labelFormatter={(_, payload) => payload?.[0]?.payload?.fullDate || ""}
                                formatter={(value, name) => {
                                    const formatted = complete ? value : `≥ ${value}`;
                                    if (name === "questions") return [formatted, isAr ? "عدد الأسئلة" : "Questions"];
                                    return [formatted, isAr ? "مستخدمو الشات" : "Chat users"];
                                }}
                            />
                            <Bar yAxisId="left" dataKey="questions" name="questions" fill="#f59e0b" radius={[3, 3, 0, 0]} maxBarSize={24} isAnimationActive={false} />
                            <Line yAxisId="right" type="linear" dataKey="chatUsers" name="chatUsers" stroke="#8b5cf6" strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
            )}
        </section>
    );
}
