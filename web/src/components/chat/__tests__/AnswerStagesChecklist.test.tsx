/** @jest-environment jsdom */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import {
    advanceAnswerStagesOnStatus,
    advanceAnswerStagesOnToken,
    createInitialAnswerStages,
    finalizeAnswerStages,
} from "@/contexts/ChatContext";
import { AnswerStagesChecklist } from "../AnswerStagesChecklist";

describe("AnswerStagesChecklist & Stage State Progression", () => {
    test("progresses through 4 ordered stages without letting raw English codes overwrite Arabic labels", () => {
        const s0 = createInitialAnswerStages();
        expect(s0.map((s) => s.id)).toEqual(["understand", "fetch_data", "quant_verify", "synthesize"]);
        expect(s0.map((s) => s.status)).toEqual(["in_progress", "pending", "pending", "pending"]);

        // Raw status code in message/content must NOT replace the human Arabic label
        const s0Raw = advanceAnswerStagesOnStatus(s0, { status: "thinking", message: "thinking" });
        expect(s0Raw[0].label).toBe("فهم السؤال وتحديد السهم والسوق");

        // Advance to fetch_data with descriptive Arabic label
        const s1 = advanceAnswerStagesOnStatus(s0Raw, {
            step_id: "fetch_data",
            status: "executing_tools",
            message: "جلب البيانات الحية (الأسعار والمؤشرات • القيمة العادلة)",
        });
        expect(s1.map((s) => s.status)).toEqual(["done", "in_progress", "pending", "pending"]);
        expect(s1[1].label).toContain("الأسعار والمؤشرات");

        // Advance to quant_verify
        const s2 = advanceAnswerStagesOnStatus(s1, {
            step_id: "quant_verify",
            status: "quant_engine",
            message: "تشغيل المحرك الكمي ومحاكاة مونت كارلو (5,000 مسار) وحسم التعارض",
        });
        expect(s2.map((s) => s.status)).toEqual(["done", "done", "in_progress", "pending"]);

        // Advance to synthesize on generating / first token
        const s3 = advanceAnswerStagesOnToken(s2);
        expect(s3.map((s) => s.status)).toEqual(["done", "done", "done", "in_progress"]);

        // Finalize marks all completed
        const s4 = finalizeAnswerStages(s3, { toolsUsed: ["get_stock", "get_fair_value"] });
        expect(s4.map((s) => s.status)).toEqual(["done", "done", "done", "done"]);
    });

    test("shortcuts cleanly on cached hits and omits unused tool stages for simple direct replies", () => {
        const s0 = createInitialAnswerStages({ hasImages: true });
        expect(s0[0].label).toContain("قراءة الصورة");

        const cachedStages = advanceAnswerStagesOnStatus(s0, {
            step_id: "fetch_data",
            status: "cached",
            message: "تم استرجاع أحدث قراءة فنية موثقة من الذاكرة اللحظية...",
        });
        expect(cachedStages.map((s) => s.id)).toEqual(["understand", "fetch_data", "synthesize"]);
        expect(cachedStages.map((s) => s.status)).toEqual(["done", "done", "in_progress"]);

        // Simple non-tool query jumping straight from understand to tokens
        const directTokenStages = advanceAnswerStagesOnToken(createInitialAnswerStages());
        expect(directTokenStages.map((s) => s.id)).toEqual(["understand", "synthesize"]);
        expect(directTokenStages.map((s) => s.status)).toEqual(["done", "in_progress"]);
        expect(finalizeAnswerStages(directTokenStages).map((s) => s.status)).toEqual(["done", "done"]);
    });

    test("AnswerStagesChecklist renders streaming checklist with stop button and collapses once completed", () => {
        const onStop = jest.fn();
        const streamingStages = advanceAnswerStagesOnStatus(createInitialAnswerStages(), {
            step_id: "quant_verify",
            status: "quant_engine",
            message: "تشغيل المحرك الكمي ومحاكاة مونت كارلو (5,000 مسار) وحسم التعارض",
        });

        const { rerender } = render(
            <AnswerStagesChecklist stages={streamingStages} isStreaming={true} onStop={onStop} language="ar" />
        );

        expect(screen.getByTestId("answer-stages-checklist")).toBeTruthy();
        expect(screen.getByText("2/4")).toBeTruthy();
        expect(screen.getAllByText("تم ✓").length).toBe(2);
        expect(screen.getByText("جاري...")).toBeTruthy();
        expect(screen.getByText("انتظار")).toBeTruthy();

        fireEvent.click(screen.getByText("إيقاف"));
        expect(onStop).toHaveBeenCalledTimes(1);

        const doneStages = finalizeAnswerStages(streamingStages, { toolsUsed: ["get_stock"] });
        rerender(<AnswerStagesChecklist stages={doneStages} isStreaming={false} language="ar" />);

        // Collapses to concise summary pill after streaming completes
        expect(screen.queryByTestId("answer-stages-checklist")).toBeNull();
        const expandBtn = screen.getByText("اكتملت مراحل التحليل والتحقق (4/4)");
        fireEvent.click(expandBtn);

        expect(screen.getByTestId("answer-stages-checklist")).toBeTruthy();
        expect(screen.getAllByText("تم ✓").length).toBe(4);
    });
});
