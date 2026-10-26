import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";

// GET /api/portfolio — current user's holdings + cash + live valuation + market symbols list
export async function GET() {
    try {
        const supabase = await createSupabaseServerClient();
        const { data: { user }, error: authError } = await supabase.auth.getUser();
        if (authError || !user) {
            return NextResponse.json({ ok: false, requiresAuth: true, message: "يجب تسجيل الدخول أولاً لإضافة الأسهم إلى محفظتك الشخصية." }, { status: 401 });
        }

        const { getPortfolioSnapshot } = await import("@/lib/ai/portfolio-tools");
        const snapshot = await getPortfolioSnapshot(supabase, user.id);
        const { data: planRows } = await supabase.from("subscriptions").select("plan_id,status,current_period_end").eq("user_id", user.id).limit(10);
        const { hasActiveProSubscription, planLimits } = await import("@/lib/ai/plan-gate");
        const pro = hasActiveProSubscription(planRows || []);
        const portfolioLimit = planLimits(pro ? "pro" : "free").portfolio_stocks;

        // Real EGX symbols for the profile-page autocomplete selector
        let marketSymbols: Array<{ symbol: string; name: string | null }> = [];
        try {
            const { data: symbolsRows } = await supabase
                .from("stocks")
                .select("symbol, name")
                .order("symbol", { ascending: true })
                .limit(500);
            marketSymbols = (symbolsRows || []).map((r: any) => ({ symbol: r.symbol, name: r.name || null }));
        } catch (e) {
            console.warn("[api/portfolio] symbols list unavailable:", e);
        }

        return NextResponse.json(
            { ...snapshot, market_symbols: marketSymbols, portfolio_limit: pro ? null : portfolioLimit, is_pro: pro },
            { headers: { "Cache-Control": "private, no-cache, no-store, must-revalidate" } },
        );
    } catch (e: any) {
        console.error("[api/portfolio] GET error:", e);
        return NextResponse.json({ ok: false, message: e?.message || "Internal error" }, { status: 500 });
    }
}

