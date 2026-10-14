import fs from "fs";
import path from "path";

try {
    const envPath = path.resolve(process.cwd(), ".env.local");
    if (fs.existsSync(envPath)) {
        const content = fs.readFileSync(envPath, "utf-8");
        for (const line of content.split("\n")) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith("#")) continue;
            const eqIdx = trimmed.indexOf("=");
            if (eqIdx > 0) {
                const key = trimmed.slice(0, eqIdx).trim();
                const val = trimmed.slice(eqIdx + 1).trim().replace(/^["']|["']$/g, "");
                if (!process.env[key]) process.env[key] = val;
            }
        }
    }
} catch (e) {}

import { runAgenticPipelineStream } from "../agentic-pipeline";
import { getSupabaseServiceClient } from "@/lib/supabase/route-data";

describe("User Session Audit Verification (Oct 14 queries)", () => {
    jest.setTimeout(90000);

    const questions = [
        {
            id: 1,
            title: "السؤال 1 (DCRC هات أخباره وشوف ليه طلع كده)",
            prompt: "DCRC هات اخباره وشوف ليه طلع كده"
        },
        {
            id: 2,
            title: "السؤال 2 (رشحلي الأسهم RSI < 60 وحجم > 1 وقرب المقاومة)",
            prompt: "رشحلي الأسهم اللي الـ RSI بتاعها تحت 60 وحجم التداول أعلى من المتوسط وقريبة من المقاومة"
        },
        {
            id: 3,
            title: "السؤال 3 (هات إقفال سهم قره من أسبوع)",
            prompt: "هات اقفال سهم قره من اسبوع"
        }
    ];

    for (const q of questions) {
        test(q.title, async () => {
            const db = getSupabaseServiceClient();
            const events: any[] = [];
            const toolsUsed: string[] = [];

            console.log(`\n======================================================`);
            console.log(`بدء اختبار: ${q.title}`);
            console.log(`نص السؤال: "${q.prompt}"`);
            console.log(`======================================================`);

            const stream = runAgenticPipelineStream(
                q.prompt,
                [], // images
                { current_symbol: null, last_symbols: [], summary: null },
                null,
                [],
                db,
                [],
                "test-user-admin-audit",
                "test-session-audit-" + q.id,
                "test-msg-" + Date.now(),
                undefined,
                { timeoutMs: 45000 }
            );

            let finalReply = "";
            let finalReview: any = null;
            let responseOrigin = "unknown";

            for await (const chunk of stream) {
                events.push(chunk);
                if (chunk.type !== "token") {
                    console.log(`[CHUNK]: ${chunk.type}`, JSON.stringify(chunk.data)?.slice(0, 300));
                }
                if (chunk.type === "plan" && Array.isArray(chunk.data?.tools)) {
                    toolsUsed.push(...chunk.data.tools);
                    console.log(`  -> الأدوات المستدعاة: ${chunk.data.tools.join(", ")}`);
                }
                if (chunk.type === "done") {
                    finalReply = chunk.data?.reply || chunk.data?.response || "";
                    finalReview = chunk.data?.publication_review;
                    responseOrigin = chunk.data?.response_origin || "unknown";
                }
            }

            console.log(`\n[الأدوات المنفذة]: ${toolsUsed.join(", ")}`);
            console.log(`[مصدر الرد]: ${responseOrigin}`);
            console.log(`[اجتياز النشر]: ${finalReview?.final_passed ?? finalReview?.passed}`);
            if (finalReview?.reasons?.length) {
                console.log(`[أسباب المراجعة إن وجدت]: ${JSON.stringify(finalReview.reasons)}`);
            }
            console.log(`\n[الرد الكامل المعروض للمستخدم في الشات]:`);
            console.log(`------------------------------------------------------`);
            console.log(finalReply);
            console.log(`------------------------------------------------------\n`);

            expect(finalReply).toBeTruthy();
            expect(finalReply.length).toBeGreaterThan(30);

            if (q.id === 1) {
                // Must mention DCRC and news situation (no news / speculative move / lack of disclosures)
                expect(finalReply).toMatch(/(?:DCRC|الدلتا للسكر)/i);
                expect(finalReply).toMatch(/(?:أخبار|اخبار|إفصاحات|افصاحات|مضارب|إعلان)/i);
            } else if (q.id === 2) {
                // Must render table or stocks matching criteria
                expect(finalReply).toMatch(/(?:EGSA|FAITA|جدول|RSI|مقاوم)/i);
            } else if (q.id === 3) {
                // Must mention KORA and historic closing price (6.50 on 2026-10-07 or past week session)
                expect(finalReply).toMatch(/(?:KORA|قره|قناة السويس)/i);
                expect(finalReply).toMatch(/(?:6\.5|6\.50|2026-10-07|الأسبوع الماضي|جلسة)/);
            }
        });
    }
});
