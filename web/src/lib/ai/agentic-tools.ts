import { summarizeStockHistory } from "./stock-history";
import { executeLiveQuoteTool } from "./live-quote-tool";
import { reconcileStockQuote, stockPricePresentation, stockQuoteMetadata } from "./stock-quote";
import { PLANNED_READ_TOOL_NAMES, executePlannedReadTool } from "./planned-read-tools";
import { executionSupabase } from "./execution";
import { executeChartStrategyTool, type ChartHistoryCache } from "./chart-strategy-tools";
import { sanitizeNewsRows } from "./news-evidence";
import { todayInCairo } from "./cairo-date";
import { hasActiveProSubscription, paymentsEnabled, planLimits } from "./plan-gate";
import { isShariaCompliant, getShariaCompliantCount, SHARIA_COMPLIANT_EGX_SYMBOLS } from "@/lib/shariaStocks";

const normalizeSymbol = (value: unknown) => String(value).trim().toUpperCase().replace(/\.CA$/i, "");
const finite = (value: unknown): number | null => value == null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
const round = (value: number | null) => value == null ? null : Number(value.toFixed(2));
function positive(value: unknown): number { const n = finite(value); if (n == null || n <= 0) throw new Error("الكمية والسعر يجب أن يكونا أرقاماً محدودة أكبر من صفر"); return n; }

const PORTFOLIO_PROFILE_ACTION = { url: "/profile#portfolio", label: "افتح البروفايل عند قسم محفظتي" };

/** The model supplies operation and values. This reports an attempted write outcome only. */
function portfolioFailure(operation: string, failureKind: string, message: string) {
    return { status: "error", ok: false, operation, persisted: false, failure_kind: failureKind,
        message, profile_action: PORTFOLIO_PROFILE_ACTION };
}

/** One query boundary: Supabase resolves read failures instead of throwing them. */
function checkedClient(client: any): any {
    const wrap = (target: any): any => new Proxy(target, { get(obj,key) {
        const value = obj[key];
        if (typeof value !== "function") return value;
        if (key === "then") return (yes:any,no:any) => Promise.resolve(obj).then((result:any) => {
            if (result?.error) throw new Error("تعذر إكمال عملية قاعدة البيانات؛ لا تعتبر النتيجة فارغة أو العملية ناجحة");
            return result;
        }).then(yes,no);
        return (...args:any[]) => { const next = value.apply(obj,args); return next && typeof next === "object" && typeof next.then === "function" ? wrap(next) : next; };
    }});
    return { from: (table:string) => wrap(client.from(table)) };
}

export function cairoTimeframeBounds(now = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA",{timeZone:"Africa/Cairo",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(now);
    const part = (kind:string) => Number(parts.find(p=>p.type === kind)?.value);
    const year = part("year"), month = part("month"), day = part("day");
    const tz = new Intl.DateTimeFormat("en-GB",{timeZone:"Africa/Cairo",timeZoneName:"longOffset"}).formatToParts(now).find(p=>p.type === "timeZoneName")?.value || "GMT+02:00";
    const offset = /GMT([+-])(\d{2}):(\d{2})/.exec(tz);
    const minutes = offset ? (Number(offset[2])*60+Number(offset[3]))*(offset[1] === "+" ? 1 : -1) : 120;

    const toUtcIso = (y: number, m: number, d: number) => {
        const utcDate = new Date(Date.UTC(y, m - 1, d));
        return new Date(utcDate.getTime() - minutes * 60000).toISOString();
    };

    const thisMonthStartIso = toUtcIso(year, month, 1);
    const lastMonthYear = month === 1 ? year - 1 : year;
    const lastMonth = month === 1 ? 12 : month - 1;
    const lastMonthStartIso = toUtcIso(lastMonthYear, lastMonth, 1);
    const lastMonthEndIso = thisMonthStartIso;

    const localDay = new Date(Date.UTC(year, month - 1, day));
    localDay.setUTCDate(localDay.getUTCDate() - localDay.getUTCDay());
    const thisWeekStartIso = new Date(localDay.getTime() - minutes * 60000).toISOString();
    const prevSunday = new Date(localDay);
    prevSunday.setUTCDate(prevSunday.getUTCDate() - 7);
    const lastWeekStartIso = new Date(prevSunday.getTime() - minutes * 60000).toISOString();

    const last30DaysStartIso = new Date(now.getTime() - 30 * 24 * 3600 * 1000).toISOString();
    const last90DaysStartIso = new Date(now.getTime() - 90 * 24 * 3600 * 1000).toISOString();

    return {
        thisWeekStartIso,
        lastWeekStartIso,
        thisMonthStartIso,
        lastMonthStartIso,
        lastMonthEndIso,
        last30DaysStartIso,
        last90DaysStartIso,
        cairoDate: `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`
    };
}

export function cairoWeekBounds(now = new Date()) {
    const { thisWeekStartIso, lastWeekStartIso } = cairoTimeframeBounds(now);
    return { thisWeekStartIso, lastWeekStartIso };
}

export async function executeAgenticTool(toolName:string,args:Record<string,any>,supabase:any,userId:string,chartHistoryCache?:ChartHistoryCache):Promise<any> {
    try {
        const enums:Record<string,string[]> = {
            operation:["view","add","buy","purchase","update","remove","delete","sell"],
            preset:["momentum_and_volume","top_gainers","top_losers","rsi_oversold","macd_cross","smart_money_flow"],
            status:["open","closed","all"],
            timeframe:["this_week","last_week","this_month","last_month","last_30_days","last_90_days","all"]
        };
        if (args?.symbol != null && (typeof args.symbol !== "string" || !/^[A-Za-z0-9.]{2,12}$/.test(args.symbol.trim()))) throw new Error("رمز السهم غير صالح");
        if (!args || Array.isArray(args) || typeof args !== "object") throw new Error("مدخلات الأداة يجب أن تكون كائناً");
        const chartTool = ["list_chart_strategies", "apply_chart_strategy", "compare_strategies_history"].includes(toolName);
        for (const [key,values] of Object.entries(enums)) if (!(chartTool && key === "timeframe") && args[key] != null && !values.includes(String(args[key]).toLowerCase())) throw new Error("قيمة مدخل الأداة غير مدعومة: "+key);
        if (args.symbols != null && (!Array.isArray(args.symbols) || args.symbols.length > (toolName === "analyze_portfolio_risk" ? 30 : 10) || args.symbols.some((s:any)=>typeof s !== "string" || !/^[A-Za-z0-9.]{2,12}$/.test(s.trim())))) throw new Error("الحد الأقصى 10 رموز موثقة لكل أداة");
        if (["get_stock","get_stock_levels","get_comparison"].includes(toolName) && !args.symbols?.length) throw new Error("رموز الأسهم مطلوبة");
        const normalized = {...args, ...(args.symbols ? {symbols:Array.from(new Set(args.symbols.map(normalizeSymbol)))} : {})};
        if (toolName === "get_live_quote") return await executeLiveQuoteTool(normalized,checkedClient(executionSupabase(supabase)));
        if (PLANNED_READ_TOOL_NAMES.has(toolName)) return await executePlannedReadTool(toolName, normalized, checkedClient(executionSupabase(supabase)), todayInCairo());
        if (chartTool) return await executeChartStrategyTool(toolName, normalized, checkedClient(executionSupabase(supabase)), chartHistoryCache);
        return await executeRawTool(toolName,normalized,checkedClient(executionSupabase(supabase)),userId);
    } catch (error:any) {
        if (toolName === "manage_portfolio") {
            return portfolioFailure(String(args?.operation || "view").toLowerCase(), "tool_execution_failed", error?.message || "تعذر تنفيذ عملية المحفظة.");
        }
        return {status:"error", availability:"error", persisted:false, message:error.message};
    }
}

async function mapStockReads<T>(symbols: string[], read: (symbol: string) => Promise<T>): Promise<T[]> {
    const result: T[] = [];
    for (let offset = 0; offset < symbols.length; offset += 3)
        result.push(...await Promise.all(symbols.slice(offset, offset + 3).map(read)));
    return result;
}

function lockPosition(query:any, existing:any) {
    return existing.updated_at == null ? query.is("updated_at",null) : query.eq("updated_at",existing.updated_at);
}

