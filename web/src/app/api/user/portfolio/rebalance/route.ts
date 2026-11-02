import { NextRequest, NextResponse } from "next/server";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { getPublicMarketClient, getSupabaseServiceClient } from "@/lib/supabase/route-data";
import { getCairoDateString, planLimits, resolveSubscriptionQuotaWindow } from "@/lib/ai/plan-gate";
import { getDeepSeekApiKey, isUnlimitedChatUser } from "@/lib/ai/server-secrets";
import { AI_CONFIG } from "@/lib/ai/config";
import { computeFairValueReport } from "@/lib/market/fair-value";
import { CANONICAL_STOCK_NAMES } from "@/lib/ai/stock-names";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
export const preferredRegion = "fra1";

export interface HoldingRebalanceDiagnosis {
  symbol: string;
  nameAr: string;
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  marketValue: number;
  weightPct: number;
  pnlPct: number;
  fairValue: number | null;
  upsidePct: number | null;
  rsi14: number | null;
  relativeVolume: number | null;
  action: "HOLD_ACCUMULATE" | "TRIM_PROFIT" | "ROTATE_OUT";
  actionLabelAr: string;
  suggestedTrimPct: number;
  freedCashEgp: number;
  reasonAr: string;
}

export interface ReplacementCandidate {
  symbol: string;
  nameAr: string;
  sectorAr: string;
  currentPrice: number;
  fairValue: number;
  upsidePct: number;
  rsi14: number | null;
  relativeVolume: number;
  suggestedAllocationEgp: number;
  suggestedShares: number;
  stopLoss: number;
  targetPrice: number;
  catalystAr: string;
}