// POST /api/portfolio — manual edits from the profile page
// body: { action: "add" | "update" | "remove" | "sell" | "cash_set", symbol?, quantity?, price? }
export async function POST(req: NextRequest) {
    try {
        const supabase = await createSupabaseServerClient();
        const { data: { user }, error: authError } = await supabase.auth.getUser();
        if (authError || !user) {
            return NextResponse.json({ ok: false, requiresAuth: true, error: "Unauthorized", message: "يجب تسجيل الدخول أولاً لإضافة الأسهم إلى محفظتك الشخصية." }, { status: 401 });
        }

        const body = await req.json().catch(() => ({}));
        const action = String(body.action || "");
        const symbol = body.symbol ? String(body.symbol).trim().toUpperCase() : "";
        const quantity = body.quantity !== undefined && body.quantity !== null && body.quantity !== "" ? Number(body.quantity) : null;
        const price = body.price !== undefined && body.price !== null && body.price !== "" ? Number(body.price) : null;

        const tools = await import("@/lib/ai/portfolio-tools");
        let result: { ok: boolean; message: string };
        switch (action) {
            case "extract_and_save":
            case "ai_extract_and_save": {
                const text = String(body.text || "").trim();
                const userQuery = body.userQuery ? String(body.userQuery).trim() : "";
                const suggestedButtons = Array.isArray(body.suggestedButtons) ? body.suggestedButtons.map(String) : [];

                if (!text && !userQuery) {
                    return NextResponse.json({ ok: false, message: "محتوى الرسالة فارغ، لا يمكن استخراج الأسهم." }, { status: 400 });
                }
                const { callExtractionLLM } = await import("@/lib/ai/portfolio-extract");
                const extracted = await callExtractionLLM({ text, userQuery, suggestedButtons });

                if (!Array.isArray(extracted) || extracted.length === 0) {
                    return NextResponse.json({
                        ok: false,
                        message: "لم يكتشف الذكاء الاصطناعي أي أسهم صريحة للبورصة المصرية في هذا الرد لحفظها.",
                    });
                }

                const preparedItems: Array<{ symbol: string; quantity: number; price: number | null }> = [];
                for (const item of extracted) {
                    const sym = String(item.symbol || "").trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
                    if (!sym || sym.length < 2 || sym.length > 8) continue;

                    const qty = item.quantity && Number(item.quantity) > 0 ? Number(item.quantity) : 100;
                    let p = item.price && Number(item.price) > 0 ? Number(item.price) : null;

                    if (p === null) {
                        try {
                            const { data: priceRow } = await supabase
                                .from("stock_prices")
                                .select("close")
                                .eq("symbol", sym)
                                .order("date", { ascending: false })
                                .limit(1)
                                .maybeSingle();

                            if (priceRow?.close && Number(priceRow.close) > 0) {
                                p = Number(priceRow.close);
                            }
                        } catch {}
                    }

                    preparedItems.push({
                        symbol: sym,
                        quantity: qty,
                        price: p || 10.0,
                    });
                }

                if (preparedItems.length === 0) {
                    return NextResponse.json({
                        ok: false,
                        message: "لم يتم التعرف على رموز صالحة لأسهم البورصة المصرية.",
                    });
                }

                const { data: planRows } = await supabase
                    .from("subscriptions")
                    .select("plan_id,status,current_period_end")
                    .eq("user_id", user.id)
                    .limit(10);
                const { isPro, planLimits } = await import("@/lib/ai/plan-gate");
                const pro = isPro(planRows || []);
                const limit = planLimits(pro ? "pro" : "free").portfolio_stocks;

                const { data: existingRows } = await supabase
                    .from("positions")
                    .select("symbol")
                    .eq("user_id", user.id)
                    .eq("status", "open");
                const currentSymbols = new Set((existingRows || []).map((r: any) => String(r.symbol || "").toUpperCase()));
                const newDistinctSymbols = new Set(preparedItems.map(p => p.symbol).filter(s => !currentSymbols.has(s)));

                if (!pro && (currentSymbols.size + newDistinctSymbols.size) > limit) {
                    return NextResponse.json({
                        ok: false,
                        isQuotaReached: true,
                        limit,
                        currentCount: currentSymbols.size,
                        attemptedCount: newDistinctSymbols.size,
                        stocks: preparedItems,
                        message: `الخطة المجانية تتيح حتى ${limit} أسهم في المحفظة (محفظتك الحالية بها ${currentSymbols.size} أسهم). قم بالترقية لباقة Pro لإدارة حتى 10 أسهم وتفعيل تنبيهات السوينج الحية!`,
                    });
                }

                const saveResult = await tools.bulkAddPortfolioPositions(supabase, user.id, preparedItems);
                return NextResponse.json({
                    ...saveResult,
                    isQuotaReached: !saveResult.ok && (saveResult.message.includes("الخطة المجانية") || saveResult.message.includes("الحد الأقصى")),
                    stocks: preparedItems,
                    addedCount: saveResult.addedCount || preparedItems.length,
                    message: saveResult.ok ? `تم بنجاح حفظ ${saveResult.addedCount || preparedItems.length} أسهم في محفظتك الشخصية!` : saveResult.message,
                });
            }
            case "bulk_add":
                if (!Array.isArray(body.items) || body.items.length === 0) {
                    return NextResponse.json({ ok: false, message: "قائمة الأسهم مطلوبة" }, { status: 400 });
                }
                result = await tools.bulkAddPortfolioPositions(supabase, user.id, body.items);
                break;
            case "add":
                if (!symbol || quantity === null || !Number.isFinite(quantity) || quantity <= 0) {
                    return NextResponse.json({ ok: false, message: "symbol و quantity مطلوبان" }, { status: 400 });
                }
                {
                    const { data: rows } = await supabase.from("positions").select("symbol").eq("user_id", user.id).eq("status", "open");
                    const { data: planRows } = await supabase.from("subscriptions").select("plan_id,status,current_period_end").eq("user_id", user.id).limit(10);
                    const { isPro, planLimits } = await import("@/lib/ai/plan-gate");
                    const pro = isPro(planRows || []);
                    const limit = planLimits(pro ? "pro" : "free").portfolio_stocks;
                    const currentSymbols = new Set((rows || []).map((row: any) => String(row.symbol || "").toUpperCase()));
                    if (!pro && !currentSymbols.has(symbol) && currentSymbols.size >= limit) return NextResponse.json({ ok: false, message: `الخطة المجانية تسمح بحد أقصى ${limit} أسهم مختلفة في المحفظة. احذف مركزاً أو قم بالترقية لإضافة سهم آخر.` }, { status: 403 });
                }
                result = await tools.addPortfolioPosition(supabase, user.id, symbol, quantity, price);
                break;
            case "update":
                if (!symbol) return NextResponse.json({ ok: false, message: "symbol مطلوب" }, { status: 400 });
                result = await tools.updatePortfolioPosition(supabase, user.id, symbol, quantity, price);
                break;
            case "remove":
                if (!symbol) return NextResponse.json({ ok: false, message: "symbol مطلوب" }, { status: 400 });
                result = await tools.removePortfolioPosition(supabase, user.id, symbol);
                break;
            case "sell":
                if (!symbol) return NextResponse.json({ ok: false, message: "symbol مطلوب" }, { status: 400 });
                result = await tools.sellPortfolioPosition(supabase, user.id, symbol, quantity, price);
                break;
            case "cash_set":
                if (quantity === null || !Number.isFinite(quantity) || quantity < 0) {
                    return NextResponse.json({ ok: false, message: "قيمة السيولة مطلوبة" }, { status: 400 });
                }
                result = await tools.setPortfolioCash(supabase, user.id, quantity);
                break;
            case "cash_add":
                if (quantity === null || !Number.isFinite(quantity) || quantity <= 0) {
                    return NextResponse.json({ ok: false, message: "قيمة الإيداع مطلوبة" }, { status: 400 });
                }
                result = await tools.addPortfolioCash(supabase, user.id, quantity);
                break;
            default:
                return NextResponse.json({ ok: false, message: "action غير معروف" }, { status: 400 });
        }

        return NextResponse.json(result);
    } catch (e: any) {
        console.error("[api/portfolio] POST error:", e);
        return NextResponse.json({ ok: false, message: e?.message || "Internal error" }, { status: 500 });
    }
}
