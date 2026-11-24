"use client";

import React, { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Circle, ListChecks, Loader2, X } from "lucide-react";
import type { AnswerStageItem } from "@/contexts/ChatContext";

interface AnswerStagesChecklistProps {
    stages: AnswerStageItem[];
    isStreaming?: boolean;
    onStop?: () => void;
    language?: string;
}

export function AnswerStagesChecklist({
    stages,
    isStreaming = false,
    onStop,
    language = "ar",
}: AnswerStagesChecklistProps) {
    const [expandedAfterDone, setExpandedAfterDone] = useState(false);

    if (!stages || stages.length === 0) return null;

    const doneCount = stages.filter((s) => s.status === "done").length;
    const progressPct = Math.round((doneCount / Math.max(stages.length, 1)) * 100);
    const allDone = !isStreaming && doneCount === stages.length;

    if (allDone && !expandedAfterDone) {
        return (
            <div className="mb-2.5 flex items-center justify-between gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/5 px-3 py-1.5 text-xs">
                <button
                    type="button"
                    onClick={() => setExpandedAfterDone(true)}
                    className="flex flex-1 items-center justify-between gap-2 text-right font-semibold text-emerald-700 dark:text-emerald-400 hover:opacity-90 transition-opacity cursor-pointer"
                    aria-expanded={false}
                >
                    <span className="flex items-center gap-1.5">
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                        <span>
                            {language === "ar"
                                ? `اكتملت مراحل التحليل والتحقق (${stages.length}/${stages.length})`
                                : `Analysis stages completed (${stages.length}/${stages.length})`}
                        </span>
                    </span>
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-75" />
                </button>
            </div>
        );
    }

    return (
        <div
            className="mb-3 rounded-xl border border-zinc-200 dark:border-white/15 bg-zinc-50/90 dark:bg-zinc-950/90 p-2.5 sm:p-3 text-xs shadow-xs"
            data-testid="answer-stages-checklist"
        >
            <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 font-bold text-zinc-900 dark:text-zinc-100">
                    <ListChecks className="h-4 w-4 shrink-0 text-amber-500" />
                    <span>{language === "ar" ? "مراحل إجابة السؤال" : "Answer Pipeline"}</span>
                    <span className="rounded-md bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-extrabold text-amber-700 dark:text-amber-300 tabular-nums">
                        {doneCount}/{stages.length}
                    </span>
                </div>

                <div className="flex items-center gap-1.5">
                    {isStreaming && onStop && (
                        <button
                            type="button"
                            onClick={onStop}
                            className="flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[11px] font-bold text-red-600 dark:text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
                            title={language === "ar" ? "إيقاف الاستجابة" : "Stop Responding"}
                        >
                            <X className="h-3 w-3" />
                            <span>{language === "ar" ? "إيقاف" : "Stop"}</span>
                        </button>
                    )}
                    {!isStreaming && allDone && (
                        <button
                            type="button"
                            onClick={() => setExpandedAfterDone(false)}
                            className="flex items-center gap-1 rounded-lg px-1.5 py-0.5 text-[11px] font-semibold text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white transition-colors cursor-pointer"
                            aria-expanded={true}
                        >
                            <span>{language === "ar" ? "إخفاء" : "Hide"}</span>
                            <ChevronUp className="h-3.5 w-3.5" />
                        </button>
                    )}
                </div>
            </div>

            <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800 mb-2.5">
                <div
                    className={`h-full transition-all duration-300 ${allDone ? "bg-emerald-500" : "bg-amber-500"}`}
                    style={{ width: `${Math.max(10, progressPct)}%` }}
                />
            </div>

            <ol className="space-y-1.5">
                {stages.map((stage, idx) => {
                    const isDone = stage.status === "done";
                    const isActive = stage.status === "in_progress";
                    return (
                        <li
                            key={stage.id}
                            className={`flex items-center justify-between gap-2 rounded-lg px-2 py-1 transition-colors ${
                                isActive
                                    ? "bg-amber-500/10 border border-amber-500/30 text-zinc-950 dark:text-amber-100 font-bold"
                                    : isDone
                                    ? "text-zinc-700 dark:text-zinc-300"
                                    : "text-zinc-400 dark:text-zinc-500"
                            }`}
                        >
                            <span className="flex items-center gap-2 min-w-0">
                                {isDone ? (
                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                                ) : isActive ? (
                                    <Loader2 className="h-3.5 w-3.5 shrink-0 text-amber-500 animate-spin" />
                                ) : (
                                    <Circle className="h-3.5 w-3.5 shrink-0 text-zinc-300 dark:text-zinc-700" />
                                )}
                                <span className="text-[10px] font-mono opacity-60 shrink-0">{idx + 1}.</span>
                                <span className="truncate">{stage.label}</span>
                            </span>
                            <span
                                className={`shrink-0 text-[10px] font-bold ${
                                    isDone
                                        ? "text-emerald-600 dark:text-emerald-400"
                                        : isActive
                                        ? "text-amber-600 dark:text-amber-400"
                                        : "text-zinc-400 dark:text-zinc-600"
                                }`}
                            >
                                {isDone
                                    ? language === "ar" ? "تم ✓" : "Done"
                                    : isActive
                                    ? language === "ar" ? "جاري..." : "Running"
                                    : language === "ar" ? "انتظار" : "Pending"}
                            </span>
                        </li>
                    );
                })}
            </ol>
        </div>
    );
}