export async function POST(req: NextRequest) {
  try {
    const supabase = await createSupabaseServerClient(req);
    const {
      data: { user },
      error: authError,
    } = await supabase.auth.getUser();

    if (authError || !user) {
      return NextResponse.json({ error: "يرجى تسجيل الدخول أولاً" }, { status: 401 });
    }

    const serviceClient = getSupabaseServiceClient();
    const now = new Date();
    const today = getCairoDateString(now);
    const calMonthStartStr = `${today.slice(0, 7)}-01`;

    // 1. Fetch positions, profile, subscriptions, and current quota usage in parallel
    const [posRes, profileRes, subRes, limitRowsRes] = await Promise.all([
      supabase
        .from("positions")
        .select("id, symbol, quantity, entry_price, target_price, stop_loss_price, created_at")
        .eq("user_id", user.id)
        .eq("status", "open")
        .limit(50),
      serviceClient
        .from("profiles")
        .select("cash_balance")
        .eq("id", user.id)
        .maybeSingle(),
      serviceClient
        .from("subscriptions")
        .select("id, plan_id, status, current_period_start, current_period_end, created_at")
        .eq("user_id", user.id)
        .in("status", ["active", "trialing"])
        .order("current_period_end", { ascending: false })
        .limit(5),
      serviceClient
        .from("ai_chatbot_limits")
        .select("date, chat_count")
        .eq("user_id", user.id)
        .gte("date", calMonthStartStr),
    ]);

    const openPositions = posRes.data || [];
    if (openPositions.length === 0) {
      return NextResponse.json(
        { error: "محفظتك فارغة حالياً. أضف أسهماً إلى محفظتك أولاً لتشغيل إعادة التدوير الذكي." },
        { status: 400 }
      );
    }

    // 2. Enforce & deduct 1 AI chat quota message atomically
    const isUnlimited = isUnlimitedChatUser(user);
    const quotaWin = resolveSubscriptionQuotaWindow(subRes.data || [], now);
    const userIsPro = quotaWin.isPro || isUnlimited;
    const planName = userIsPro
      ? quotaWin.activeSub?.plan_id === "lifetime" || isUnlimited
        ? "lifetime"
        : "pro"
      : "free";
    const limits = planLimits(planName);
    const userMonthlyCap = limits.chat_messages_per_month;
    const monthStartStr = userIsPro ? quotaWin.effectiveMonthStartStr : calMonthStartStr;

    const effectiveLimitRows = (limitRowsRes.data || []).filter(
      (r: any) => String(r.date || "") >= monthStartStr
    );
    let monthlyUsed = effectiveLimitRows.reduce(
      (acc: number, row: any) => acc + (Number(row.chat_count) || 0),
      0
    );

    if (!isUnlimited) {
      if (monthlyUsed >= userMonthlyCap) {
        const { data: bonusRes } = await serviceClient.rpc("consume_chat_bonus", {
          p_user_id: user.id,
        });
        if (!bonusRes || bonusRes.allowed !== true) {
          return NextResponse.json(
            {
              error: "LIMIT_REACHED",
              detail: `لقد استهلكت كامل كوتا الشات الذكي (${userMonthlyCap}/${userMonthlyCap} رسالة). قم بالترقية إلى باقة Pro للحصول على 350 رسالة شهرياً وإعادة تدوير محفظتك بلا قيود.`,
            },
            { status: 429 }
          );
        }
      } else {
        const effectiveDailyLimit = userIsPro
          ? Math.max(AI_CONFIG.limits.dailyMessages, userMonthlyCap)
          : Math.max(10, userMonthlyCap);
        const { data: quotaRows, error: quotaError } = await serviceClient.rpc(
          "consume_ai_chat_quota",
          {
            p_user_id: user.id,
            p_date: today,
            p_limit: effectiveDailyLimit,
          }
        );
        if (quotaError) {
          return NextResponse.json({ error: "تعذر خصم الكوتا حالياً" }, { status: 503 });
        }
        const quota = Array.isArray(quotaRows) ? quotaRows[0] : quotaRows;
        if (!quota?.allowed) {
          const { data: bonusRes } = await serviceClient.rpc("consume_chat_bonus", {
            p_user_id: user.id,
          });
          if (!bonusRes || bonusRes.allowed !== true) {
            return NextResponse.json(
              {
                error: "LIMIT_REACHED",
                detail: `لقد استهلكت كوتا الشات المتاحة (${userMonthlyCap} رسالة). قم بالترقية إلى باقة Pro للمتابعة.`,
              },
              { status: 429 }
            );
          }
        }
      }
      monthlyUsed += 1;
    }

    const remainingQuota = isUnlimited ? 999 : Math.max(0, userMonthlyCap - monthlyUsed);

    // 3. Load cached market indicators and fundamentals
    const marketClient = getPublicMarketClient();
    const [fundRes, indRes] = await Promise.all([
      marketClient
        .from("stock_fundamentals")
        .select("symbol, name, name_ar, data, updated_at")
        .eq("exchange", "EGX")
        .limit(400),
      marketClient
        .from("stock_technical_indicators")
        .select("symbol, date, close, volume, ema_20, ema_50, ema_200, sma_200, vwap_20, change_pct, rsi_14, r_vol, atr_14")
        .eq("exchange", "EGX")
        .limit(400),
    ]);

    const fairValueReport = computeFairValueReport(fundRes.data || [], indRes.data || []);
    const fvMap = new Map(fairValueReport.stocks.map((s) => [s.symbol, s]));
    const indMap = new Map<string, any>();
    for (const r of indRes.data || []) {
      if (r.symbol) indMap.set(String(r.symbol).trim().toUpperCase(), r);
    }

    const cashBalance = Number(profileRes.data?.cash_balance || 0);
    let totalStocksValue = 0;

    const rawHoldings = openPositions.map((pos: any) => {
      const sym = String(pos.symbol || "").trim().toUpperCase();
      const qty = Math.max(0, Number(pos.quantity) || 0);
      const entry = Math.max(0, Number(pos.entry_price) || 0);
      const ind = indMap.get(sym);
      const fv = fvMap.get(sym);
      const currentPrice = Number(ind?.close || fv?.currentPrice || entry || 0);
      const marketValue = qty * currentPrice;
      totalStocksValue += marketValue;
      return { sym, qty, entry, currentPrice, marketValue, ind, fv };
    });

    const totalPortfolioEquity = Math.max(1, totalStocksValue + cashBalance);
    let totalFreedCash = 0;

    const holdingsDiagnosis: HoldingRebalanceDiagnosis[] = rawHoldings.map((h: any) => {
      const weightPct = Number(((h.marketValue / totalPortfolioEquity) * 100).toFixed(1));
      const pnlPct = h.entry > 0 ? Number((((h.currentPrice - h.entry) / h.entry) * 100).toFixed(2)) : 0;
      const rsi = h.ind?.rsi_14 != null ? Number(Number(h.ind.rsi_14).toFixed(1)) : null;
      const rVol = h.ind?.r_vol != null ? Number(Number(h.ind.r_vol).toFixed(2)) : null;
      const ema50 = Number(h.ind?.ema_50 || h.currentPrice);
      const fairValue = h.fv?.fairValue ?? null;
      const upsidePct = h.fv?.upsidePct ?? null;
      const nameAr = CANONICAL_STOCK_NAMES[h.sym]?.name_ar || h.fv?.nameAr || h.sym;

      let action: HoldingRebalanceDiagnosis["action"] = "HOLD_ACCUMULATE";
      let actionLabelAr = "احتفاظ واستمرار 🟢";
      let suggestedTrimPct = 0;
      let reasonAr = "السهم يتحرك في مسار متوازن فوق دعومه الفنية مع تقييم مالي مقبول.";

      const belowEma50 = h.currentPrice < ema50 * 0.975;
      const weakVolume = (rVol ?? 1) < 0.75;
      const overvalued = upsidePct !== null && upsidePct <= -15;
      const overweight = weightPct >= 42;

      if (belowEma50 && (weakVolume || (rsi !== null && rsi < 44))) {
        action = "ROTATE_OUT";
        actionLabelAr = "تدوير السيولة (سهم راكد) 🔄";
        suggestedTrimPct = 50;
        reasonAr = "السهم يتداول أسفل متوسط 50 يوماً مع ضعف في السيولة النسبية؛ يُنصح بتدوير نصف السيولة لفرصة أسرع زخماً.";
      } else if (overvalued && pnlPct > 5) {
        action = "ROTATE_OUT";
        actionLabelAr = "تدوير السيولة (متضخم سعرياً) 🔄";
        suggestedTrimPct = 40;
        reasonAr = `السهم يتداول أعلى من سعره العادل المحسوب (${fairValue} ج.م)؛ تدوير 40% يحمي أرباحك.`;
      } else if (overweight) {
        action = "TRIM_PROFIT";
        actionLabelAr = "تخفيف التركز القطاعي 🟡";
        suggestedTrimPct = 25;
        reasonAr = `وزن السهم يمثل ${weightPct}% من إجمالي المحفظة وهو تركز مرتفع؛ يُنصح بتخفيف 25% لتوزيع المخاطر.`;
      } else if (pnlPct >= 14 && rsi !== null && rsi >= 68) {
        action = "TRIM_PROFIT";
        actionLabelAr = "جني أرباح جزئي 🟡";
        suggestedTrimPct = 30;
        reasonAr = `السهم حقق ربحاً ممتازاً (+${pnlPct}%) مع اقتراب مؤشر RSI (${rsi}) من مناطق التشبع الشرائي.`;
      } else if (upsidePct !== null && upsidePct >= 20 && !belowEma50) {
        action = "HOLD_ACCUMULATE";
        actionLabelAr = "احتفاظ / فرصة واعدة 💎";
        suggestedTrimPct = 0;
        reasonAr = `السهم أرخص من قيمته العادلة (${fairValue} ج.م) بخصم +${upsidePct}% ويحافظ على زخمه الفني.`;
      }

      const freedCashEgp = Math.round(h.marketValue * (suggestedTrimPct / 100));
      totalFreedCash += freedCashEgp;

      return {
        symbol: h.sym,
        nameAr,
        quantity: h.qty,
        entryPrice: h.entry,
        currentPrice: h.currentPrice,
        marketValue: Math.round(h.marketValue),
        weightPct,
        pnlPct,
        fairValue,
        upsidePct,
        rsi14: rsi,
        relativeVolume: rVol,
        action,
        actionLabelAr,
        suggestedTrimPct,
        freedCashEgp,
        reasonAr,
      };
    });

    const deployableCash = Math.round(totalFreedCash + cashBalance * 0.7);
    const heldSymbols = new Set(rawHoldings.map((h: any) => h.sym));

    // 4. Select Top 3 Replacement Candidates (Undervalued + Positive Technical Momentum)
    const candidatePool = fairValueReport.stocks.filter((st) => {
      if (heldSymbols.has(st.symbol)) return false;
      const ind = indMap.get(st.symbol);
      if (!ind || !st.currentPrice || st.currentPrice <= 0) return false;
      const ema50 = Number(ind.ema_50 || st.currentPrice);
      const rVol = Number(ind.r_vol || 0);
      const rsi = Number(ind.rsi_14 || 50);
      return (
        st.upsidePct >= 12 &&
        st.currentPrice >= ema50 * 0.99 &&
        rsi >= 46 &&
        rsi <= 68 &&
        rVol >= 0.85
      );
    });

    candidatePool.sort((a, b) => {
      const rVolA = Number(indMap.get(a.symbol)?.r_vol || 1);
      const rVolB = Number(indMap.get(b.symbol)?.r_vol || 1);
      return b.upsidePct * 0.6 + rVolB * 15 - (a.upsidePct * 0.6 + rVolA * 15);
    });

    const topReplacements = candidatePool.slice(0, 3);
    const perStockAllocation =
      topReplacements.length > 0
        ? Math.max(2500, Math.round(deployableCash / topReplacements.length))
        : 0;

    const replacements: ReplacementCandidate[] = topReplacements.map((st) => {
      const ind = indMap.get(st.symbol);
      const atr = Number(ind?.atr_14 || st.currentPrice * 0.035);
      const rVol = Number(Number(ind?.r_vol || 1.0).toFixed(2));
      const stopLoss = Number(Math.max(0.01, st.currentPrice - 2 * atr).toFixed(2));
      const targetPrice = Number(Math.min(st.fairValue, st.currentPrice + 3.5 * atr).toFixed(2));
      const suggestedShares = Math.max(1, Math.floor(perStockAllocation / st.currentPrice));

      return {
        symbol: st.symbol,
        nameAr: st.nameAr,
        sectorAr: st.sectorAr,
        currentPrice: st.currentPrice,
        fairValue: st.fairValue,
        upsidePct: st.upsidePct,
        rsi14: st.rsi14,
        relativeVolume: rVol,
        suggestedAllocationEgp: perStockAllocation,
        suggestedShares,
        stopLoss,
        targetPrice,
        catalystAr: `يتداول بخصم +${st.upsidePct}% عن سعره العادل (${st.fairValue} ج.م) مع سيولة تجميعية (${rVol}x) أعلى من متوسط 50 جلسة.`,
      };
    });

    // Calculate overall portfolio health score (0-100)
    const rotateCount = holdingsDiagnosis.filter((h) => h.action === "ROTATE_OUT").length;
    const maxWeight = Math.max(...holdingsDiagnosis.map((h) => h.weightPct), 0);
    let healthScore = 84 - rotateCount * 12 - (maxWeight > 50 ? 12 : maxWeight > 35 ? 5 : 0);
    healthScore = Math.max(38, Math.min(96, Math.round(healthScore)));

    // 5. Generate concise AI Executive Advisory via DeepSeek-V3 (with deterministic fallback)
    let aiAdvisory =
      rotateCount > 0
        ? `محفظتك تحتوي على ${rotateCount} مراكز بطيئة الحركة أو متضخمة سعرياً. بتحرير نحو ${totalFreedCash.toLocaleString("en-US")} ج.م وإعادة توجيهها نحو الأسهم المقترحة ذات الخصم المالي والزخم المؤسسي، سترفع كفاءة دوران رأس المال وتقلل مخاطر التركز.`
        : `توزيع محفظتك الحالي متماسك وفوق مستويات الدعم الرئيسية. يمكنك استغلال السيولة المتاحة أو جني الأرباح الجزئي من الأسهم المرتفعة لاقتناص الفرص الرخيصة استثمارياً في القائمة المرشحة.`;

    const deepseekKey = getDeepSeekApiKey();
    if (deepseekKey) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 12000);
        const prompt = `أنت مستشار مالي خبير في البورصة المصرية (EGX). لخص في 3 جمل عربية واضحة ومباشرة خطة إعادة تدوير المحفظة التالية:
- التقييم الصحي للمحفظة: ${healthScore}/100
- المراكز الحالية: ${holdingsDiagnosis.map((h) => `${h.symbol} (${h.actionLabelAr}, ربح/خسارة ${h.pnlPct}%, وزن ${h.weightPct}%)`).join(" | ")}
- السيولة المقترح تحريرها للتدوير: ${totalFreedCash} ج.م + كاش متاح ${cashBalance} ج.م
- الأسهم البديلة المرشحة: ${replacements.map((r) => `${r.symbol} (سعر ${r.currentPrice}, عادل ${r.fairValue}, مستهدف ${r.targetPrice})`).join(" | ")}
اكتب نصيحة عملية مركزة بدون مقدمات إنشائية.`;

        const llmRes = await fetch("https://api.deepseek.com/chat/completions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${deepseekKey}`,
          },
          body: JSON.stringify({
            model: "deepseek-chat",
            messages: [{ role: "user", content: prompt }],
            max_tokens: 240,
            temperature: 0.3,
          }),
          signal: controller.signal,
        });
        clearTimeout(timer);
        if (llmRes.ok) {
          const json = await llmRes.json();
          const txt = json?.choices?.[0]?.message?.content?.trim();
          if (txt && txt.length > 20) {
            aiAdvisory = txt;
          }
        }
      } catch {
        // Fallback advisory already populated
      }
    }

    return NextResponse.json({
      healthScore,
      totalPortfolioEquity: Math.round(totalPortfolioEquity),
      cashBalance: Math.round(cashBalance),
      totalFreedCash: Math.round(totalFreedCash),
      deployableCash: Math.round(deployableCash),
      remainingQuota,
      aiAdvisory,
      holdings: holdingsDiagnosis,
      replacements,
    });
  } catch (err: any) {
    console.error("[api/user/portfolio/rebalance] error:", err);
    return NextResponse.json(
      { error: "حدث خطأ أثناء تحليل وإعادة تدوير المحفظة" },
      { status: 500 }
    );
  }
}