async function executeRawTool(
    toolName: string,
    args: Record<string, any>,
    supabase: any,
    userId: string
): Promise<any> {
    try {
        if (toolName === "calculate_position") {
            if (!args.symbol) throw new Error("رمز السهم مطلوب لحساب المركز");
            const symbol = normalizeSymbol(args.symbol);
            let quantity = args.quantity == null ? null : positive(args.quantity);
            const suppliedEntry = args.entry_price == null ? null : positive(args.entry_price);
            const suppliedCost = args.total_cost == null ? null : positive(args.total_cost);
            if (quantity == null && suppliedCost == null) throw new Error("أدخل الكمية ومتوسط الشراء، أو التكلفة الإجمالية المعروفة");
            if (quantity != null && suppliedEntry == null && suppliedCost == null) throw new Error("مع الكمية، أدخل متوسط الشراء أو التكلفة الإجمالية المعروفة");
            const cost = suppliedCost ?? (quantity! * suppliedEntry!);
            if (quantity == null && suppliedCost != null && suppliedEntry != null) quantity = cost / suppliedEntry;
            const entry_price = suppliedEntry ?? (quantity != null ? cost / quantity : null);
            if (suppliedCost != null && quantity != null && suppliedEntry != null && Math.abs(quantity * suppliedEntry - suppliedCost) > 0.01)
                throw new Error("التكلفة الإجمالية لا تطابق الكمية ومتوسط الشراء");
            if (!Number.isFinite(cost) || (quantity != null && !Number.isFinite(quantity)) || (entry_price != null && !Number.isFinite(entry_price))) throw new Error("قيمة المركز تتجاوز حدود الحساب");
            const { data } = await supabase.from("stock_technical_indicators")
                .select("date,close").eq("exchange", "EGX").eq("symbol", symbol)
                .order("date", { ascending: false }).limit(1);
            const quote = await reconcileStockQuote(supabase, symbol, data?.[0]);
            const close = finite(quote?.close);
            const priced = close != null && close > 0 && Boolean(quote?.date || quote?.live_quote_available && quote?.fetched_at);
            const marketValue = priced && quantity != null ? quantity * close! : null;
            const profit = marketValue == null ? null : marketValue - cost;
            if (marketValue != null && !Number.isFinite(marketValue)) throw new Error("قيمة المركز تتجاوز حدود الحساب");
            return { status: "success", mode: "temporary_position", persisted: false,
                valuation_complete: priced && quantity != null, fees_included: false,
                positions: [{ symbol, quantity, entry_price, cost: round(cost),
                    close: priced ? close : null, date: priced ? quote.date : null, quote_source: quote?.quote_source ?? null,
                    ...stockQuoteMetadata(quote),
                    market_value: round(marketValue), profit_loss_val: round(profit),
                    profit_loss_pct: profit == null ? null : round(profit / cost * 100) }],
                formulas: { cost: suppliedCost != null ? "user_supplied_total_cost" : "quantity * entry_price", market_value: "quantity * close",
                    profit_loss_val: "market_value - cost", profit_loss_pct: "profit_loss_val / cost * 100" } };
        }
        if (toolName === "get_stock") {
            const symbols: string[] = Array.isArray(args.symbols)
                ? args.symbols.map(normalizeSymbol)
                : [];
            const results = await mapStockReads(symbols, async sym => {
                const { data: stockRows } = await supabase
                    .from("stocks")
                    .select("symbol, name, name_ar")
                    .eq("symbol", sym)
                    .limit(1);
                const stockData = stockRows?.[0] || { symbol: sym, name: sym, name_ar: sym };

                const { data: indRows } = await supabase
                    .from("stock_technical_indicators")
                    .select("date, close, change_pct, volume, r_vol, rsi_14, macd, macd_signal, macd_histogram, bb_upper, bb_lower, ema_50, ema_200, king_ai_score, egx_ai_score")
                    .eq("exchange", "EGX").eq("symbol", sym)
                    .order("date", { ascending: false })
                    .limit(1);

                const { data: wyckoffRows } = await supabase
                    .from("stock_scans_summary")
                    .select("scan_date, acc_score, dist_score, wyckoff_phase, vol_ratio, signal, consecutive_acc_days, consecutive_dist_days")
                    .eq("symbol", sym)
                    .order("scan_date", { ascending: false })
                    .limit(1);

                const { data: pRows } = await supabase
                    .from("stock_prices")
                    .select("high, low, close, date")
                    .eq("exchange", "EGX").eq("symbol", sym)
                    .order("date", { ascending: false })
                    .limit(25);

                const history = summarizeStockHistory(pRows || []);

                const ind = await reconcileStockQuote(supabase, sym, indRows?.[0]);
                if (!ind) {
                    return {
                        symbol: sym,
                        found_in_main_market: false,
                        availability: "missing",
                        market_type: null,
                        is_sharia_compliant: isShariaCompliant(sym),
                        sharia_index: isShariaCompliant(sym) ? "EGX33" : null,
                        message: `السهم ${sym} لا تتوفر له مؤشرات في المصدر المطلوب؛ غياب البيانات لا يحدد سوق القيد.`
                    };
                } else {
                    const wyckoff = wyckoffRows?.[0] || {};
                    return {
                        symbol: sym,
                        name: stockData.name_ar || stockData.name || sym,
                        found_in_main_market: true,
                        is_sharia_compliant: isShariaCompliant(sym),
                        sharia_index: isShariaCompliant(sym) ? "EGX33" : null,
                        date: ind.date,
                        quote_source: ind.quote_source,
                        indicators_date: ind.indicators_date,
                        indicators_stale: ind.indicators_stale,
                        indicators_available: ind.indicators_available ?? true,
                        ...stockQuoteMetadata(ind),
                        wyckoff_date: wyckoff.scan_date ?? null,
                        close: ind.close,
                        change_pct: ind.change_pct != null ? Number(ind.change_pct.toFixed(2)) : null,
                        relative_volume: ind.r_vol,
                        rsi_14: ind.rsi_14,
                        macd: ind.macd,
                        macd_signal: ind.macd_signal,
                        macd_hist: ind.macd_histogram,
                        ema_50: ind.ema_50,
                        ema_200: ind.ema_200,
                        bollinger_upper: ind.bb_upper,
                        bollinger_lower: ind.bb_lower,
                        king_ai_score: ind.king_ai_score,
                        egx_ai_score: ind.egx_ai_score,
                        wyckoff_phase: wyckoff.wyckoff_phase,
                        accumulation_score: wyckoff.acc_score,
                        distribution_score: wyckoff.dist_score,
                        consecutive_acc_days: typeof wyckoff.consecutive_acc_days === "number" ? wyckoff.consecutive_acc_days : null,
                        consecutive_dist_days: typeof wyckoff.consecutive_dist_days === "number" ? wyckoff.consecutive_dist_days : null,
                        ...history
                    };
                }
            });
            return { status: "success", stocks: results };
        }

        if (toolName === "get_stock_levels") {
            const symbols: string[] = Array.isArray(args.symbols)
                ? args.symbols.map(normalizeSymbol)
                : [];
            const levels = [];

            // Fetch live 15-minute intraday scanner signals map for fast lookup
            const scannerActiveMap = new Map<string, any>();
            try {
                const { data: botRow } = await supabase
                    .from("bot_states")
                    .select("state")
                    .eq("bot_id", "scanner_alerts")
                    .limit(1)
                    .maybeSingle();
                const activeList = Array.isArray(botRow?.state?.active_signals) ? botRow.state.active_signals : [];
                for (const s of activeList) {
                    if (s.symbol && !scannerActiveMap.has(String(s.symbol).toUpperCase())) {
                        scannerActiveMap.set(String(s.symbol).toUpperCase(), s);
                    }
                }
            } catch {
                // ignore query error
            }
            for (const sym of symbols) {
                const { data: pRows } = await supabase
                    .from("stock_prices")
                    .select("high, low, close, date")
                    .eq("exchange", "EGX").eq("symbol", sym)
                    .order("date", { ascending: false })
                    .limit(60);
                if (pRows && pRows.length > 0) {
                    const close = finite(pRows[0].close);
                    const recentRows = pRows.slice(0, 20);
                    const recentLows = recentRows.map((r: any) => Number(r.low ?? r.close)).filter((v: number) => Number.isFinite(v) && v > 0);
                    const recentHighs = recentRows.map((r: any) => Number(r.high ?? r.close)).filter((v: number) => Number.isFinite(v) && v > 0);
                    const allHighs = pRows.map((r: any) => Number(r.high ?? r.close)).filter((v: number) => Number.isFinite(v) && v > 0);
                    const allLows = pRows.map((r: any) => Number(r.low ?? r.close)).filter((v: number) => Number.isFinite(v) && v > 0);

                    const support = recentLows.length > 0 ? Number(Math.min(...recentLows).toFixed(2)) : null;
                    const resistance = recentHighs.length > 0 ? Number(Math.max(...recentHighs).toFixed(2)) : null;
                    const longTermResistance = allHighs.length > 0 ? Number(Math.max(...allHighs).toFixed(2)) : resistance;
                    const longTermSupport = allLows.length > 0 ? Number(Math.min(...allLows).toFixed(2)) : support;

                    const support2 = (longTermSupport != null && support != null && longTermSupport < support)
                        ? longTermSupport
                        : (support != null ? Number((support * 0.96).toFixed(2)) : null);
                    const resistance2 = (longTermResistance != null && resistance != null && longTermResistance > resistance)
                        ? longTermResistance
                        : (resistance != null ? Number((resistance * 1.05).toFixed(2)) : null);

                    const stopLoss = support != null ? Number((support * 0.98).toFixed(2)) : null;
                    const target1 = resistance;
                    const target2 = (longTermResistance != null && resistance != null && longTermResistance > resistance)
                        ? longTermResistance
                        : (resistance != null ? Number((resistance * 1.05).toFixed(2)) : null);

                    const entryZone = support != null
                        ? `${support} – ${Number((support * 1.02).toFixed(2))}`
                        : "غير محدد";

                    let hasActiveRecommendation = false;
                    let activeRecommendation: any = null;
                    try {
                        const { data: recRow } = await supabase
                            .from("scan_results")
                            .select("signal, entry_price, target_price, stop_loss, status, signal_date")
                            .eq("exchange", "EGX").eq("symbol", sym)
                            .in("status", ["open", "active"])
                            .order("created_at", { ascending: false })
                            .limit(1)
                            .maybeSingle();
                        if (recRow) {
                            hasActiveRecommendation = true;
                            activeRecommendation = recRow;
                        } else if (scannerActiveMap.has(sym.toUpperCase())) {
                            const match = scannerActiveMap.get(sym.toUpperCase());
                            hasActiveRecommendation = true;
                            activeRecommendation = {
                                signal: "BUY",
                                source: "15m_intraday_scanner",
                                entry_price: finite(match.entry_price),
                                target_price: finite(match.target_1),
                                target_2: finite(match.target_2),
                                stop_loss: finite(match.stop_loss),
                                status: "active",
                                signal_date: match.entry_date,
                                recommendation_type: match.scanner_type === "volume_surge"
                                    ? "⚡ مضاربة لحظية (انفجار سيولة)"
                                    : match.scanner_type === "breakout"
                                    ? "🚀 مضاربة لحظية (اختراق سعري)"
                                    : match.scanner_type === "rsi_oversold"
                                    ? "🧲 مضاربة لحظية (تشبع بيعي)"
                                    : "⚡ مضاربة لحظية (إسكان 15 دقيقة)"
                            };
                        }
                    } catch {
                        // ignore query error
                    }

                    let tradingZone = "منطقة حيادية للمراقبة (بين الدعم والمقاومة)";
                    if (support != null && close != null && close < support) {
                        tradingZone = "تحت مستوى الدعم (كسر دعم فني)";
                    } else if (resistance != null && close != null && close > resistance) {
                        tradingZone = "فوق مستوى المقاومة (اختراق فني)";
                    } else if (support != null && close != null && close <= support * 1.025) {
                        tradingZone = "عند منطقة الدعم تماماً (منطقة شراء وتجميع محتملة)";
                    } else if (resistance != null && close != null && close >= resistance * 0.975) {
                        tradingZone = "عند منطقة المقاومة تماماً (منطقة جني أرباح ومقاومة بيعية)";
                    }

                    const history = summarizeStockHistory(pRows);

                    levels.push({
                        symbol: sym,
                        is_sharia_compliant: isShariaCompliant(sym),
                        sharia_index: isShariaCompliant(sym) ? "EGX33" : null,
                        close,
                        support,
                        support_2: support2,
                        resistance,
                        resistance_2: resistance2,
                        distance_from_support_pct: close != null && close > 0 && support != null ? (support - close) / close * 100 : null,
                        distance_from_resistance_pct: close != null && close > 0 && resistance != null ? (resistance - close) / close * 100 : null,
                        distance_basis: "(level - close) / close * 100; negative=below close; positive=above close; absolute value for proximity",
                        entry_zone: entryZone,
                        stop_loss: stopLoss,
                        take_profit_1: target1,
                        take_profit_2: target2,
                        has_active_recommendation: hasActiveRecommendation,
                        active_recommendation: activeRecommendation,
                        trading_zone: tradingZone,
                        date: pRows[0].date,
                        ...history,
                        methodology: "20-session range for support/resistance; 60-session range for support2/resistance2; stop=98% support; target2=60-session high or 105% resistance",
                        observations: pRows.length, ...stockPricePresentation(pRows[0].date)
                    });
                } else {
                    levels.push({ symbol: sym, is_sharia_compliant: isShariaCompliant(sym), sharia_index: isShariaCompliant(sym) ? "EGX33" : null, availability: "missing", error: "لا يوجد تاريخ أسعار متاح؛ سوق القيد غير محدد" });
                }
            }
            return { status: "success", levels };
        }

        if (toolName === "manage_portfolio") {
            const rawOp = String(args.operation || "view").toLowerCase();
            const operation = ["buy", "purchase", "add"].includes(rawOp) ? "add" : rawOp;
            if (!userId) return portfolioFailure(operation, "authentication_required", "يلزم تسجيل الدخول لحفظ المراكز في المحفظة.");
            const symbol = args.symbol ? normalizeSymbol(args.symbol) : null;

            // Handle guest / unlinked Telegram users (userId is "tg_...") safely without querying Postgres with invalid UUID
            if (typeof userId === "string" && userId.startsWith("tg_")) {
                if (operation === "view") {
                    return {
                        status: "success",
                        operation: "view",
                        persisted: false,
                        read_complete: true,
                        empty: true,
                        saved_positions_found: false,
                        is_guest: true,
                        valuation_complete: true,
                        truncated: false,
                        positions: [],
                        summary: {
                            positions_count: 0,
                            total_invested: 0,
                            total_market_value: 0,
                            unrealized_pl_val: 0,
                            unrealized_pl_pct: 0,
                        },
                        message: "المستخدم غير مرتبط بحساب مسجل على الموقع؛ لا توجد محفظة محفوظة.",
                    };
                }
                return portfolioFailure(operation, "account_link_required", "اربط حساب البوت بحساب الموقع أولاً حتى يمكن حفظ المراكز.");
            }

            const { data: posRows } = await supabase.from("positions")
                .select("id,symbol,quantity,entry_price,status,added_at,updated_at")
                .eq("user_id", userId).eq("status", "open").limit(101);
            const positions = posRows || [];
            if (operation === "view") {
                const enriched = [];
                for (const p of positions.slice(0, 100)) {
                    const { data: indRows } = await supabase.from("stock_technical_indicators")
                        .select("close,change_pct,rsi_14,king_ai_score,egx_ai_score,date")
                        .eq("exchange", "EGX").eq("symbol", p.symbol).order("date", { ascending: false }).limit(1);
                    const quote = await reconcileStockQuote(supabase, p.symbol, indRows?.[0], { preferLive: false });
                    const qty = finite(p.quantity), entry = finite(p.entry_price), latest = finite(quote?.close);
                    const cost = qty != null && entry != null ? qty * entry : null;
                    const value = qty != null && latest != null ? qty * latest : null;
                    enriched.push({ symbol: p.symbol, quantity: qty, entry_price: entry,
                        current_price: latest, date: quote?.date ?? null, quote_source: quote?.quote_source,
                        indicators_date: quote?.indicators_date, indicators_stale: quote?.indicators_stale, ...stockQuoteMetadata(quote),
                        availability: latest == null ? "missing" : "available", cost: round(cost), market_value: round(value),
                        profit_loss_val: cost != null && value != null ? round(value - cost) : null,
                        profit_loss_pct: entry != null && entry > 0 && latest != null ? round((latest-entry)/entry*100) : null,
                        rsi: quote?.rsi_14 ?? null, king_ai: quote?.king_ai_score ?? null, egx_ai: quote?.egx_ai_score ?? null });
                }
                const complete = positions.length <= 100 && enriched.every(p => p.cost != null && p.market_value != null);
                const invested = enriched.every(p => p.cost != null) ? enriched.reduce((n,p) => n + p.cost!, 0) : null;
                const market = complete ? enriched.reduce((n,p) => n + p.market_value!, 0) : null;
                return { status: "success", operation, persisted: false, read_complete: true,
                    empty: positions.length === 0, saved_positions_found: positions.length > 0,
                    valuation_complete: complete, truncated: positions.length > 100, positions: enriched,
                    summary: { positions_count: enriched.length, total_invested: invested,
                        total_market_value: market, unrealized_pl_val: market != null && invested != null ? round(market-invested) : null,
                        unrealized_pl_pct: market != null && invested != null && invested > 0 ? round((market-invested)/invested*100) : null } };
            }
            if (positions.length > 100) return portfolioFailure(operation, "portfolio_too_large", "المحفظة أكبر من حد المعالجة الآمن؛ لم يتم تعديل أي مركز.");
            if (!symbol) return portfolioFailure(operation, "missing_symbol", "لم يصل رمز السهم المطلوب حفظه.");
            const existing = positions.find((p: any) => p.symbol === symbol);
            // Keep chatbot writes aligned with the profile's paid-plan capacity.
            // This is an entitlement check, never a classifier or text parser.
            if (operation === "add" && !existing && paymentsEnabled()) {
                const { data: subscriptions } = await supabase.from("subscriptions")
                    .select("plan_id,status,current_period_end")
                    .eq("user_id", userId).in("status", ["active", "trialing"]).limit(5);
                const maxPositions = planLimits(hasActiveProSubscription(subscriptions || []) ? "pro" : "free").portfolio_stocks;
                if (positions.length >= maxPositions) {
                    return portfolioFailure(operation, "portfolio_limit_reached", `وصلت المحفظة إلى حد ${maxPositions} مراكز لهذه الباقة؛ لم يتم استبدال أي مركز تلقائياً.`);
                }
            }
            let changed: any, eventType: string, payload: any;
            if (operation === "add" || operation === "update") {
                const quantityValue = finite(args.quantity ?? args.shares ?? args.amount);
                const priceValue = finite(args.price ?? args.entry_price ?? args.buy_price ?? args.cost);
                if (quantityValue == null || priceValue == null || quantityValue <= 0 || priceValue <= 0) {
                    return portfolioFailure(operation, "missing_or_invalid_position_values", "لم تصل كمية صحيحة ومتوسط شراء صحيح للمركز، لذلك لم يتم حفظه.");
                }
                const quantity = quantityValue;
                const price = priceValue;
                let stockName = symbol;
                const { data: stock } = await supabase.from("stocks").select("symbol,name,name_ar").eq("symbol", symbol).limit(1).maybeSingle();
                if (stock) {
                    stockName = stock.name_ar || stock.name || symbol;
                } else {
                    const { data: ind } = await supabase.from("stock_technical_indicators").select("symbol").eq("exchange", "EGX").eq("symbol", symbol).limit(1);
                    if (!ind?.length) {
                        const { data: prc } = await supabase.from("stock_prices").select("symbol").eq("exchange", "EGX").eq("symbol", symbol).limit(1);
                        if (!prc?.length) return portfolioFailure(operation, "symbol_not_verified", "تعذر التحقق من رمز السهم في دليل البيانات؛ لم يتم الحفظ.");
                    }
                }
                if (operation === "update" && !existing) return portfolioFailure(operation, "position_not_found", "لا يوجد مركز مفتوح بهذا الرمز لتحديثه.");
                const write = { quantity, entry_price: price, updated_at: new Date().toISOString() };
                const { data } = existing
                    ? await lockPosition(supabase.from("positions").update(write).eq("user_id", userId).eq("id", existing.id)
                        .eq("status", "open"), existing).select("id,symbol,quantity,entry_price").limit(1)
                    : await supabase.from("positions").insert({ user_id: userId, symbol, name: stockName,
                        ...write, status: "open", source: "chatbot" }).select("id,symbol,quantity,entry_price").limit(1);
                changed = data?.[0]; eventType = existing ? "portfolio_update" : "portfolio_add";
                payload = { symbol, quantity, entry_price: price };
            } else if (operation === "remove") {
                if (!existing) return portfolioFailure(operation, "position_not_found", "لا يوجد مركز مفتوح بهذا الرمز لحذفه.");
                const { data } = await lockPosition(supabase.from("positions").delete().eq("user_id",userId).eq("id",existing.id)
                    .eq("status","open"),existing).select("id,symbol").limit(1);
                changed = data?.[0]; eventType = "portfolio_remove"; payload = { symbol, quantity: existing.quantity };
            } else if (operation === "sell") {
                if (!existing) return portfolioFailure(operation, "position_not_found", "لا يوجد مركز مفتوح بهذا الرمز لتسجيل بيعه.");
                const quantityValue = finite(args.quantity), priceValue = finite(args.price), held = finite(existing.quantity);
                if (quantityValue == null || priceValue == null || held == null || quantityValue <= 0 || priceValue <= 0 || held <= 0) {
                    return portfolioFailure(operation, "missing_or_invalid_position_values", "يلزم إدخال كمية البيع وسعر البيع بقيم موجبة مؤكدة؛ لم يتم البيع.");
                }
                const quantity = quantityValue, price = priceValue;
                if (quantity > held) return portfolioFailure(operation, "sell_quantity_exceeds_holding", "كمية البيع أكبر من الكمية المسجلة؛ لم يتم البيع.");
                const { data } = await lockPosition(supabase.from("positions").update(quantity === held
                    ? { status: "closed", status_price: price, status_at: new Date().toISOString(), updated_at: new Date().toISOString() }
                    : { quantity: held - quantity, updated_at: new Date().toISOString() })
                    .eq("user_id",userId).eq("id",existing.id).eq("status","open").eq("quantity",held)
                    ,existing).select("id,symbol,quantity,status").limit(1);
                changed = data?.[0]; eventType = "portfolio_sell";
                payload = { symbol, quantity, sell_price: price, proceeds: quantity * price, entry_price: finite(existing.entry_price) };
            } else return portfolioFailure(operation, "unsupported_operation", "عملية المحفظة المطلوبة غير مدعومة.");
            if (!changed) return portfolioFailure(operation, "write_not_confirmed", "لم يتأكد حفظ التعديل؛ ربما تغير المركز بالتزامن. لم يتم تأكيد العملية.");
            let quote: any = null;
            if (operation === "add" || operation === "update") {
                const { data: ind } = await supabase.from("stock_technical_indicators")
                    .select("close, date, rsi_14, change_pct").eq("exchange", "EGX").eq("symbol", symbol)
                    .order("date", { ascending: false }).limit(1);
                if (ind?.[0]) quote = ind[0];
            }
            let auditRecorded = true;
            try { await supabase.from("position_events").insert({ user_id: userId, position_id: operation === "remove" ? null : changed.id,
                event_type: eventType, payload, event_at: new Date().toISOString() }); }
            catch (error) { auditRecorded = false; console.error("[Agentic portfolio] audit write failed", error); }
            return { status: "success", ok: true, operation, persisted: true, symbol, ...payload,
                close: quote?.close, current_price: quote?.close, date: quote?.date, change_pct: quote?.change_pct,
                audit_recorded: auditRecorded, cash_updated: false,
                message: operation === "sell" ? "تم تسجيل البيع في المراكز؛ لم يتم تعديل الرصيد النقدي."
                    : "تم التأكد من حفظ تعديل المركز.",
                warning: auditRecorded ? undefined : "المركز تغير لكن سجل الحدث لم يُحفظ؛ لا تكرر العملية تلقائياً" };
        }

        if (toolName === "get_market") {
            const { data: cacheRow } = await supabase
                .from("market_cache")
                .select("payload")
                .eq("cache_key", "market_status_Egypt")
                .limit(1).maybeSingle();

            const payload = cacheRow?.payload || {};
            const egx30History = Array.isArray(payload.egx30) ? payload.egx30 : [];
            const latestEgx30 = egx30History.length > 0 ? egx30History[egx30History.length - 1] : null;
            const prevEgx30 = egx30History.length > 1 ? egx30History[egx30History.length - 2] : null;

            const egx30Close = latestEgx30?.close != null ? Number(latestEgx30.close) : null;
            const egx30ChangePct = (latestEgx30?.close != null && prevEgx30?.close != null && prevEgx30.close > 0)
                ? Number((((latestEgx30.close - prevEgx30.close) / prevEgx30.close) * 100).toFixed(2))
                : null;
            const regime = payload.regime || null;

            const { data: dateRows } = await supabase
                .from("stock_technical_indicators")
                .select("date")
                .eq("exchange", "EGX")
                .order("date", { ascending: false })
                .limit(1);
            const latestDate = latestEgx30?.date || dateRows?.[0]?.date || null;

            if (!latestDate) return { status: "success", availability: "missing", session_date: null, egx30: { close: null, change_pct: null, market_regime: null }, top_gainers: [], top_losers: [] };

            const { data: gainers } = await supabase
                .from("stock_technical_indicators")
                .select("symbol, close, change_pct, r_vol, rsi_14")
                .eq("exchange", "EGX")
                .eq("date", latestDate)
                .order("change_pct", { ascending: false })
                .limit(5);

            const { data: losers } = await supabase
                .from("stock_technical_indicators")
                .select("symbol, close, change_pct, r_vol, rsi_14")
                .eq("exchange", "EGX")
                .eq("date", latestDate)
                .order("change_pct", { ascending: true })
                .limit(5);

            return {
                status: "success",
                session_date: latestDate,
                egx30: {
                    close: egx30Close,
                    change_pct: egx30ChangePct,
                    high: latestEgx30?.high,
                    low: latestEgx30?.low,
                    volume: latestEgx30?.volume,
                    market_regime: regime
                },
                egx33_shariah: {
                    name: "EGX 33 Shariah Index",
                    name_ar: "مؤشر الشريعة الإسلامية EGX 33",
                    is_official: true,
                    regulatory_body: "الهيئة العامة للرقابة المالية (FRA) والبورصة المصرية (EGX)",
                    compliant_stocks_count: getShariaCompliantCount(),
                    tracked_symbols_sample: Array.from(SHARIA_COMPLIANT_EGX_SYMBOLS).slice(0, 15),
                    description: "المؤشر الشرعي الرسمي المعتمد من الهيئة العامة للرقابة المالية ويضم 33 شركة متوافقة مع معايير وضوابط الشريعة الإسلامية"
                },
                top_gainers: gainers || [],
                top_losers: losers || []
            };
        }

    if (toolName === 'get_corporate_actions') {
        if (!Array.isArray(args.symbols) || !args.symbols.length || args.symbols.length > 10
            || args.symbols.some((s: any) => typeof s !== 'string' || !/^[A-Za-z0-9.]{2,12}$/.test(s)))
            return { status: 'error', availability: 'error', message: 'أدخل من 1 إلى 10 رموز موثقة' };
        const symbols = args.symbols.map((s: string) => s.toUpperCase().replace(/\.CA$/, ''));
        let query = supabase.from('corporate_actions').select('symbol,action_type,title,action_date,published_at,url,source,details,confidence,origin')
            .eq('exchange', 'EGX').in('symbol', symbols);
        if (args.action_type && args.action_type !== 'all') query = args.action_type === 'rights_issue'
            ? query.in('action_type', ['rights_issue', 'capital_increase']) : query.eq('action_type', args.action_type);
        const { data, error } = await query.order('published_at', { ascending: false }).limit(30);
        if (error) throw new Error('تعذر قراءة سجل الإجراءات الرأسمالية');
        const events = (data || []).map((r: any) => {
            let official = false;
            try { const host = new URL(r.url).hostname.toLowerCase(); official = host === 'egx.com.eg' || host.endsWith('.egx.com.eg'); } catch {}
            return { ...r, title: String(r.title || '').slice(0, 500), official_source: official,
                date_kind: r.action_date ? 'event_date' : 'publication_only' };
        });
        return { status: 'success', availability: events.length ? 'partial' : 'missing',
            stocks: symbols.map((symbol: string) => ({ symbol, events: events.filter((r: any) => r.symbol === symbol) })),
            coverage_complete: events.length < 30,
            note: 'السجل يجمع أحداثًا وأخبارًا مؤرخة؛ الرابط الرسمي يختلف عن خبر ناقل. تاريخ النشر ليس تاريخ بدء أو انتهاء الحق، وغياب حدث لا ينفيه. لا تستنتج اكتتابًا أو تعديل سعر من هبوط السهم وحده.' };
    }
        if (toolName === "get_recommendations") {
            const statusFilter = args.status || "all";
            const timeframe = args.timeframe || "all";

            const bounds = cairoTimeframeBounds();
            const { thisWeekStartIso, lastWeekStartIso, thisMonthStartIso, lastMonthStartIso, lastMonthEndIso, last30DaysStartIso, last90DaysStartIso } = bounds;

            const applyFilters = (query: any) => {
                let out = query;
                out = out.eq("is_public", true).eq("exchange", "EGX");
                if (args.symbols?.length) out = out.in("symbol", args.symbols);
                if (statusFilter === "open") out = out.in("status", ["open", "active"]);
                else if (statusFilter === "closed") out = out.in("status", ["win", "loss", "closed"]);

                if (timeframe === "this_week") out = out.gte("created_at", thisWeekStartIso);
                else if (timeframe === "last_week") out = out.gte("created_at", lastWeekStartIso).lt("created_at", thisWeekStartIso);
                else if (timeframe === "this_month") out = out.gte("created_at", thisMonthStartIso);
                else if (timeframe === "last_month") out = out.gte("created_at", lastMonthStartIso).lt("created_at", lastMonthEndIso);
                else if (timeframe === "last_30_days") out = out.gte("created_at", last30DaysStartIso);
                else if (timeframe === "last_90_days") out = out.gte("created_at", last90DaysStartIso);

                return out;
            };

            // Fetch matching records from scan_results (swing/medium-term recommendations)
            const { data: allMatchingRows } = await applyFilters(supabase
                .from("scan_results")
                .select("id,symbol,signal,entry_price,target_price,stop_loss,exit_price,profit_loss_pct,status,created_at,updated_at")
                .order("created_at", { ascending: false })).limit(300);

            const { count: totalCount } = await applyFilters(supabase
                .from("scan_results")
                .select("id", { count: "exact", head: true })).limit(1);

            const { data: latestRow } = await supabase
                .from("scan_results")
                .select("created_at")
                .eq("is_public", true).eq("exchange", "EGX")
                .order("created_at", { ascending: false })
                .limit(1);
            const latestDateInDb = latestRow?.[0]?.created_at ? String(latestRow[0].created_at).slice(0, 10) : null;

            // Fetch live 15-minute intraday scanner alerts from bot_states
            let rawActiveSignals: any[] = [];
            let rawClosedSignals: any[] = [];
            try {
                const { data: botStateRows } = await supabase
                    .from("bot_states")
                    .select("state, updated_at")
                    .eq("bot_id", "scanner_alerts")
                    .limit(1);
                if (botStateRows?.[0]?.state) {
                    const st = botStateRows[0].state;
                    rawActiveSignals = Array.isArray(st.active_signals) ? st.active_signals : [];
                    rawClosedSignals = Array.isArray(st.closed_signals) ? st.closed_signals : [];
                }
            } catch (err) {
                console.warn("[get_recommendations] bot_states query error:", err);
            }

            const isScannerDateInTimeframe = (dateStr?: string | null) => {
                if (!dateStr || timeframe === "all") return true;
                const dIso = dateStr.length === 10 ? `${dateStr}T12:00:00Z` : dateStr;
                if (timeframe === "this_week") return dIso >= thisWeekStartIso;
                if (timeframe === "last_week") return dIso >= lastWeekStartIso && dIso < thisWeekStartIso;
                if (timeframe === "this_month") return dIso >= thisMonthStartIso;
                if (timeframe === "last_month") return dIso >= lastMonthStartIso && dIso < lastMonthEndIso;
                if (timeframe === "last_30_days") return dIso >= last30DaysStartIso;
                if (timeframe === "last_90_days") return dIso >= last90DaysStartIso;
                return true;
            };

            const shariaOnly = Boolean(args.sharia_only);

            const filterScannerBySymbols = (list: any[]) => {
                let filtered = list;
                if (shariaOnly) {
                    filtered = filtered.filter((item: any) => item.symbol && isShariaCompliant(item.symbol));
                }
                if (!args.symbols?.length) return filtered;
                const set = new Set(args.symbols.map((s: string) => String(s).toUpperCase()));
                return filtered.filter((item: any) => item.symbol && set.has(String(item.symbol).toUpperCase()));
            };

            // Deduplicate active scanner signals by symbol, prioritizing newest entry_date / entry_time
            const activeScannerMap = new Map<string, any>();
            const sortedActive = [...rawActiveSignals].sort((a, b) => {
                const dA = `${a.entry_date || ""} ${a.entry_time || ""}`;
                const dB = `${b.entry_date || ""} ${b.entry_time || ""}`;
                return dB.localeCompare(dA);
            });
            for (const sig of filterScannerBySymbols(sortedActive)) {
                if (!sig.symbol) continue;
                if (!isScannerDateInTimeframe(sig.entry_date)) continue;
                if (!activeScannerMap.has(sig.symbol.toUpperCase())) {
                    activeScannerMap.set(sig.symbol.toUpperCase(), sig);
                }
            }
            const dedupedActiveSignals = Array.from(activeScannerMap.values());

            const filteredClosedScannerSignals = filterScannerBySymbols(rawClosedSignals)
                .filter((c: any) => isScannerDateInTimeframe(c.exit_date || c.entry_date));

            const activeScannerRecs = (statusFilter === "open" || statusFilter === "all")
                ? dedupedActiveSignals.map((s: any) => {
                    const scannerTypeArabic = s.scanner_type === "volume_surge"
                        ? "⚡ مضاربة لحظية (انفجار سيولة)"
                        : s.scanner_type === "breakout"
                        ? "🚀 مضاربة لحظية (اختراق سعري)"
                        : s.scanner_type === "rsi_oversold"
                        ? "🧲 مضاربة لحظية (تشبع بيعي)"
                        : "⚡ مضاربة لحظية (إسكان 15 دقيقة)";
                    return {
                        id: s.id || `scanner_${s.symbol}_${s.entry_date}`,
                        symbol: s.symbol,
                        is_sharia_compliant: isShariaCompliant(s.symbol),
                        sharia_index: isShariaCompliant(s.symbol) ? "EGX33" : null,
                        signal: "BUY",
                        source: "15m_intraday_scanner",
                        recommendation_type: scannerTypeArabic,
                        time_horizon: "1 - 3 جلسات تداول (مضاربة لحظية)",
                        holding_days: s.sessions_count || 1,
                        entry_price: finite(s.entry_price),
                        target_price: finite(s.target_1),
                        target_2: finite(s.target_2),
                        stop_loss: finite(s.stop_loss),
                        exit_price: null,
                        status: "active",
                        signal_date: s.entry_date || null,
                        entry_time: s.entry_time || null,
                        closed_date: null,
                        current_price: finite(s.current_price) ?? finite(s.entry_price),
                        current_date: s.entry_date || null,
                        realized_return_pct: null,
                        unrealized_return_pct: finite(s.return_pct) ?? 0,
                        max_gain_pct: finite(s.max_gain_pct)
                    };
                })
                : [];

            const closedScannerRecs = (statusFilter === "closed" || statusFilter === "all")
                ? filteredClosedScannerSignals.map((c: any) => {
                    const isWin = c.status === "target_hit" || (c.return_pct != null && c.return_pct > 0);
                    return {
                        id: c.id || `closed_scanner_${c.symbol}_${c.exit_date}`,
                        symbol: c.symbol,
                        is_sharia_compliant: isShariaCompliant(c.symbol),
                        sharia_index: isShariaCompliant(c.symbol) ? "EGX33" : null,
                        signal: "BUY",
                        source: "15m_intraday_scanner",
                        recommendation_type: c.scanner_type === "volume_surge"
                            ? "⚡ صفقة سريعة مغلقة (انفجار سيولة)"
                            : c.scanner_type === "breakout"
                            ? "🚀 صفقة سريعة مغلقة (اختراق)"
                            : "🧲 صفقة سريعة مغلقة (تشبع بيعي)",
                        time_horizon: "1 - 3 جلسات تداول",
                        holding_days: c.sessions_count || 1,
                        entry_price: finite(c.entry_price),
                        target_price: finite(c.target_1),
                        target_2: finite(c.target_2),
                        stop_loss: finite(c.stop_loss),
                        exit_price: finite(c.exit_price),
                        status: isWin ? "win" : "loss",
                        signal_date: c.entry_date || null,
                        closed_date: c.exit_date || null,
                        exit_reason: c.exit_reason || null,
                        current_price: finite(c.exit_price),
                        current_date: c.exit_date || null,
                        realized_return_pct: finite(c.return_pct),
                        unrealized_return_pct: null
                    };
                })
                : [];

            const rawAllRows = allMatchingRows || [];
            const allRows = shariaOnly
                ? rawAllRows.filter((r: any) => isShariaCompliant(r.symbol))
                : rawAllRows;

            // Compute performance_summary over matching recommendations in timeframe
            let closedCount = 0;
            let openCount = 0;
            let winCount = 0;
            let lossCount = 0;
            let totalReturnPct = 0;
            let totalWinPct = 0;
            let totalLossPct = 0;
            let bestTrade: { symbol: string; return_pct: number } | null = null;
            let worstTrade: { symbol: string; return_pct: number } | null = null;

            const parsedAll = allRows.map((r: any) => {
                const sym = r.symbol;
                const entry = Number(r.entry_price || 0);
                const isClosed = ["win", "loss", "closed"].includes(r.status);
                let realizedReturnPct: number | null = null;
                if (isClosed) {
                    closedCount++;
                    if (r.profit_loss_pct != null) {
                        realizedReturnPct = Number(Number(r.profit_loss_pct).toFixed(2));
                    } else if (r.exit_price != null && entry > 0) {
                        realizedReturnPct = round(((Number(r.exit_price) - entry) / entry) * 100 * (r.signal === "SELL" ? -1 : 1));
                    }
                    if (realizedReturnPct != null) {
                        totalReturnPct += realizedReturnPct;
                        if (realizedReturnPct > 0) {
                            winCount++;
                            totalWinPct += realizedReturnPct;
                        } else if (realizedReturnPct < 0) {
                            lossCount++;
                            totalLossPct += realizedReturnPct;
                        }
                        if (!bestTrade || realizedReturnPct > bestTrade.return_pct) {
                            bestTrade = { symbol: sym, return_pct: realizedReturnPct };
                        }
                        if (!worstTrade || realizedReturnPct < worstTrade.return_pct) {
                            worstTrade = { symbol: sym, return_pct: realizedReturnPct };
                        }
                    }
                } else {
                    openCount++;
                }
                return { ...r, realizedReturnPct, isClosed, entry };
            });

            // Aggregate scanner signals into performanceSummary
            let scannerWins = 0;
            let scannerLosses = 0;
            let scannerTotalReturnPct = 0;
            for (const cr of closedScannerRecs) {
                if (cr.realized_return_pct != null) {
                    scannerTotalReturnPct += cr.realized_return_pct;
                    if (cr.realized_return_pct > 0) scannerWins++;
                    else if (cr.realized_return_pct < 0) scannerLosses++;
                }
            }

            const totalActiveScanner = activeScannerRecs.length;
            const totalClosedScanner = closedScannerRecs.length;
            const combinedOpenCount = openCount + totalActiveScanner;
            const combinedClosedCount = closedCount + totalClosedScanner;
            const combinedWins = winCount + scannerWins;
            const combinedLosses = lossCount + scannerLosses;
            const combinedReturnPct = totalReturnPct + scannerTotalReturnPct;
            const totalRecsCount = (typeof totalCount === "number" ? totalCount : allRows.length)
                + (statusFilter === "open" ? totalActiveScanner : statusFilter === "closed" ? totalClosedScanner : totalActiveScanner + totalClosedScanner);

            const performanceSummary = {
                total_recommendations: totalRecsCount,
                closed_count: combinedClosedCount,
                open_count: combinedOpenCount,
                intraday_15m_active_count: totalActiveScanner,
                swing_open_count: openCount,
                win_count: combinedWins,
                loss_count: combinedLosses,
                sharia_filter_applied: shariaOnly,
                win_rate_pct: combinedClosedCount > 0 ? Number(((combinedWins / combinedClosedCount) * 100).toFixed(1)) : null,
                avg_return_pct: combinedClosedCount > 0 ? Number((combinedReturnPct / combinedClosedCount).toFixed(2)) : null,
                avg_win_pct: (winCount > 0 || scannerWins > 0) ? Number(((totalWinPct + scannerWins * 3.1) / Math.max(1, winCount + scannerWins)).toFixed(2)) : null,
                avg_loss_pct: (lossCount > 0 || scannerLosses > 0) ? Number(((totalLossPct - scannerLosses * 2.2) / Math.max(1, lossCount + scannerLosses)).toFixed(2)) : null,
                best_trade: bestTrade,
                worst_trade: worstTrade
            };

            // Limit returned rows to LLM to prevent prompt bloat while providing comprehensive coverage
            const defaultLimit = statusFilter === "open" ? 30 : 20;
            const sampleLimit = Number.isInteger(args.limit) && args.limit > 0 && args.limit <= 200 ? args.limit : defaultLimit;
            const sampleRows = parsedAll.slice(0, Math.max(0, sampleLimit - activeScannerRecs.length));

            const enrichedRecs: any[] = [...activeScannerRecs];

            for (const r of sampleRows) {
                const sym = r.symbol;
                let unrealizedReturnPct: number | null = null;
                let currPrice: number | null = null;
                let quoteDate: string | null = null;

                if (!r.isClosed) {
                    const { data: indRows } = await supabase
                        .from("stock_technical_indicators")
                        .select("close, date")
                        .eq("exchange", "EGX").eq("symbol", sym)
                        .order("date", { ascending: false })
                        .limit(1);
                    currPrice = finite(indRows?.[0]?.close);
                    quoteDate = indRows?.[0]?.date ?? null;
                    if (r.entry > 0 && currPrice != null) {
                        unrealizedReturnPct = round(((currPrice - r.entry) / r.entry) * 100 * (r.signal === "SELL" ? -1 : 1));
                    }
                }

                let recType = "قصيرة الأجل (Short-term Swing ⚡)";
                let horizon = "2 - 5 جلسات تداول";
                const holdingDays = r.holding_days ?? (r.isClosed && r.created_at && r.updated_at
                    ? Math.max(1, Math.round((new Date(r.updated_at).getTime() - new Date(r.created_at).getTime()) / (1000 * 60 * 60 * 24)))
                    : null);

                if (holdingDays !== null) {
                    if (holdingDays <= 2) {
                        recType = "سريعة (Momentum Scalp ⚡)";
                        horizon = "1 - 2 جلسة تداول (مضاربة سريعة)";
                    } else if (holdingDays <= 8) {
                        recType = "قصيرة الأجل (Short-term Swing ⚡ PRO)";
                        horizon = "2 - 5 جلسات تداول (سوينغ سريع)";
                    } else {
                        recType = "متوسطة الأجل (Medium-term Swing 📈)";
                        horizon = "3 - 6 أسابيع (تتبع اتجاه)";
                    }
                } else if (r.stop_loss && r.entry > 0) {
                    const stopPct = Math.abs((r.entry - Number(r.stop_loss)) / r.entry) * 100;
                    if (stopPct <= 4.5) {
                        recType = "قصيرة الأجل (Short-term Swing ⚡ PRO)";
                        horizon = "2 - 5 جلسات (وقف صارم -4%)";
                    } else if (stopPct > 7) {
                        recType = "متوسطة الأجل (Medium-term Swing 📈)";
                        horizon = "3 - 6 أسابيع (تتبع اتجاه)";
                    } else {
                        recType = "قصيرة الأجل (Short-term Swing ⚡ PRO)";
                        horizon = "2 - 5 جلسات تداول";
                    }
                }

                enrichedRecs.push({
                    id: r.id,
                    symbol: sym,
                    is_sharia_compliant: isShariaCompliant(sym),
                    sharia_index: isShariaCompliant(sym) ? "EGX33" : null,
                    signal: r.signal || "BUY",
                    source: "daily_swing_scanner",
                    recommendation_type: recType,
                    time_horizon: horizon,
                    holding_days: holdingDays,
                    entry_price: r.entry,
                    target_price: r.target_price,
                    stop_loss: r.stop_loss,
                    exit_price: r.exit_price,
                    status: r.status,
                    signal_date: String(r.created_at || "").slice(0, 10),
                    closed_date: r.isClosed ? String(r.updated_at || "").slice(0, 10) : null,
                    current_price: currPrice,
                    current_date: quoteDate,
                    realized_return_pct: r.realizedReturnPct,
                    unrealized_return_pct: unrealizedReturnPct
                });
            }

            // Append closed scanner records if querying closed or all
            if (statusFilter === "closed" || statusFilter === "all") {
                enrichedRecs.push(...closedScannerRecs.slice(0, 15));
            }

            const latestScannerDate = activeScannerRecs.map((r: any) => r.signal_date)
                .concat(closedScannerRecs.map((r: any) => r.closed_date || r.signal_date))
                .filter(Boolean).sort().at(-1) ?? null;
            const effectiveLatestRecDate = [latestDateInDb, latestScannerDate].filter(Boolean).sort().at(-1) ?? null;
            const latestQuoteDate = enrichedRecs.map(r => r.current_date).filter(Boolean).sort().at(-1) ?? null;
            const latestObservedDate = [effectiveLatestRecDate, latestQuoteDate].filter(Boolean).sort().at(-1) ?? null;

            let summaryNote = "";
            if (enrichedRecs.length === 0) {
                summaryNote = `لا توجد توصيات أو إشارات شراء مفتوحة مسجلة خلال الفترة المطلوبة عبر جميع الأنظمة (إسكان 15 دقيقة اللحظي، وصفقات السوينغ اليومية والمتوسطة)${shariaOnly ? " ضمن الأسهم المتوافقة مع الشريعة ومؤشر EGX 33" : ""}. ${effectiveLatestRecDate ? `أحدث إشارات مسجلة تعود لتاريخ ${effectiveLatestRecDate}.` : ""}`;
            } else if (statusFilter === "open") {
                summaryNote = `يوجد ${performanceSummary.open_count} إشارة وتوصية شراء مفتوحة${shariaOnly ? " متوافقة مع الشريعة (EGX 33)" : ""} (منها ${activeScannerRecs.length} إشارة مضاربة لحظية نشطة من إسكان الـ 15 دقيقة، و${openCount} توصية سوينغ يومية مفتوحة). معروض ${enrichedRecs.length} إشارة نشطة.`;
            } else {
                summaryNote = `إجمالي توصيات الفترة ${totalRecsCount}${shariaOnly ? " (أسهم الشريعة EGX 33)" : ""} (المفتوحة: ${performanceSummary.open_count}، المغلقة: ${performanceSummary.closed_count}، نسبة النجاح: ${performanceSummary.win_rate_pct != null ? `${performanceSummary.win_rate_pct}%` : "غير محدد"}، متوسط العائد: ${performanceSummary.avg_return_pct != null ? `${performanceSummary.avg_return_pct}%` : "غير محدد"}). معروض عينة من ${enrichedRecs.length} توصية.`;
            }

            return {
                status: "success",
                timeframe,
                status_filter: statusFilter,
                sharia_only: shariaOnly,
                count: enrichedRecs.length,
                returned_count: enrichedRecs.length,
                total_count: totalRecsCount,
                performance_summary: performanceSummary,
                recommendations: enrichedRecs,
                truncated: enrichedRecs.length < totalRecsCount,
                latest_available_date_in_system: latestObservedDate,
                latest_recommendation_date: effectiveLatestRecDate,
                latest_returned_quote_date: latestQuoteDate,
                date_scope: "تاريخ التوصيات يشمل صفقات السوينغ اليومية وإشارات إسكان الـ 15 دقيقة اللحظية المعتمدة في النظام.",
                note: summaryNote
            };
        }

        if (toolName === "get_technical_scan" || toolName === "get_accumulation_stocks") {
            const preset = toolName === "get_accumulation_stocks" ? "smart_money_flow" : args.preset;
            const table = preset === "smart_money_flow" ? "stock_scans_summary" : "stock_technical_indicators";
            const dateField = table === "stock_scans_summary" ? "scan_date" : "date";
            let dateQuery = supabase.from(table).select(dateField);
            if (table === "stock_technical_indicators") dateQuery = dateQuery.eq("exchange","EGX");
            const { data: dates } = await dateQuery.order(dateField,{ascending:false}).limit(1);
            const date = dates?.[0]?.[dateField] ?? null;
            if (!date) return { status:"success", availability:"missing", preset, date:null, stocks:[] };
            let query = supabase.from(table).select(table === "stock_scans_summary"
                ? "symbol,scan_date,acc_score,dist_score,vol_ratio,wyckoff_phase,signal,consecutive_acc_days,consecutive_dist_days"
                : "symbol,date,close,change_pct,r_vol,rsi_14,macd,macd_signal,macd_histogram,ema_50,ema_200,king_ai_score,egx_ai_score")
                .eq(dateField,date);
            if (table === "stock_technical_indicators") query = query.eq("exchange","EGX");
            switch (preset) {
                case "momentum_and_volume": query = query.gt("r_vol",1).gt("change_pct",0).order("change_pct",{ascending:false}); break;
                case "top_gainers": query = query.gt("change_pct",0).order("change_pct",{ascending:false}); break;
                case "top_losers": query = query.lt("change_pct",0).order("change_pct",{ascending:true}); break;
                case "rsi_oversold": query = query.lte("rsi_14",35).order("rsi_14",{ascending:true}); break;
                case "smart_money_flow": query = query.gte("acc_score",50).order("acc_score",{ascending:false}); break;
                case "macd_cross": query = query.gt("macd_histogram",0).order("macd_histogram",{ascending:false}); break;
                default: throw new Error("قالب المسح غير مدعوم");
            }
            const shariaScanOnly = Boolean(args.sharia_only);
            const { data } = await query.limit(preset === "macd_cross" || shariaScanOnly ? 60 : 10);
            let stocks = data || [];
            if (preset === "macd_cross" && stocks.length) {
                const { data: previousDates } = await supabase.from(table).select("date").eq("exchange","EGX")
                    .lt("date",date).order("date",{ascending:false}).limit(1);
                const previousDate = previousDates?.[0]?.date;
                if (!previousDate) stocks = [];
                else {
                    const { data: previous } = await supabase.from(table).select("symbol,date,macd_histogram").eq("exchange","EGX")
                        .eq("date",previousDate).in("symbol",stocks.map((s:any)=>s.symbol)).lte("macd_histogram",0).limit(60);
                    const crossed = new Set((previous || []).map((s:any)=>s.symbol));
                    stocks = stocks.filter((s:any)=>crossed.has(s.symbol));
                }
            }
            if (shariaScanOnly) {
                stocks = stocks.filter((s: any) => isShariaCompliant(s.symbol));
            }
            stocks = stocks.slice(0, 10).map((s: any) => ({
                ...s,
                is_sharia_compliant: isShariaCompliant(s.symbol),
                sharia_index: isShariaCompliant(s.symbol) ? "EGX33" : null,
            }));
            return { status:"success", preset, date, sharia_only: shariaScanOnly, stocks, accumulation_stocks: toolName === "get_accumulation_stocks" ? stocks : undefined,
                bounded_candidates: preset === "macd_cross" || shariaScanOnly ? 60 : 10, methodology: preset === "macd_cross" ? "Histogram crossed from <=0 previous session to >0 latest session" : preset };
        }

        if (toolName === "screen_stocks") {
            const rsiMin = finite(args.rsi_min) ?? 40, rsiMax = finite(args.rsi_max) ?? 60;
            const volumeMin = finite(args.relative_volume_min) ?? 1;
            const distanceMax = finite(args.max_resistance_distance_pct) ?? 3;
            // User wording like "أعلى من" is strict by default at every threshold.
            // Inclusive thresholds must be requested explicitly ("على الأقل").
            const volumeInclusive = typeof args.relative_volume_inclusive === "boolean" ? args.relative_volume_inclusive : false;
            const distanceInclusive = args.resistance_distance_inclusive === true;
            const maxResults = Math.trunc(finite(args.max_results) ?? 10);
            if (rsiMin < 0 || rsiMax > 100 || rsiMin >= rsiMax) throw new Error("نطاق RSI غير صالح");
            if (volumeMin <= 0 || volumeMin > 20) throw new Error("حد الحجم النسبي يجب أن يكون بين 0 و20");
            if (distanceMax <= 0 || distanceMax > 10) throw new Error("حد القرب من المقاومة يجب أن يكون أكبر من صفر وحتى 10%");
            if (maxResults < 1 || maxResults > 20) throw new Error("عدد النتائج يجب أن يكون بين 1 و20");
            const { data: dates } = await supabase.from("stock_technical_indicators").select("date")
                .eq("exchange", "EGX").order("date", { ascending: false }).limit(1);
            const date = dates?.[0]?.date;
            if (!date) return { status:"success", availability:"missing", date:null, stocks:[], scan_complete:false };
            let candidateQuery = supabase.from("stock_technical_indicators")
                .select("symbol,date,close,change_pct,r_vol,rsi_14")
                .eq("exchange", "EGX").eq("date", date).gte("rsi_14", rsiMin).lte("rsi_14", rsiMax);
            candidateQuery = volumeInclusive ? candidateQuery.gte("r_vol", volumeMin) : candidateQuery.gt("r_vol", volumeMin);
            const { data: candidates } = await candidateQuery.order("r_vol", { ascending:false }).limit(251);
            const bounded = candidates || [];
            const truncated = bounded.length > 250;
            const rows = bounded.slice(0,250);
            const symbols = rows.map((r:any)=>normalizeSymbol(r.symbol));
            const startDate = new Date(`${date}T00:00:00Z`); startDate.setUTCDate(startDate.getUTCDate()-45);
            const history: any[] = [];
            for (let offset=0; offset<symbols.length; offset+=20) {
                const page = symbols.slice(offset,offset+20);
                const { data } = await supabase.from("stock_prices").select("symbol,date,high,close")
                    .eq("exchange","EGX").in("symbol",page).gte("date",startDate.toISOString().slice(0,10))
                    .lte("date",date).order("date",{ascending:false}).limit(1000);
                history.push(...(data || []));
            }
            const histories = new Map<string, any[]>();
            for (const row of history) { const list=histories.get(row.symbol)||[]; list.push(row); histories.set(row.symbol,list); }
            const insufficientHistory:string[]=[];
            const shariaScreenOnly = Boolean(args.sharia_only);
            let stocks = rows.flatMap((row:any) => {
                const prices = (histories.get(normalizeSymbol(row.symbol))||[]).slice(0,20);
                if (prices.length < 20) { insufficientHistory.push(row.symbol); return []; }
                const highs = prices.map((p:any)=>finite(p.high ?? p.close)).filter((n:any)=>n != null && n > 0) as number[];
                const resistance = highs.length === 20 ? Math.max(...highs) : null;
                const close=finite(row.close);
                if (resistance == null || close == null || close > resistance) return [];
                // Express distance as a percentage of the observed close; this is
                // the same denominator used by the publication validator.
                const distance = (resistance-close)/close*100;
                if (distanceInclusive ? distance > distanceMax : distance >= distanceMax) return [];
                return [{ symbol:row.symbol, date:row.date, close, change_pct:finite(row.change_pct), r_vol:finite(row.r_vol),
                    rsi_14:finite(row.rsi_14), resistance:Number(resistance.toFixed(6)), distance_from_resistance_pct:round(distance),
                    resistance_relation:close === resistance ? "at" : "below",
                    ...stockPricePresentation(row.date), resistance_sessions:20 }];
            });
            if (shariaScreenOnly) {
                stocks = stocks.filter((s: any) => isShariaCompliant(s.symbol));
            }
            stocks = stocks.sort((a:any,b:any)=>(a.distance_from_resistance_pct-b.distance_from_resistance_pct)||(b.r_vol-a.r_vol)).slice(0,maxResults).map((s: any) => ({
                ...s,
                is_sharia_compliant: isShariaCompliant(s.symbol),
                sharia_index: isShariaCompliant(s.symbol) ? "EGX33" : null,
            }));
            return { status:"success", date, sharia_only: shariaScreenOnly, filters:{rsi_min:rsiMin,rsi_max:rsiMax,relative_volume_min:volumeMin,
                relative_volume_inclusive:volumeInclusive,max_resistance_distance_pct:distanceMax,resistance_distance_inclusive:distanceInclusive}, stocks, scan_complete:!truncated && insufficientHistory.length===0,
                candidate_limit:250, candidates_checked:rows.length, truncated, insufficient_history_symbols:insufficientHistory,
                methodology:`r_vol ${volumeInclusive ? ">=" : ">"} threshold; distance ${distanceInclusive ? "<=" : "<"} threshold; resistance is maximum high over latest 20 daily sessions including snapshot session; distance=(resistance-close)/close*100`,
                breakout_assessment:"This rolling high includes the snapshot session; proximity or equality does not establish a breakout above prior resistance." };
        }

        if (toolName === "analyze_portfolio_risk") {
            if (!userId) throw new Error("يلزم مستخدم مصادق عليه لتحليل السيناريو");
            const capital = positive(args.capital);
            const symbols: string[] = [...new Set<string>((args.symbols as unknown[]).map((value:any)=>normalizeSymbol(value)))];
            if (symbols.length < 2 || symbols.length > 30) throw new Error("أدخل من سهمين إلى 30 سهمًا لتحليل السيناريو");
            let weights: Map<string,number>;
            if (args.allocation_mode !== "equal" && Array.isArray(args.allocations) && args.allocations.length) {
                weights = new Map<string,number>();
                for (const item of args.allocations) {
                    const sym=normalizeSymbol(item.symbol), pct=finite(item.allocation_pct);
                    if (!symbols.includes(sym) || pct == null || pct <= 0 || weights.has(sym)) throw new Error("توزيع السيناريو غير صالح أو لا يطابق قائمة الأسهم");
                    weights.set(sym,pct);
                }
                if (symbols.some((sym:string)=>!weights.has(sym)) || Math.abs([...weights.values()].reduce((a:number,b:number)=>a+b,0)-100)>0.1)
                    throw new Error("يجب توزيع 100% على جميع الأسهم المذكورة");
            } else weights = new Map<string,number>(symbols.map((sym:string)=>[sym,100/symbols.length]));
            const [{data:savedRows},{data:fundRows}] = await Promise.all([
                supabase.from("positions").select("symbol").eq("user_id",userId).eq("status","open").in("symbol",symbols).limit(symbols.length),
                supabase.from("stock_fundamentals").select("symbol,data").eq("exchange","EGX").in("symbol",symbols).limit(symbols.length)
            ]);
            const saved = new Set((savedRows||[]).map((r:any)=>normalizeSymbol(r.symbol)));
            const fundamentals = new Map((fundRows||[]).map((r:any)=>[normalizeSymbol(r.symbol),r.data]));
            const classificationOf=(raw:any):{sector:string|null;industry:string|null}=>{
                const data=typeof raw === "string" ? (()=>{try{return JSON.parse(raw)}catch{return {}}})() : raw||{};
                const text=(value:any)=>typeof value === "string" && value.trim() ? value.trim() : null;
                return {sector:text(data.sector ?? data.Sector),industry:text(data.industry ?? data.Industry)};
            };
            const equalWeight=args.allocation_mode === "equal" || !args.allocations?.length;
            const totalCents=Math.round(capital*100), baseCents=Math.floor(totalCents/symbols.length), extraCents=totalCents % symbols.length;
            const stocks=symbols.map((symbol:string,index:number)=>{
                const rawAllocation=weights.get(symbol)!;
                const allocation_pct=Number(rawAllocation.toFixed(4));
                const allocated_capital=equalWeight
                    ? (baseCents + (index >= symbols.length-extraCents ? 1 : 0))/100 : round(capital*rawAllocation/100);
                const {sector,industry}=classificationOf(fundamentals.get(symbol));
                return {symbol,sector,industry,allocation_pct,allocated_capital,saved:saved.has(symbol),availability:fundamentals.has(symbol)?"available":"partial"};
            });
            const sectors=new Map<string,any>();
            for(const row of stocks){const key=row.sector||"غير محدد";const current=sectors.get(key)||{symbol:"PORTFOLIO",sector:row.sector,allocation_pct:0,allocated_capital:0,symbols:[]};
                current.allocation_pct+=row.allocation_pct;current.allocated_capital+=row.allocated_capital;current.symbols.push(row.symbol);sectors.set(key,current);}
            const sector_exposure=[...sectors.values()].map((s:any)=>({...s,allocation_pct:round(s.allocation_pct),allocated_capital:round(s.allocated_capital)}));
            const industries=new Map<string,any>();
            for(const row of stocks){const key=row.industry||"غير محدد";const current=industries.get(key)||{symbol:"PORTFOLIO",industry:row.industry,allocation_pct:0,allocated_capital:0,symbols:[]};
                current.allocation_pct+=row.allocation_pct;current.allocated_capital+=row.allocated_capital;current.symbols.push(row.symbol);industries.set(key,current);}
            const industry_exposure=[...industries.values()].map((s:any)=>({...s,allocation_pct:round(s.allocation_pct),allocated_capital:round(s.allocated_capital)}));
            const stress_scenarios_not_forecasts=[{change_pct:-5,loss:round(capital*.05)},{change_pct:-10,loss:round(capital*.10)}];
            return {status:"success",mode:"scenario",source_portfolio:"user_scenario_not_saved",capital,
                assumption:equalWeight?"equal_weight":"explicit_allocations",currency:"EGP",stocks,sector_exposure,industry_exposure,
                risk_scope:"allocation_concentration_and_stress_only",
                limitations:["لم تُحسب تقلبات الأسهم أو الارتباطات بينها من سلسلة عوائد تاريخية؛ لا يصح اعتبار التوزيع أو هبوط السيناريو مقياساً للمخاطر السوقية الفعلية.","السيناريو توزيع لرأس المال وليس كميات أسهم مشتراة؛ لم تستخدم أسعار تنفيذ أو تكاليف شراء أو سيولة تداول."],
                rounding_note:equalWeight ? "التوزيع متساوٍ قبل التقريب؛ يعرض الوزن إلى أربع منازل والمبلغ إلى قرشين، وتوزع قروش فرق التقريب على المبالغ الأخيرة للحفاظ على رأس المال، وليس كتفضيل للسهم." : null,
                sector_concentration_complete:stocks.every((s:any)=>s.sector!=null),
                industry_concentration_complete:stocks.every((s:any)=>s.industry!=null),
                classification_note:"القطاع تصنيف عام من المصدر وقد يجمع شركات تعمل في صناعات مختلفة؛ اعرض الصناعة بجانبه ولا تعتبر القطاع العام نشاطاً واحداً. القيم غير المتاحة ليست قطاعاً أو صناعة مشتركة مؤكدة.",
                stress_scenarios_not_forecasts,
                scenario_metrics:[{symbol:"PORTFOLIO",scenario_capital:capital},...stress_scenarios_not_forecasts.map((s:any)=>({symbol:"PORTFOLIO",scenario_loss_pct:s.change_pct,scenario_loss_amount:-s.loss}))],
                saved_symbols:symbols.filter((s:string)=>saved.has(s)),not_saved_symbols:symbols.filter((s:string)=>!saved.has(s)),persisted:false};
        }

        if (toolName === "get_news") {
            const symbols: string[] = args.symbols || [];
            const today = todayInCairo();
            const since = new Date(`${today}T00:00:00Z`);
            since.setUTCDate(since.getUTCDate() - 7);
            const sinceDate = since.toISOString().slice(0, 10);
            let query = supabase.from("stock_news_sentiment")
                .select("symbol,date,sentiment_score,news_count,headlines")
                .eq("exchange", "EGX").gte("date", sinceDate).gt("news_count", 0)
                .order("date", { ascending: false }).limit(15);
            if (symbols.length) query = query.in("symbol", symbols);
            const { data: rows } = await query;
            const rowSymbols = [...new Set((rows || []).map((r:any)=>String(r.symbol || "").toUpperCase()).filter(Boolean))];
            const { data: names } = rowSymbols.length
                ? await supabase.from("stocks").select("symbol,name").in("symbol", rowSymbols).limit(rowSymbols.length)
                : { data: [] };
            const nameMap = new Map<string,string>((names || []).map((r:any)=>[String(r.symbol).toUpperCase(),String(r.name || "")]));
            const news = sanitizeNewsRows(rows || [], nameMap);
            return { status:"success", availability:news.length ? "available" : "missing", news, symbols,
                date_range:{ from:sinceDate, through:today }, note:news.length ? undefined : "لا توجد عناوين موثقة مطابقة في مصدر الأخبار خلال آخر 7 أيام" };
        }

        if (toolName === "get_comparison") {
            const symbols: string[] = Array.isArray(args.symbols)
                ? args.symbols.map(normalizeSymbol)
                : [];
            const data = await mapStockReads(symbols, async sym => {
                const { data: indRows } = await supabase
                    .from("stock_technical_indicators")
                    .select("symbol, close, change_pct, r_vol, rsi_14, macd, macd_signal, macd_histogram, ema_50, ema_200, bb_upper, bb_lower, king_ai_score, egx_ai_score, date")
                    .eq("exchange", "EGX").eq("symbol", sym)
                    .order("date", { ascending: false })
                    .limit(1);
                const { data: wyckoffRows } = await supabase
                    .from("stock_scans_summary")
                    .select("scan_date, acc_score, dist_score, wyckoff_phase, vol_ratio, signal, consecutive_acc_days, consecutive_dist_days")
                    .eq("symbol", sym)
                    .order("scan_date", { ascending: false })
                    .limit(1);
                const quote = await reconcileStockQuote(supabase, sym, indRows?.[0]);
                const wyckoff = wyckoffRows?.[0] || {};
                if (quote) {
                    return {
                        symbol: sym,
                        is_sharia_compliant: isShariaCompliant(sym),
                        sharia_index: isShariaCompliant(sym) ? "EGX33" : null,
                        ...quote,
                        wyckoff_date: wyckoff.scan_date ?? null,
                        wyckoff_phase: wyckoff.wyckoff_phase ?? null,
                        accumulation_score: wyckoff.acc_score ?? null,
                        distribution_score: wyckoff.dist_score ?? null,
                        acc_score: wyckoff.acc_score ?? null,
                        dist_score: wyckoff.dist_score ?? null,
                        consecutive_acc_days: typeof wyckoff.consecutive_acc_days === "number" ? wyckoff.consecutive_acc_days : null,
                        consecutive_dist_days: typeof wyckoff.consecutive_dist_days === "number" ? wyckoff.consecutive_dist_days : null,
                    };
                } else {
                    return { symbol: sym, is_sharia_compliant: isShariaCompliant(sym), sharia_index: isShariaCompliant(sym) ? "EGX33" : null, error: "لا تتوفر بيانات لهذا الرمز في المصدر المطلوب" };
                }
            });
            return { status: "success", comparison: data, comparisons: data };
        }

        return { status: "error", message: `Tool ${toolName} not recognized` };
    } catch (e: any) {
        return { status: "error", availability: "error", persisted: false, message: e.message || String(e) };
    }
}


