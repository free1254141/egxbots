import { renderPlannedReadEvidence } from "./planned-read-tools";
import { normalizeEvidenceNumbers } from "./numeric-evidence";
import { BACKTEST_METRICS, renderBacktestEvidence } from "./backtest-evidence";
import { checkAttribution } from "./answer-gate";
import { stockPricePresentation } from "./stock-quote";
import { buildFactRecords, FactRecord } from "./facts";
import { ToolResult } from "./types";
import { newsEventDate } from "./news-evidence";
import { renderStockRecovery } from "./stock-recovery";

export interface AgenticEvidence {
    tool: string;
    arguments: Record<string, any>;
    data: any;
    source: string;
    data_time: string | null;
    symbols: string[];
    availability: "available" | "missing" | "partial" | "error";
    data_type: "historical" | "image-derived" | "provider-snapshot";
    captured_at?: string;
}

const memoryTools = new Set(["get_stock", "get_stock_levels", "get_market", "get_technical_scan", "get_accumulation_stocks", "get_comparison", "get_news", "get_recommendations"]);
memoryTools.add("apply_chart_strategy"); memoryTools.add("compare_strategies_history");
memoryTools.add("get_fundamentals"); memoryTools.add("get_sector_peers"); memoryTools.add("get_market_breadth");
memoryTools.add("screen_stocks"); memoryTools.add("analyze_portfolio_risk");
/** Remove duplicate aliases/payload text, without removing source, dates, identity or unknown values. */
export function compactEvidence(record: AgenticEvidence): AgenticEvidence {
    const data = { ...record.data };
    if (record.tool === "get_news" && Array.isArray(data.news)) {
        data.news = data.news.map((row: any) => ({ ...row, date_kind: "aggregation", record_date: row.record_date || row.date || null,
            event_date: newsEventDate({ ...row, date_kind: "aggregation" }) }));
        const publishedDates = [...new Set<string>(data.news.map((r: any) => r.event_date).filter(Boolean))];
        return { ...record, data, data_time: publishedDates.length === 1 ? publishedDates[0] : null };
    }
    if (data.comparison) delete data.comparisons;
    if (data.stocks) delete data.accumulation_stocks;
    if (data.analysis) data.analysis = { strategyId: data.analysis.strategyId, warnings: data.analysis.warnings,
        overlay_labels: data.analysis.overlays?.map((o: any) => o.label), signal_count: data.analysis.signals?.length, last_signal: data.analysis.signals?.at(-1) };
    if (data.comparison?.results) data.comparison = { warnings: data.comparison.warnings,
        results: data.comparison.results.map((r: any) => ({ strategyId: r.strategyId,
            metrics: data.strategy_metrics?.some((m: any) => m.strategy_id === r.strategyId) ? r.metrics : undefined, warnings: r.warnings })) };
    return { ...record, data };
}

export function evidenceMemory(records: AgenticEvidence[], now = new Date()): Array<AgenticEvidence & { captured_at: string }> {
    const dedup = new Map<string, AgenticEvidence & { captured_at: string }>();
    for (const record of records) {
        if (!record || typeof record.source !== "string" || !record.data || typeof record.arguments !== "object") continue;
        if (!memoryTools.has(record.tool) || record.availability === "error" || !/^(?:supabase|tradingview|mixed):/.test(record.source)) continue;
        const captured = record.captured_at || now.toISOString();
        if (!Number.isFinite(Date.parse(captured)) || now.getTime() - Date.parse(captured) > 24 * 3600_000 || Date.parse(captured) > now.getTime() + 60_000) continue;
        dedup.set(record.tool + JSON.stringify(record.arguments), { ...compactEvidence(record), captured_at: captured });
    }
    const result: Array<AgenticEvidence & { captured_at: string }> = [];
    let bytes = 0;
    for (const record of [...dedup.values()].reverse()) {
        const size = JSON.stringify(record).length;
        if (bytes + size > 8000) continue;
        result.unshift(record); bytes += size;
        if (result.length === 6) break;
    }
    return result;
}

export function evidenceRows(data: any): any[] {
    if (!data || typeof data !== "object") return [];
    const rows = ["stocks", "levels", "positions", "recommendations", "comparison", "accumulation_stocks", "top_gainers", "top_losers", "top_liquidity_stocks", "news", "sector_exposure", "industry_exposure", "scenario_metrics"]
        .flatMap(key => Array.isArray(data[key]) ? data[key] : []);
    if (data.symbol) rows.push(data);
    if (data.egx30 && typeof data.egx30 === "object" && (data.egx30.close != null || data.egx30.change_pct != null)) {
        rows.push({
            symbol: "EGX",
            date: data.session_date ?? data.date ?? null,
            ...data.egx30,
            ...(data.market_liquidity && typeof data.market_liquidity === "object" ? data.market_liquidity : {}),
        });
    }
    if (data.egx33_shariah && typeof data.egx33_shariah === "object") {
        rows.push({
            symbol: "EGX33",
            date: data.session_date ?? data.date ?? null,
            ...data.egx33_shariah,
        });
    }
    return rows;
}

export function toAgenticEvidence(tool: string, args: any, data: any): AgenticEvidence {
    const rows = evidenceRows(data);
    const symbols = tool === "get_market_breadth" && rows.some(r => r.symbol === "EGX")
        ? ["EGX"]
        : [...new Set<string>(rows.map(r => r.symbol).filter(Boolean))];
    // A scan's output symbols (not its empty input) are the ordered reference for follow-ups.
    const dates = [...new Set<string>(rows.map(r => tool === "get_news"
        ? r.event_date || r.published_at || r.publication_date
        : r.date || r.scan_date || r.current_date || r.signal_date || r.published_at).filter(Boolean))];
    const missing = data?.availability === "missing" || rows.some(r => r.error || r.availability === "missing");
    const plannedPartial = data?.availability === "partial";
    const verifiedEmptyScreen = tool === "screen_stocks" && data?.status === "success" && Boolean(data.date)
        && Array.isArray(data.stocks) && typeof data.scan_complete === "boolean";
    const hasProviderQuotes = rows.some(row => row.live_quote_available === true);
    return { tool, arguments: args, data, source: tool === "get_live_quote" || hasProviderQuotes ? (rows.every(r=>r.live_quote_available) ? "tradingview:provider-snapshot" : hasProviderQuotes ? "mixed:tradingview+supabase" : "supabase:stored-fallback") : tool === "list_chart_strategies" ? "deterministic:strategy-catalog" : "supabase:" + ({ get_stock: "stock_prices+stock_technical_indicators+stocks+stock_scans_summary", get_stock_levels: "stock_prices",
        apply_chart_strategy: "stock_prices+deterministic-strategy-engine", compare_strategies_history: "stock_prices+deterministic-backtest", list_chart_strategies: "strategy-catalog",
        calculate_position: "stock_prices+stock_technical_indicators+position-calculation", manage_portfolio: "positions+stock_prices+stock_technical_indicators", get_market: "market_cache+stock_technical_indicators", get_news: "stock_news_sentiment+stocks",
        get_recommendations: "scan_results+stock_technical_indicators+short_swing_checkpoints", get_corporate_actions: "corporate_actions", get_accumulation_stocks: "stock_scans_summary", get_comparison: "stock_prices+stock_technical_indicators+stock_scans_summary",
        get_technical_scan: args.preset === "smart_money_flow" ? "stock_scans_summary" : "stock_technical_indicators",
        get_fundamentals: "stock_fundamentals", get_sector_peers: "stock_fundamentals", get_market_breadth: "stock_technical_indicators+deterministic-breadth",
        screen_stocks: "stock_technical_indicators+stock_prices", analyze_portfolio_risk: "positions+stock_fundamentals+scenario-calculation",
        enable_autonomous_recommendations: "user_consent+client_action",
        disable_autonomous_recommendations: "user_consent+client_action" } as any)[tool],
        data_time: dates.length === 1 ? dates[0] : data?.date || data?.session_date || null, symbols,
        availability: data?.status === "error" ? "error" : data?.availability === "missing" || (!verifiedEmptyScreen && !rows.length && !data?.egx30?.close && !data?.persisted && !data?.strategies?.length)
            ? "missing" : plannedPartial || missing || data?.valuation_complete === false || data?.scan_complete === false
                || data?.sector_concentration_complete === false || data?.industry_concentration_complete === false || data?.truncated ? "partial" : "available", data_type: tool === "get_live_quote" || hasProviderQuotes ? "provider-snapshot" : "historical" };
}

export function agenticFacts(evidence: AgenticEvidence[]): FactRecord[] {
    const adapted: ToolResult[] = evidence.filter(e => e.availability !== "error").map(e => ({ tool: e.tool, source: e.source, symbols: e.symbols,
        data_type: e.data_type, data_time: e.data_time || "", data: evidenceRows(e.data).map(row => ({ ...row,
        vol_ratio: row.relative_volume ?? row.r_vol ?? row.vol_ratio,
        acc_score: row.accumulation_score ?? row.acc_score, dist_score: row.distribution_score ?? row.dist_score,
        target_price: row.take_profit_1 ?? row.target_price, profit_pct: row.profit_loss_pct ?? row.realized_return_pct ?? row.unrealized_return_pct,
        cost_basis: row.cost ?? row.cost_basis, profit_value: row.profit_loss_val ?? row.profit_value,
        position_pct: row.allocation_pct, value: row.allocated_capital,
        close: row.close ?? row.current_price, price: row.current_price ?? row.close,
        change_pct: row.change_pct ?? row.change_percent ?? row.change,
        macd_hist: row.macd_hist ?? row.macd_histogram,
        rsi: row.rsi ?? row.rsi_14,
        king_ai_score: row.king_ai ?? row.king_ai_score,
        egx_ai_score: row.egx_ai ?? row.egx_ai_score,
        bollinger_upper: row.bollinger_upper ?? row.bb_upper,
        bollinger_lower: row.bollinger_lower ?? row.bb_lower,
        pe_ratio: row.pe_ratio ?? row.peRatio,
        eps: row.eps,
        market_cap: row.market_cap ?? row.marketCap,
    })) }));
    const facts = buildFactRecords(adapted);
    for (const e of evidence) {
        for (const row of evidenceRows(e.data)) {
            for (const [key, field] of [["total", "chart_signal_count"], ["buy_count", "chart_buy_signal_count"], ["sell_count", "chart_sell_signal_count"]] as const) {
                const value = row.signal_summary?.[key];
                if (typeof value === "number" && Number.isFinite(value)) facts.push({ id: `${row.symbol}:${row.analysis?.strategyId}:${key}`, symbol: row.symbol, field, value, unit: "count", as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            for (const metrics of row.strategy_metrics || []) {
                for (const {key, field, unit} of BACKTEST_METRICS) if (typeof metrics[key] === "number" && Number.isFinite(metrics[key])) facts.push({ id: `${row.symbol}:${metrics.strategy_id}:${key}`, symbol: row.symbol, field, value: metrics[key], unit, as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
                if (Number.isFinite(row.candle_count)) facts.push({ id: `${row.symbol}:${metrics.strategy_id}:candle_count`, symbol: row.symbol, field: "backtest_candle_count", value: row.candle_count, unit: "count", as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            // Distances are derived from quote/level rows for primary and secondary levels.
            const closePrices = [row.close, row.current_price].filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v > 0);
            if (row.symbol && closePrices.length > 0) {
                for (const closeVal of closePrices) {
                    for (const [level, field] of [
                        ["support", "distance_from_support_pct"],
                        ["resistance", "distance_from_resistance_pct"],
                        ["support_2", "distance_from_support_pct"],
                        ["resistance_2", "distance_from_resistance_pct"]
                    ] as const) {
                        if (Number.isFinite(row[level]) && row[level] > 0)
                            facts.push({ id: `${row.symbol}:${field}:${level}:${closeVal}`, symbol: row.symbol, field,
                                value: (row[level] - closeVal) / closeVal * 100, unit: "percent",
                                as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
                    }
                }
            }
            // Different calculated targets remain separate supported observations.
            const target2Val = row.take_profit_2 ?? row.target_2;
            if (row.symbol && Number.isFinite(target2Val)) facts.push({ id: `${row.symbol}:target2`, symbol: row.symbol,
                field: "target_price", value: target2Val, unit: "egp", as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            if (row.symbol && Number.isFinite(row.support_2)) facts.push({ id: `${row.symbol}:support2`, symbol: row.symbol,
                field: "support", value: row.support_2, unit: "egp", as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            if (row.symbol && Number.isFinite(row.resistance_2)) facts.push({ id: `${row.symbol}:resistance2`, symbol: row.symbol,
                field: "resistance", value: row.resistance_2, unit: "egp", as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            if (row.symbol && typeof row.entry_zone === "string") for (const value of row.entry_zone.match(/\d+(?:\.\d+)?/g) || []) {
                facts.push({ id: `${row.symbol}:entry:${value}`, symbol: row.symbol, field: "entry_price", value: Number(value), unit: "egp",
                    as_of: row.date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            if (row.active_recommendation && row.symbol) {
                const rec = row.active_recommendation;
                if (Number.isFinite(rec.entry_price)) facts.push({ id: `${row.symbol}:rec:entry`, symbol: row.symbol, field: "entry_price", value: rec.entry_price, unit: "egp", as_of: rec.signal_date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
                if (Number.isFinite(rec.stop_loss)) facts.push({ id: `${row.symbol}:rec:stop`, symbol: row.symbol, field: "stop_loss", value: rec.stop_loss, unit: "egp", as_of: rec.signal_date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
                if (Number.isFinite(rec.target_price)) facts.push({ id: `${row.symbol}:rec:target`, symbol: row.symbol, field: "target_price", value: rec.target_price, unit: "egp", as_of: rec.signal_date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            if (row.symbol && typeof row.consecutive_acc_days === "number" && Number.isFinite(row.consecutive_acc_days)) {
                facts.push({ id: `${row.symbol}:consecutive_acc_days`, symbol: row.symbol, field: "quantity", value: row.consecutive_acc_days, unit: "count", as_of: row.date ?? row.scan_date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            if (row.symbol && typeof row.consecutive_dist_days === "number" && Number.isFinite(row.consecutive_dist_days)) {
                facts.push({ id: `${row.symbol}:consecutive_dist_days`, symbol: row.symbol, field: "quantity", value: row.consecutive_dist_days, unit: "count", as_of: row.date ?? row.scan_date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            if (row.symbol && Array.isArray(row.recent_sessions)) {
                for (const s of row.recent_sessions) {
                    const sDate = s.date ? String(s.date).slice(0, 10) : null;
                    if (s.close != null && Number.isFinite(s.close)) {
                        facts.push({ id: `${row.symbol}:close:${sDate}`, symbol: row.symbol, field: "close", value: s.close, unit: "egp", as_of: sDate, source: "supabase:stock_prices", tool: e.tool, fetched_at: new Date().toISOString() });
                    }
                    for (const field of ["high", "low"] as const) if (typeof s[field] === "number" && Number.isFinite(s[field])) {
                        facts.push({ id:`${row.symbol}:${field}:${sDate}`, symbol:row.symbol, field, value:s[field], unit:"egp", as_of:sDate, source:"supabase:stock_prices", tool:e.tool, fetched_at:new Date().toISOString() });
                    }
                    if (s.change_pct != null && Number.isFinite(s.change_pct)) {
                        facts.push({ id: `${row.symbol}:change_pct:${sDate}`, symbol: row.symbol, field: "change_pct", value: s.change_pct, unit: "percent", as_of: sDate, source: "supabase:stock_prices", tool: e.tool, fetched_at: new Date().toISOString() });
                    }
                }
            }
            if (row.symbol && row.last_week_summary) {
                const week = row.last_week_summary;
                if (typeof week.sessions_count === "number" && Number.isFinite(week.sessions_count)) facts.push({id:`${row.symbol}:week:sessions_count`,symbol:row.symbol,field:"quantity",value:week.sessions_count,unit:"count",as_of:week.end_date ?? null,source:"supabase:stock_prices",tool:e.tool,fetched_at:new Date().toISOString()});
                for (const [key,dateKey] of [["baseline_close","baseline_date"],["start_close","start_date"],["end_close","end_date"]] as const) {
                    if (typeof week[key] === "number" && Number.isFinite(week[key])) facts.push({id:`${row.symbol}:week:${key}`,symbol:row.symbol,field:"close",value:week[key],unit:"egp",as_of:week[dateKey] ?? null,source:"supabase:stock_prices",tool:e.tool,fetched_at:new Date().toISOString()});
                }
                if (typeof week.within_week_change_pct === "number" && Number.isFinite(week.within_week_change_pct)) facts.push({id:`${row.symbol}:within_week_change`,symbol:row.symbol,field:"change_pct",value:week.within_week_change_pct,unit:"percent",as_of:week.end_date ?? null,source:"supabase:stock_prices",tool:e.tool,fetched_at:new Date().toISOString()});
            }
            if (row.symbol && row.last_week_summary?.change_pct != null && Number.isFinite(row.last_week_summary.change_pct)) {
                facts.push({ id: `${row.symbol}:last_week_change_pct`, symbol: row.symbol, field: "change_pct", value: row.last_week_summary.change_pct, unit: "percent", as_of: row.last_week_summary.end_date ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() });
            }
            if (row.symbol) {
                const rowAsOf = row.date ?? row.scan_date ?? e.data_time ?? null;
                const rowMeta = { as_of: rowAsOf, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() };
                for (const k of ["turnover_egp", "turnover_million_egp", "turnover_billion_egp", "total_turnover_egp", "total_turnover_million_egp", "total_turnover_billion_egp", "avg_20d_turnover_egp", "avg_20d_turnover_million_egp", "avg_20d_turnover_billion_egp", "advancing_turnover_egp", "advancing_turnover_million_egp", "declining_turnover_egp", "declining_turnover_million_egp", "unchanged_turnover_egp", "unchanged_turnover_million_egp"]) {
                    if (typeof row[k] === "number" && Number.isFinite(row[k])) {
                        facts.push({ id: `${row.symbol}:${k}:val`, symbol: row.symbol, field: "value", value: row[k], unit: "egp", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:vol`, symbol: row.symbol, field: "volume", value: row[k], unit: "shares", ...rowMeta });
                    }
                }
                for (const k of ["market_share_pct", "turnover_vs_20d_pct", "advancing_turnover_pct", "declining_turnover_pct", "unchanged_turnover_pct", "top5_concentration_pct", "top10_concentration_pct", "advancing_stocks_pct"]) {
                    if (typeof row[k] === "number" && Number.isFinite(row[k])) {
                        facts.push({ id: `${row.symbol}:${k}:pos`, symbol: row.symbol, field: "position_pct", value: row[k], unit: "percent", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:chg`, symbol: row.symbol, field: "change_pct", value: row[k], unit: "percent", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:brp`, symbol: row.symbol, field: "breadth_advancing_pct", value: row[k], unit: "percent", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:rat`, symbol: row.symbol, field: "vol_ratio", value: row[k], unit: "ratio", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:val`, symbol: row.symbol, field: "value", value: row[k], unit: "egp", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:prf`, symbol: row.symbol, field: "profit_pct", value: row[k], unit: "percent", ...rowMeta });
                    }
                }
                for (const k of ["turnover_vs_20d_ratio", "cmf_20"]) {
                    if (typeof row[k] === "number" && Number.isFinite(row[k])) {
                        facts.push({ id: `${row.symbol}:${k}:rat`, symbol: row.symbol, field: "vol_ratio", value: row[k], unit: "ratio", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:val`, symbol: row.symbol, field: "value", value: row[k], unit: "egp", ...rowMeta });
                    }
                }
                for (const [k, f] of [
                    ["stocks_traded_count", "breadth_total"],
                    ["advancing_count", "breadth_advancing"],
                    ["declining_count", "breadth_declining"],
                    ["unchanged_count", "breadth_unchanged"],
                ] as const) {
                    if (typeof row[k] === "number" && Number.isFinite(row[k])) {
                        facts.push({ id: `${row.symbol}:${k}:${f}`, symbol: row.symbol, field: f, value: row[k], unit: "count", ...rowMeta });
                        facts.push({ id: `${row.symbol}:${k}:qty`, symbol: row.symbol, field: "quantity", value: row[k], unit: "count", ...rowMeta });
                    }
                }
                for (const k of ["unusual_volume_surge_count", "positive_cmf_count", "negative_cmf_count", "accumulation_count", "strong_accumulation_count", "distribution_count", "strong_distribution_count"]) {
                    if (typeof row[k] === "number" && Number.isFinite(row[k])) {
                        for (const f of ["quantity", "value", "volume", "vol_ratio", "breadth_total", "breadth_advancing", "breadth_declining", "acc_score", "dist_score"] as const) {
                            facts.push({ id: `${row.symbol}:${k}:${f}`, symbol: row.symbol, field: f, value: row[k], unit: "count", ...rowMeta });
                        }
                    }
                }
            }
        }
        if (Array.isArray(e.data?.sector_liquidity)) {
            const secMeta = { as_of: e.data?.session_date ?? e.data_time ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() };
            for (const sec of e.data.sector_liquidity) {
                const tag = String(sec.sector || sec.sector_ar || sec.sector_en || "sec");
                const targetSymbols = ["EGX", ...(sec.top_stock_symbol ? [String(sec.top_stock_symbol).toUpperCase()] : [])];
                for (const targetSym of targetSymbols) {
                    for (const k of ["turnover_egp", "turnover_million_egp", "top_stock_turnover_million_egp"]) {
                        if (typeof sec[k] === "number" && Number.isFinite(sec[k])) {
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:val`, symbol: targetSym, field: "value", value: sec[k], unit: "egp", ...secMeta });
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:vol`, symbol: targetSym, field: "volume", value: sec[k], unit: "shares", ...secMeta });
                        }
                    }
                    for (const k of ["market_share_pct", "weighted_change_pct", "top_stock_change_pct", "top_stock_share_in_sector_pct"]) {
                        if (typeof sec[k] === "number" && Number.isFinite(sec[k])) {
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:pos`, symbol: targetSym, field: "position_pct", value: sec[k], unit: "percent", ...secMeta });
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:chg`, symbol: targetSym, field: "change_pct", value: sec[k], unit: "percent", ...secMeta });
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:brp`, symbol: targetSym, field: "breadth_advancing_pct", value: sec[k], unit: "percent", ...secMeta });
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:val`, symbol: targetSym, field: "value", value: sec[k], unit: "egp", ...secMeta });
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:prf`, symbol: targetSym, field: "profit_pct", value: sec[k], unit: "percent", ...secMeta });
                        }
                    }
                    if (typeof sec.weighted_cmf_20 === "number" && Number.isFinite(sec.weighted_cmf_20)) {
                        facts.push({ id: `${targetSym}:sec:${tag}:cmf:rat`, symbol: targetSym, field: "vol_ratio", value: sec.weighted_cmf_20, unit: "ratio", ...secMeta });
                        facts.push({ id: `${targetSym}:sec:${tag}:cmf:val`, symbol: targetSym, field: "value", value: sec.weighted_cmf_20, unit: "egp", ...secMeta });
                    }
                    for (const [k, f] of [
                        ["stocks_count", "breadth_total"],
                        ["advancing_count", "breadth_advancing"],
                        ["declining_count", "breadth_declining"],
                    ] as const) {
                        if (typeof sec[k] === "number" && Number.isFinite(sec[k])) {
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:${f}`, symbol: targetSym, field: f, value: sec[k], unit: "count", ...secMeta });
                            facts.push({ id: `${targetSym}:sec:${tag}:${k}:qty`, symbol: targetSym, field: "quantity", value: sec[k], unit: "count", ...secMeta });
                        }
                    }
                }
            }
        }
        if (e.tool === "manage_portfolio" && e.data?.summary) {
            const sum = e.data.summary;
            const meta = { as_of: e.data_time ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() };
            if (Number.isFinite(sum.total_invested)) facts.push({ id: "PORTFOLIO:total_invested", symbol: "PORTFOLIO", field: "cost_basis", value: sum.total_invested, unit: "egp", ...meta });
            if (Number.isFinite(sum.total_market_value)) facts.push({ id: "PORTFOLIO:total_market_value", symbol: "PORTFOLIO", field: "market_value", value: sum.total_market_value, unit: "egp", ...meta });
            if (Number.isFinite(sum.unrealized_pl_val)) facts.push({ id: "PORTFOLIO:unrealized_pl_val", symbol: "PORTFOLIO", field: "profit_value", value: sum.unrealized_pl_val, unit: "egp", ...meta });
            if (Number.isFinite(sum.unrealized_pl_pct)) facts.push({ id: "PORTFOLIO:unrealized_pl_pct", symbol: "PORTFOLIO", field: "profit_pct", value: sum.unrealized_pl_pct, unit: "percent", ...meta });
            if (Number.isFinite(sum.positions_count)) facts.push({ id: "PORTFOLIO:positions_count", symbol: "PORTFOLIO", field: "quantity", value: sum.positions_count, unit: "count", ...meta });
        }
        if (e.tool === "get_recommendations" && e.data?.performance_summary) {
            const ps = e.data.performance_summary;
            const meta = { as_of: e.data_time ?? null, source: e.source, tool: e.tool, fetched_at: new Date().toISOString() };
            if (Number.isFinite(ps.total_recommendations)) facts.push({ id: "RECOMMENDATIONS:total", symbol: "RECOMMENDATIONS", field: "quantity", value: ps.total_recommendations, unit: "count", ...meta });
            if (Number.isFinite(ps.closed_count)) facts.push({ id: "RECOMMENDATIONS:closed", symbol: "RECOMMENDATIONS", field: "quantity", value: ps.closed_count, unit: "count", ...meta });
            if (Number.isFinite(ps.open_count)) facts.push({ id: "RECOMMENDATIONS:open", symbol: "RECOMMENDATIONS", field: "quantity", value: ps.open_count, unit: "count", ...meta });
            if (Number.isFinite(ps.win_count)) facts.push({ id: "RECOMMENDATIONS:wins", symbol: "RECOMMENDATIONS", field: "quantity", value: ps.win_count, unit: "count", ...meta });
            if (Number.isFinite(ps.loss_count)) facts.push({ id: "RECOMMENDATIONS:losses", symbol: "RECOMMENDATIONS", field: "quantity", value: ps.loss_count, unit: "count", ...meta });
            if (Number.isFinite(ps.win_rate_pct)) facts.push({ id: "RECOMMENDATIONS:win_rate", symbol: "RECOMMENDATIONS", field: "profit_pct", value: ps.win_rate_pct, unit: "percent", ...meta });
            if (Number.isFinite(ps.avg_return_pct)) facts.push({ id: "RECOMMENDATIONS:avg_return", symbol: "RECOMMENDATIONS", field: "profit_pct", value: ps.avg_return_pct, unit: "percent", ...meta });
            if (Number.isFinite(ps.avg_win_pct)) facts.push({ id: "RECOMMENDATIONS:avg_win", symbol: "RECOMMENDATIONS", field: "profit_pct", value: ps.avg_win_pct, unit: "percent", ...meta });
            if (Number.isFinite(ps.avg_loss_pct)) facts.push({ id: "RECOMMENDATIONS:avg_loss", symbol: "RECOMMENDATIONS", field: "profit_pct", value: ps.avg_loss_pct, unit: "percent", ...meta });
            if (ps.best_trade && Number.isFinite(ps.best_trade.return_pct)) facts.push({ id: `${ps.best_trade.symbol}:best_trade`, symbol: ps.best_trade.symbol, field: "profit_pct", value: ps.best_trade.return_pct, unit: "percent", ...meta });
            if (ps.worst_trade && Number.isFinite(ps.worst_trade.return_pct)) facts.push({ id: `${ps.worst_trade.symbol}:worst_trade`, symbol: ps.worst_trade.symbol, field: "profit_pct", value: ps.worst_trade.return_pct, unit: "percent", ...meta });
        }
    }
    return facts;
}

function cleanCellText(text: string): string {
    return normalizeEvidenceNumbers(text)
        // 1. Strip full dates and short dates FIRST before any dash/number normalization
        .replace(/(?:\b|\D)\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\b|\D)/g, " ")
        .replace(/(?:\b|\D)\d{1,2}[-/.]\d{1,2}[-/.]\d{4}(?:\b|\D)/g, " ")
        .replace(/(?:جلسة|بتاريخ|تاريخ|يوم)\s*\b\d{1,2}[-/]\d{1,2}\b/g, " ")
        .replace(/\b(?:0?[1-9]|[12][0-9]|3[01])[-/](?:0?[1-9]|1[0-2])\b/g, " ")
        // 2. Disambiguate range dashes vs negative values vs bullet points
        .replace(/(?:^|[\s|:،,])[-−–—•*]\s+(\d)/g, " $1")
        .replace(/(?<=\d)\s*[-−–—]\s*(?=\d)/g, " ")
        .replace(/(\d+(?:\.\d+)?)\s*[%٪]?\s*[-−–](?!\s*\d)/g, "-$1")
        .replace(/[−–—]/g, "-")
        .replace(/(?<=\d),(?=\d{3}(?:\D|$))/g, "")
        // 3. Strip ordinal targets, rank markers, and indicator parameters
        .replace(/(?:(?:ال)?هدف|(?:ال)?مستهدف|(?:ال)?دعم|(?:ال)?مقاوم[ةه]|(?:ال)?مركز|(?:ال)?ترتيب|(?:ال)?أولوية|(?:ال)?أفضلية|(?:ال)?خيار|(?:ال)?مستوى|(?:ال)?فئ[ةه]|target|tp|t|rank)\s*\(?\s*[1-9]\s*\)?/gi, " ")
        .replace(/\b(?:RSI|EMA|SMA|BB|MACD|ATR|STOCH|CMF)\s*[-_]?\s*(?:\(\s*\d+(?:[\s,]+\d+)*\s*\)|\d+)/gi, " ")
        .replace(/\b(?:R\.?Vol|CMF)\s*(?:>=|>|<=|<|=|أكبر\s*من|أقل\s*من)\s*[-+]?\d+(?:\.\d+)?\s*[x×]?/gi, " ")
        .replace(/(?:(?:حد|مستوى|منطقة)\s*)?(?:(?:ال)?تشبع\s*(?:ال)?(?:بيعي|شرائي)|oversold|overbought)\s*\(?\s*(?:30|70)\s*\)?/gi, " ")
        .replace(/(?:(?:حد|مستوى)\s*(?:RSI\s*)?)\(?\s*(?:30|70)\s*\)?/gi, " ")
        .replace(/(?:مؤشر\s*(?:القوة\s*النسبية)?|فترة|إعداد)\s*\(?\s*14\s*\)?/gi, " ")
        .replace(/(?:(?:ال|ب|ل)?متوسط(?:\s*(?:ال)?متحرك)?|(?:ال)?موفينج(?:\s*(?:ال)?أفريج)?|EMA|SMA)\s*\(?\s*(?:5|10|14|20|30|50|60|100|200)\s*\)?(?:\s*(?:يوم|يوماً|جلس[ةه]|جلسات))?/gi, " ")
        .replace(/(?:فوق|تحت|أعلى\s*من|أسفل\s*من|مخترق|كسر)\s*(?:(?:ال)?متوسط(?:\s*(?:ال)?متحرك)?|(?:ال)?موفينج(?:\s*(?:ال)?أفريج)?|EMA|SMA)?\s*(?:14|20|50|100|200)/gi, " ")
        .replace(/(?:(?:فوق|تحت|أعلى|أدنى|بين)\s*)?[12]\s*(?:من\s*2\s*)?متوسط(?:ات|ين)?/gi, " ")
        .replace(/\b(?:14|20|50|100|200)\s*يوماً?\b/gi, " ")
        .replace(/\b(?:RSI|EMA|SMA|BB|MACD|ATR|STOCH|CMF)\b/gi, " ")
        // Strip Egyptian exchange index names and references (EGX30, EGX33 Shariah, EGX70, EGX100, etc.)
        .replace(/\b(?:EGX|إيجي\s*إكس|ايجي\s*اكس|مؤشر\s*(?:الشريعة\s*)?|شريعة)\s*[-_]?\s*(?:30|33|70|100|20|50)(?:\s*(?:shariah|شريعة))?\b/gi, " ")
        .replace(/\bEGX[-_]?(?:30|33|70|100|20|50)\b/gi, " ")
        .replace(/(?:مؤشر\s*(?:الشريعة)?\s*)\(?\s*(?:30|33|70|100|20|50)\s*\)?/gi, " ")
        // 4. Strip percentage multipliers/proportions in descriptions (e.g. "98% من الدعم", "105% من المقاومة")
        .replace(/\b\d+(?:\.\d+)?\s*[%٪]\s*من\s*(?:الدعم|المقاومة|الإغلاق|السعر)/gi, " ")
        .replace(/\b(?:8[0-9]|9[0-9]|10[0-9]|11[0-9]|12[0-9])\s*[%٪]\s*من\s*\S+/gi, " ")
        // 5. Strip session count and top-N group descriptions (e.g. "آخر 20 جلسة", "أعلى 5 أسهم", "أعلى 10 أسهم")
        .replace(/(?:(?:ال)?أعلى|(?:ال)?أكبر|(?:ال)?أول|(?:ال)?أهم|top)\s*\d+\s*(?:أسهم|اسهم|قطاعات|شركات|stocks?|sectors?)?/gi, " ")
        .replace(/(?:ل?آخر|ل?مدى|خلال|في|لـ?)?\s*\d+\s*جلس(?:[ةه]|ات)(?:\s+تداول)?/gi, " ")
        .replace(/\b\d+\s*(?:sessions?|trading\s*days?)\b/gi, " ");
}

/** Metric labels describe generated evidence, never user intent routing. */
function compoundMetricFields(label: string): FactRecord["field"][] | null {
    const parts = label.replace(/[*_`]/g, "").split(/\s*[/،]\s*/);
    if (parts.length < 2) return null;

    // 1. MACD
    const macdFields = parts.map(part => /هيست|hist/i.test(part) ? "macd_hist"
        : /إشار|اشار|signal/i.test(part) ? "macd_signal"
            : /^\s*MACD\s*$/i.test(part) ? "macd" : null);
    if (macdFields.every(Boolean) && new Set(macdFields).size === macdFields.length) {
        return macdFields as FactRecord["field"][];
    }

    // 2. Accumulation / Distribution (e.g. "درجة التجميع / التوزيع", "تجميع / تصريف")
    const accDistFields = parts.map(part => /تجميع|accumulation|acc/i.test(part) ? "acc_score"
        : /توزيع|تصريف|distribution|dist/i.test(part) ? "dist_score" : null);
    if (accDistFields.every(Boolean) && new Set(accDistFields).size === accDistFields.length) {
        return accDistFields as FactRecord["field"][];
    }

    // 3. Support / Resistance
    const supResFields = parts.map(part => /دعم|support/i.test(part) ? "support"
        : /مقاوم|resistance/i.test(part) ? "resistance" : null);
    if (supResFields.every(Boolean) && new Set(supResFields).size === supResFields.length) {
        return supResFields as FactRecord["field"][];
    }

    // 4. EMA 50 / 200
    const emaFields = parts.map(part => /EMA\s*50|50/i.test(part) ? "ema_50"
        : /EMA\s*200|200/i.test(part) ? "ema_200" : null);
    if (emaFields.every(Boolean) && new Set(emaFields).size === emaFields.length) {
        return emaFields as FactRecord["field"][];
    }

    // 5. Advancing / Declining counts (e.g. "صاعد / هابط", "صاعدة / هابطة")
    if (!/نسب|إلى|الى|ratio/i.test(label)) {
        const advDecFields = parts.map(part => /صاعد|مرتفع|advanc/i.test(part) ? "breadth_advancing"
            : /هابط|منخفض|declin/i.test(part) ? "breadth_declining"
            : /ثابت|مستقر|unchang/i.test(part) ? "breadth_unchanged" : null);
        if (advDecFields.every(Boolean) && new Set(advDecFields).size === advDecFields.length) {
            return advDecFields as FactRecord["field"][];
        }
    }

    return null;
}

function checkCompoundMetricCell(label: string, cell: string, symbol: string, facts: FactRecord[]): string[] | null {
    const fields = compoundMetricFields(label);
    if (!fields) return null;
    const parts = normalizeEvidenceNumbers(cell.replace(/[*_`]/g, "")).split(/\s*[/،]\s*/);
    if (parts.length !== fields.length) return null;
    const reasons: string[] = [];
    for (let i = 0; i < fields.length; i++) {
        const cleanedPart = cleanCellText(parts[i]);
        const match = cleanedPart.match(/[-+]?\d+(?:\.\d+)?/);
        if (!match) continue;
        const value = Number(match[0]);
        const precision = match[0].split(".")[1]?.length || 0;
        const relevant = facts.filter(f => f.symbol === symbol && f.field === fields[i]);
        // Support distribution score 0 when in accumulation or dist_score is 0/null in facts
        const isDistZeroAllowed = fields[i] === "dist_score" && value === 0 && (
            relevant.some(f => f.value === 0) ||
            facts.some(f => f.symbol === symbol && f.field === "acc_score" && f.value > 0)
        );
        // Ordered metrics retain their signs and accept only rounding at the
        // displayed precision. Never borrow another metric's similar value.
        if (!isDistZeroAllowed && !relevant.some(f => Math.abs(value - f.value) <= 0.5 * 10 ** -precision + 1e-8))
            reasons.push(`table_value_not_grounded:${symbol}:${value}`);
    }
    return reasons;
}

/** Resolve a displayed date against actual evidence, including Arabic month names. */
function groundedTableDate(cell: string, dates: string[]): string | null {
    const normalize = (text: string) => normalizeDigitsAndNumberFormatting(text.replace(/[*_`]/g, "")).replace(/[،,\u200e\u200f]/g, "").replace(/[أإآ]/g, "ا").replace(/^جلسة\s+/, "").replace(/\s+/g, " ").trim();
    const text = normalize(cell);
    const matches = [...new Set(dates)].filter(date => {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
        const [year,month,day] = date.split("-").map(Number);
        const instant = new Date(`${date}T12:00:00Z`);
        const variants = [date, `${day}/${month}/${year}`, `${day}/${month}`, `${date.slice(8,10)}/${date.slice(5,7)}`, `${date.slice(8,10)}/${date.slice(5,7)}/${year}`,
            new Intl.DateTimeFormat("ar-EG",{timeZone:"UTC",day:"numeric",month:"long",year:"numeric"}).format(instant),
            new Intl.DateTimeFormat("ar-EG",{timeZone:"UTC",day:"numeric",month:"long"}).format(instant)];
        return variants.some(value => normalize(value) === text);
    });
    return matches.length === 1 ? matches[0] : null;
}

function tableMetricFields(label: string): FactRecord["field"][] | undefined {
    const text = label.replace(/[*_]/g, "");
    // Specific financial labels take precedence over generic profit/currency words.
    if (/مضاعف.*ربحي|مكرر.*ربحي|P\/?E|pe.?ratio/i.test(text)) return ["pe_ratio"];
    if (/ربحية.*سهم|EPS/i.test(text)) return ["eps"];
    if (/القيمة السوقية للشركة|قيمة.*سوقية.*شركة|market.?cap/i.test(text)) return ["market_cap"];
    if (/(?:عائد|تغير).*(?:أسبوع|اسبوع)|(?:أسبوع|اسبوع).*(?:عائد|تغير)/i.test(text)) return ["change_pct"];
    if (/^(?:الفترة|فترة الاختبار|عدد الشموع|شموع|period|candles|bars)$/i.test(text.trim())) return ["backtest_candle_count"];
    if (/^(?:عدد الجلسات|جلسات)$/i.test(text.trim())) return ["quantity", "backtest_candle_count"];
    if (/ربح|خسار/i.test(text) && /%|٪|نسب/i.test(text)) return ["profit_pct"];
    if (/ربح|خسار/i.test(text) && /جنيه|بالجنيه/i.test(text)) return ["profit_value"];
    if (/^(?:(?:سعر|السعر)\s*)?(?:أعلى|اعلى|الأعلى|الاعلى|high)(?:\s*(?:سعر|السعر|price))?(?:\s*(?:للجلسة|الجلسة|اليومي))?$/i.test(text.replace(/\([^)]*\)/g, "").trim())) return ["high"];
    if (/^(?:(?:سعر|السعر)\s*)?(?:أدنى|ادنى|الأدنى|الادنى|low)(?:\s*(?:سعر|السعر|price))?(?:\s*(?:للجلسة|الجلسة|اليومي))?$/i.test(text.replace(/\([^)]*\)/g, "").trim())) return ["low"];
    if (/EMA\s*50/i.test(text) && /EMA\s*200/i.test(text)) return ["ema_50","ema_200"];
    const labels: Array<[RegExp, FactRecord["field"][]]> = [
        [/(?:مضاعف|مكرر)\s*(?:الربحي[ةه]|الربح)|P\s*[/]?\s*E|pe.?ratio/i, ["pe_ratio"]],
        [/(?:ربحي[ةه]|عائد)\s*(?:السهم|سهم)|EPS/i, ["eps"]],
        [/(?:القيمة|قيمة)\s*(?:السوقي[ةه]|سوقي[ةه])|رأس\s*المال\s*السوقي|market.?cap/i, ["market_cap", "market_value"]],
        [/(?:(?:السعر|الإغلاق|اغلاق|إقفال|price|close).*(?:تغير|التغير|التغيّر|change))|(?:(?:تغير|التغير|التغيّر|change).*(?:السعر|الإغلاق|اغلاق|إقفال|price|close))/i, ["price", "close", "change_pct"]],
        [/(?:حصة|نسبة|وزن|تركز|تركيز).*(?:(?:ال)?سيول[ةه]|(?:ال)?سوق|(?:ال)?تداول|(?:ال)?قطاع|أعلى|أكبر)|market.?share|concentration/i,["position_pct","change_pct","value","quantity"]],
        [/(?:قيمة|إجمالي|مجموع|حجم|أحجام|احجام|متوسط)\s*(?:(?:ال)?تداول|(?:ال)?سيول[ةه])|(?:ال)?سيول[ةه]|تدفق.*سيول[ةه]|turnover|money.?flow/i,["value","volume","vol_ratio","position_pct","change_pct","quantity","acc_score","dist_score"]],
        [/صاعد.*هابط|الصاعدة.*الهابطة|advance.*decline/i,["breadth_ad_ratio"]], [/نسبة.*صاعد|الصاعدة.*%|advancing.*%/i,["breadth_advancing_pct"]],
        [/صاعد|مرتفعة|advancing/i,["breadth_advancing"]], [/هابط|منخفضة|declining/i,["breadth_declining"]], [/ثابت|unchanged/i,["breadth_unchanged"]], [/الأسهم.*(?:صالحة|تغير صالح)|إجمالي.*(?:أسهم|تغير صالح)|total.*stocks/i,["breadth_total"]],
        [/^(?!.*سعر).*(?:إشارات.*شراء|buy.*signals|(?:إشارات|صفقات)\s*شراء|^شراء$)/i,["chart_buy_signal_count"]], [/^(?!.*سعر).*(?:إشارات.*بيع|sell.*signals|(?:إشارات|صفقات)\s*بيع|^بيع$)/i,["chart_sell_signal_count"]], [/(?:عدد|إجمالي|مجموع|كل)?\s*إشارات|signal.*count|إشارات/i,["chart_signal_count"]],
        ...BACKTEST_METRICS.map(({pattern,field}): [RegExp, FactRecord["field"][]] => [pattern,field === "backtest_return_pct" ? ["profit_pct",field] : [field]]),
        [/RSI|القوة النسبية/i,["rsi"]], [/هيست|hist/i,["macd_hist"]], [/MACD.*(?:signal|إشار|اشار)|(?:signal|إشار|اشار).*MACD/i,["macd_signal"]], [/MACD/i,["macd","macd_signal","macd_hist"]],
        [/EMA\s*50/i,["ema_50"]], [/EMA\s*200/i,["ema_200"]], [/حجم.*نسبي|الحجم النسبي|r_vol|vol_ratio/i,["vol_ratio","quantity"]],
        [/CMF|تدفق\s*نقدي|Chaikin/i,["vol_ratio","value","quantity"]],
        [/(?:حجم|أحجام|احجام)\s*(?:التداول|السيولة)?|volume/i,["volume","vol_ratio","value","quantity"]],
        [/KING/i,["king_ai_score"]], [/EGX.*AI/i,["egx_ai_score"]],
        [/(?:(?:ال)?تجميع|acc).*(?:(?:ال)?توزيع|(?:ال)?تصريف|dist)|(?:(?:ال)?توزيع|(?:ال)?تصريف|dist).*(?:(?:ال)?تجميع|acc)/i, ["acc_score", "dist_score", "quantity"]],
        [/تجميع/i,["acc_score"]], [/(?:درجة|مؤشر|تقييم).*توزيع|تصريف|distribution.*score/i,["dist_score"]],
        [/أيام.*تجميع|يوم.*تجميع|consecutive.*acc/i, ["quantity"]],
        [/أيام.*توزيع|يوم.*توزيع|consecutive.*dist/i, ["quantity"]],
        [/متوسط.*شراء|سعر.*(?:شراء|دخول)|الدخول/i,["entry_price"]], [/وقف/i,["stop_loss"]], [/هدف|مستهدف/i,["target_price"]], [/مسافة.*دعم|بعد.*دعم|القرب.*دعم/i,["distance_from_support_pct"]], [/دعم/i,["support"]], [/مسافة.*مقاوم|بعد.*مقاوم|القرب.*مقاوم/i,["distance_from_resistance_pct"]], [/مقاوم/i,["resistance"]],
        [/توزيعات\s*(?:نقدية)?|cash dividends/i,["cash_dividends"]], [/تكلف/i,["cost_basis"]], [/توزيع|وزن|نسبة.*المحفظة|تركيز.*قطاع/i,["position_pct"]], [/مبلغ.*مخصص|قيمة.*مخصصة|رأس.*مال.*موزع/i,["value"]], [/قيمة.*(?:سوق|مركز)|القيمة السوقية/i,["market_value"]], [/ربح|خسار|عائد|النسبة/i,["profit_pct","profit_value","backtest_return_pct"]],
        [/خسارة.*افتراضية|خسارة.*سيناريو|هبوط.*مفترض/i,["scenario_loss_amount","scenario_loss_pct"]], [/رأس.*مال|إجمالي.*رأس المال/i,["scenario_capital"]],
        [/تغير|التغيّر/i,["change_pct"]], [/فارق|الفارق/i,["change_pct","price","close"]], [/كمية|الكمية|عدد|مراكز/i,["quantity"]], [/إغلاق|اغلاق|إقفال|اقفال|السعر|سعر|price|close/i,["price","close"]],
    ];
    return labels.find(([pattern]) => pattern.test(text))?.[1];
}

/** Bind backtest claims to the selected strategy as well as the stock. */
function checkStrategyClaims(reply: string, evidence: AgenticEvidence[]): string[] {
    const reasons: string[] = [];
    const latest = new Map<string, any>();
    for (const e of evidence.filter(e => e.availability !== "error")) for (const row of evidenceRows(e.data)) for (const m of row.strategy_metrics || []) latest.set(`${row.symbol}:${m.strategy_id}`, { ...m, symbol: row.symbol });
    const rows = [...latest.values()];
    const labels: Array<[RegExp, string]> = BACKTEST_METRICS.map(({pattern,key}) => [pattern,key]);
    const matchesMetric = (val: number, expected: unknown, rawStr: string) =>
        typeof expected === "number" && Math.abs(val - expected) <= Math.max(0.5 * 10 ** -(rawStr.split(".")[1]?.length || 0), Math.abs(expected) * 0.005);
    let headers: string[] = [], owner: any = null, stockOwner: string | null = null;
    for (const rawLine of reply.split("\n")) {
        const line = normalizeEvidenceNumbers(rawLine);
        const stockNames = [...new Set(rows.map(r => r.symbol))].filter(s => line.includes(s));
        if (stockNames.length === 1) stockOwner = stockNames[0];
        const selected = rows.filter((r: any) => (!stockOwner || r.symbol === stockOwner) && (line.includes(r.strategy_id) || line.includes(r.strategy_name) || (r.strategy_id === "trend_macd" && /استراتيجية\s+الاتجاه/.test(line))));
        if (selected.length === 1) owner = selected[0];
        if (line.trim().startsWith("|")) {
            if (/^\|[\s\-:|]+\|$/.test(line.trim())) continue;
            const cells = line.split("|").slice(1, -1);
            if (!selected.length && cells.some(c => /استراتيجية|strategy/i.test(c))) { headers = cells; continue; }
            if (selected.length !== 1) continue;
            cells.forEach((cell, i) => {
                const key = labels.find(([pattern]) => pattern.test(headers[i] || ""))?.[1];
                if (!key) return;
                const cleanStr = cleanCellText(cell).replace(/[%٪]/g, "").trim();
                const n = Number(cleanStr);
                if (!Number.isFinite(n) || !/\d/.test(cell)) return;
                const cmpVal = key === "maxDrawdownPct" ? Math.abs(n) : n;
                const expected = selected[0][key];
                if (!matchesMetric(cmpVal, expected, String(n))) reasons.push(`strategy_metric_mismatch:${selected[0].symbol}:${selected[0].strategy_id}:${key}`);
            });
        } else if (owner && selected.length <= 1) {
            const peerRows = rows.filter((r: any) => r.symbol === owner.symbol);
            for (const match of line.matchAll(/[-+]?\d+(?:\.\d+)?\s*(?:%|٪|جنيه)/g)) {
                // Full-line lookahead preserves peak-to-trough qualifiers after the
                // number; only labels preceding this value may own it.
                const candidates = labels.flatMap(([pattern, key]) => { const found = [...line.matchAll(new RegExp(pattern.source, pattern.flags + "g"))].filter(label => label.index! < match.index!).at(-1); return found ? [{ key, index: found.index! }] : []; }).sort((a, b) => b.index - a.index);
                if (!candidates.length) continue;
                const key = candidates[0].key, rawNum = match[0].replace(/[%٪\s]|جنيه/g, ""), n = Number(rawNum), expected = owner[key];
                if (["closedTrades", "profitFactor"].includes(key) && /[%٪]/.test(match[0])) continue;
                const cmpVal = key === "maxDrawdownPct" ? Math.abs(n) : n;
                if (matchesMetric(cmpVal, expected, String(n))) continue;
                const contextWindow = line.slice(Math.max(0, candidates[0].index - 40), Math.min(line.length, match.index! + match[0].length + 45));
                const isComparative = peerRows.length > 1 && /مقابل|مقارن|أقل\s+من|أعلى\s+من|بينما|في\s+حين|تليها|ثم|عن\s+|في\s+استراتيجية/.test(contextWindow);
                if (isComparative && peerRows.some((r: any) => matchesMetric(cmpVal, r[key], String(n)))) continue;
                reasons.push(`strategy_metric_mismatch:${owner.symbol}:${owner.strategy_id}:${key}`);
            }
        }
    }
    return reasons;
}

function normalizeDigitsAndNumberFormatting(value: string): string {
    return value.replace(/[٠-٩]/g, d => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
        .replace(/[۰-۹]/g, d => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).replace(/٫/g, ".").replace(/,/g, ".");
}

/** Bind allocations to one scenario row, never to an arbitrary sum of stock facts. */
function scenarioTableRow(evidence: AgenticEvidence[], cells: string[], symbols: string[], headers: string[]) {
    const scenario = [...evidence].reverse().find(e => e.tool === "analyze_portfolio_risk"
        && e.availability !== "error" && e.data?.status === "success" && e.data?.mode === "scenario");
    if (!scenario) return null;
    const clean = (text: string) => text.replace(/[*_`]/g, "").trim().toLowerCase();
    if (symbols.length === 0 && headers.some(h => /خسار|loss|متبقي|متبقية|بعد (?:الهبوط|الانخفاض|التراجع)|remaining|after.*drop/i.test(h)) && headers.some(h => /هبوط|انخفاض|تراجع|drop|السيناريو|scenario/i.test(h))) {
        const declineIndex = headers.findIndex(h => /هبوط|انخفاض|تراجع|drop|السيناريو|scenario/i.test(h) && !/متبقي|متبقية|بعد (?:الهبوط|الانخفاض|التراجع)|remaining|after.*drop/i.test(h));
        if (declineIndex < 0) return null;
        const decline = Number(cleanCellText(cells[declineIndex] || "").replace(/[%٪\s]/g, ""));
        const stress = scenario.data.stress_scenarios_not_forecasts?.find((row: any) => Math.abs(row.change_pct) === Math.abs(decline));
        if (stress) return { symbol: "PORTFOLIO", scenario_loss_pct: stress.change_pct, scenario_loss_amount: -stress.loss, allocated_capital: scenario.data.capital - stress.loss };
    }
    if (!symbols.length && cells.some(cell => /^(?:الإجمالي|إجمالي|المجموع|مجموع|total)$/i.test(clean(cell))))
        return { symbol: "PORTFOLIO", allocation_pct: 100, allocated_capital: scenario.data.capital };
    const groupTable = headers.some(h => /قطاع|صناع|sector|industry/i.test(h));
    const groups = [...(scenario.data.sector_exposure || []), ...(scenario.data.industry_exposure || [])];
    if (groupTable) {
        const exactMembers = (members: string[]) => symbols.length === members.length
            && symbols.every(s => members.includes(s));
        return groups.find(row => {
            const label = row.industry ?? row.sector;
            const labelMatches = typeof label === "string" && cells.some(cell => clean(cell) === clean(label));
            // A sector label cannot turn a subset or a different set of stocks into its total.
            return symbols.length ? Array.isArray(row.symbols) && exactMembers(row.symbols) : labelMatches;
        }) || (symbols.length === 1 ? scenario.data.stocks?.find((row: any) => row.symbol === symbols[0]) : null);
    }
    if ((!symbols.length || symbols.every(symbol => symbol === "PORTFOLIO")) && cells.some(cell => /^(?:الإجمالي|إجمالي|المجموع|مجموع|total)$/i.test(clean(cell))))
        return { symbol: "PORTFOLIO", allocation_pct: 100, allocated_capital: scenario.data.capital };
    const allocationTable = headers.some(h => /توزيع|وزن|مبلغ|قيمة.*مخصص|allocation|weight|amount/i.test(h)
        || /^(?:النسبة|نسبة|النسبة %|نسبة %)$/i.test(clean(h)));
    if (allocationTable && symbols.length === 1) return scenario.data.stocks?.find((row: any) => row.symbol === symbols[0]) || null;
    return null;
}

function scenarioMetricFields(label: string): FactRecord["field"][] | undefined {
    if (/متبقي|متبقية|بعد (?:الهبوط|الانخفاض|التراجع)|remaining|after.*drop/i.test(label)) return ["value"];
    if (/هبوط|انخفاض|تراجع|drop|السيناريو|scenario/i.test(label)) return ["scenario_loss_pct"];
    if (/خسار|loss/i.test(label)) return /%|٪|نسب|percent|pct/i.test(label) ? ["scenario_loss_pct"] : ["scenario_loss_amount"];
    if (/توزيع|وزن|تخصيص|خصيص|نسب|تركيز|allocation|weight/i.test(label)) return ["position_pct"];
    // A percentage tied to capital/allocation is a share of the portfolio, not a
    // currency amount: "من رأس المال %" must not fall through to the amount rule.
    if (/%|٪/.test(label) && /رأس|مال|capital|تخصيص|خصيص|توزيع|وزن|تركيز/i.test(label)) return ["position_pct"];
    if (/مبلغ|قيمة|رأس.*مال|جنيه|capital|amount/i.test(label)) return ["value"];
    return tableMetricFields(label);
}

function checkResistanceRelations(reply: string, evidence: AgenticEvidence[]): string[] {
    const rows = new Map<string, any>();
    for (const e of evidence) if (e.availability !== "error") for (const row of evidenceRows(e.data))
        if (row.symbol && Number.isFinite(row.close) && Number.isFinite(row.resistance)) rows.set(row.symbol, row);
    const reasons: string[] = [];
    for (const sentence of reply.replace(/[*_`]/g, "").split(/\n|[.!؟]\s+/)) {
        if (sentence.trim().startsWith("|") || /إذا|اذا|(?:^|\s)لو(?:\s|$)|عند اختراق|شرط|يتطلب|يحتاج/.test(sentence)) continue;
        for (const [symbol, row] of rows) {
            if (!new RegExp(`\\b${symbol}\\b`, "i").test(sentence)) continue;
            for (const relation of sentence.matchAll(/(تحت|أدنى من|ادنى من|أسفل|اسفل|فوق|أعلى من|اعلى من|عند|اخترق(?:ت|ا|وا)?)\s*(?:الـ\s*)?(المقاومة|مقاومتها|مقاومته|تحتها|فوقها)|(تحتها|فوقها)(?=\s|[.,،؛!?؟]|$)/g)) {
                const prefix = sentence.slice(0, relation.index);
                if (/(?:ليس|ليست|ليسا|لم|لن|مش|لا|غير|لم يكن|لم تكن)\s*$/.test(prefix)) continue;
                const term = relation[1] || relation[3];
                const tolerance = Math.max(1e-9, Math.abs(row.resistance) * 1e-9);
                const delta = row.close - row.resistance;
                const valid = /تحت|أدنى|ادنى|أسفل|اسفل/.test(term) ? delta < -tolerance
                    : term === "عند" ? Math.abs(delta) <= tolerance : delta > tolerance;
                if (!valid) reasons.push(`price_resistance_relation_contradiction:${symbol}`);
            }
        }
    }
    return [...new Set(reasons)];
}

/** A prose claim belongs to its own clause, never the last row of a preceding table. */
function interpretationSubject(text: string, claimIndex: number, symbols: string[], inherited: string | null): string | null {
    const before = text.slice(0, claimIndex).split(/[،؛]/).at(-1) || "";
    const after = text.slice(claimIndex).split(/[،؛]/)[0];
    const namesIn = (value: string) => symbols.filter(symbol => new RegExp(`\\b${symbol}\\b`, "i").test(value));
    const clause = before + after;
    // A blanket clause ("both are closer to oversold") is not a single-stock
    // ranking claim; leave it to the contextual reviewer instead of binding it
    // to the sentence's leading ticker.
    if (/كلاهما|كلا\s+السهمين|الاثنان|الاثنين|both|جميع|الجميع/i.test(clause)) return null;
    const local = namesIn(clause);
    if (local.length === 1) return local[0];
    // Ambiguous multi-stock clauses are left to the contextual reviewer.
    return local.length === 0 && namesIn(text).length <= 1 ? inherited : null;
}

/** Verify interpretations as relations, not just the presence of their individual numbers. */
function checkSnapshotInterpretations(reply: string, evidence: AgenticEvidence[]): string[] {
    const allRows = evidence.filter(e => e.availability !== "error").flatMap(e => evidenceRows(e.data));
    // A follow-up can carry an older snapshot alongside a refreshed comparison.
    // Rank only one dated row per symbol: newest date wins, and the later evidence
    // wins ties (the current comparison is appended after session memory).
    const latestBySymbol = new Map<string, any>();
    for (const row of allRows) {
        if (!row.symbol) continue;
        const prior = latestBySymbol.get(row.symbol);
        const date = String(row.date || row.current_date || row.as_of || "").slice(0, 10);
        const priorDate = String(prior?.date || prior?.current_date || prior?.as_of || "").slice(0, 10);
        if (!prior || date >= priorDate) latestBySymbol.set(row.symbol, row);
    }
    const currentRows = [...latestBySymbol.values()];
    // Preserve the full series below; only ranking checks use the current snapshot.
    const rows = allRows;
    const symbols = [...new Set<string>(currentRows.map(r => r.symbol).filter(Boolean))];
    let owner: string | null = symbols.length === 1 ? symbols[0] : null;
    const reasons: string[] = [];
    for (const raw of reply.replace(/[*_`]/g, "").split(/\n|[.!؟؛]\s+/)) {
        const named = symbols.filter(symbol => new RegExp(`\\b${symbol}\\b`, "i").test(raw));
        if (named.length === 1) owner = named[0];
        else if (named.length > 1) owner = null;
        const proximity = /(?:الأقرب|أقرب).{0,30}(?:للتشبع\s+البيعي|(?:من|إلى|الى)\s+(?:منطقة\s+)?التشبع\s+البيعي)/.exec(raw)
            || /(?:الأقرب|أقرب).{0,20}(?:حد\s*(?:RSI\s*)?30|RSI\s*30)|30.{0,15}(?:الأقرب|أقرب)/i.exec(raw);
        const proximityOwner = proximity ? interpretationSubject(raw, proximity.index, symbols, owner) : null;
        if (proximityOwner) {
            const current = currentRows.find(row => row.symbol === proximityOwner && Number.isFinite(row.rsi_14));
            const peers = current ? currentRows.filter(row => row.date === current.date && Number.isFinite(row.rsi_14)) : [];
            // “Closer to the oversold zone” means lower RSI. Only an explicit
            // distance-to-30 claim is a geometric proximity comparison.
            const explicitThresholdDistance = /(?:المسافة|أقرب|أقربها).{0,20}(?:إلى|ل|من)?\s*(?:حد\s*)?30|30.{0,15}(?:أقرب|المسافة)/.test(raw);
            if (current && peers.some(row => row.symbol !== proximityOwner && (explicitThresholdDistance
                ? Math.abs(row.rsi_14 - 30) < Math.abs(current.rsi_14 - 30) - 1e-6
                : row.rsi_14 < current.rsi_14 - 1e-6)))
                reasons.push(`rsi_oversold_proximity_ranking_contradiction:${proximityOwner}`);
        }
        const minimum = /(?:الأدنى|أدنى|الأقل|أقل)\s+(?:في\s+)?RSI.{0,30}بين\s+(?:الثلاثة|الأسهم|الاسهم)/i.exec(raw);
        const minimumOwner = minimum ? interpretationSubject(raw, minimum.index, symbols, owner) : null;
        if (minimumOwner) {
            const current = currentRows.find(row => row.symbol === minimumOwner && Number.isFinite(row.rsi_14));
            if (current && currentRows.some(row => row.date === current.date && row.symbol !== minimumOwner && Number.isFinite(row.rsi_14) && row.rsi_14 < current.rsi_14-1e-6))
                reasons.push(`rsi_minimum_ranking_contradiction:${minimumOwner}`);
        }
        const easing = /(?:تخفيف|انحسار|تراجع)\s+ضغط\s+البيع|ضغط\s+البيع\s+(?:يخف|يقل|يتراجع|يتباطأ)/.exec(raw);
        if (easing && /RSI|مؤشر\s+القوة\s+النسبية/i.test(raw)) {
            const prefix = raw.slice(Math.max(0, easing.index - 45), easing.index);
            const blanket = /كلا\s+السهمين|كلاهما|السهمان|السهمين|both/i.test(raw);
            const targets = named.length ? named : blanket ? symbols : owner ? [owner] : [];
            const claimPrefix = prefix.split(/[،؛]|لكن|بل/).at(-1) || "";
            if (!/لا\s+(?:يثبت|تثبت|يعني|تعني|يكفي|تكفي|يمكن|يدل|تدل)|(?:ليس|غير|لا)\s*$/.test(claimPrefix)) {
                for (const symbol of targets) {
                    const dates = new Set(rows.filter(r => r.symbol === symbol && Number.isFinite(r.rsi_14)
                        && /^\d{4}-\d{2}-\d{2}/.test(r.date || "")).map(r => r.date.slice(0, 10)));
                    if (dates.size < 2) reasons.push(`rsi_snapshot_does_not_prove_trend:${symbol}`);
                }
            }
            continue;
        }
        if (!owner || named.length > 1 || raw.trim().startsWith("|") || /إذا|اذا|(?:^|\s)لو(?:\s|$)/.test(raw)) continue;
        const stockRows = rows.filter(r => r.symbol === owner);
        const levels = [...stockRows].reverse().find(r => Number.isFinite(r.close) && r.close > 0 && Number.isFinite(r.support) && Number.isFinite(r.resistance));
        if (levels) for (const match of raw.matchAll(/(دعم|مقاوم[ةه]).{0,70}?(أكبر|أقل|أبعد|أقرب).{0,60}?(دعم|مقاوم[ةه])/g)) {
            const beforeRelation = raw.slice(0, match.index! + match[0].indexOf(match[2]));
            if (match[1] === match[3] || /(?:ليس|ليست|مش|غير|لا)\s*$/.test(beforeRelation)) continue;
            if (/أكبر|أقل/.test(match[2]) && !/مساف|بعد|قرب/.test(raw)) continue;
            const distance = (label: string) => Math.abs(levels.close - levels[/دعم/.test(label) ? "support" : "resistance"]) / levels.close;
            const first = distance(match[1]), second = distance(match[3]);
            const larger = /أكبر|أبعد/.test(match[2]);
            if (larger ? first <= second + 1e-9 : first >= second - 1e-9) reasons.push(`level_distance_ranking_contradiction:${owner}`);
        }
        // A histogram sign is a relation to the signal, not proof of improvement over time.
        const temporal = raw.match(/(?:(?:الزخم\s+(يتحسن|يتعافى|يتراجع|يتدهور)|(?:تحسن|تعافي|تراجع|تباطؤ).{0,45}(?:الزخم|العلاقة\s+بين\s+MACD))|ضغط\s+البيع\s+(يتراجع|يتباطأ|يخف|يقل)|(?:يخف|يقل|يتراجع|تخفيف|تراجع|انحسار)\s+ضغط\s+البيع)/);
        if (!temporal) continue;
        const prefix = raw.slice(Math.max(0,temporal.index!-35),temporal.index);
        if (/(?:لا|ليس|مش|غير|قد|يمكن أن)\s*$|لا يثبت|لا تثبت|لا يمكن|لا يعني|لا يكفي/.test(prefix)) continue;
        const snapshots = new Map<string,number>();
        for (const row of stockRows) {
            const hist = row.macd_histogram ?? row.macd_hist;
            if (typeof hist === "number" && Number.isFinite(hist) && /^\d{4}-\d{2}-\d{2}/.test(row.date || "")) snapshots.set(row.date.slice(0,10),hist);
        }
        const ordered = [...snapshots.entries()].sort(([a],[b]) => a.localeCompare(b));
        const pressureClaim = /ضغط\s+البيع/.test(raw);
        if (ordered.length < 2) reasons.push(`temporal_momentum_without_series:${owner}`);
        else {
            const change = ordered.at(-1)![1] - ordered.at(-2)![1];
            const improving = pressureClaim
                ? /يتراجع|يتباطأ|يخف|يقل/.test(temporal[0])
                : /يتحسن|يتعافى/.test(temporal[0]);
            if (improving ? change <= 0 : change >= 0) reasons.push(`temporal_momentum_direction_contradiction:${owner}`);
        }
    }
    return [...new Set(reasons)];
}

/** Verify a stock's share of a sector against the scenario's aggregate allocation. */
function checkScenarioSectorShareClaims(reply: string, evidence: AgenticEvidence[]): string[] {
    const scenarios = evidence.filter(e => e.tool === "analyze_portfolio_risk" && e.availability !== "error"
        && e.data?.status === "success" && e.data?.mode === "scenario");
    const reasons: string[] = [];
    const shareClaims = /([-+]?\d+(?:[.,٫]\d+)?)\s*(?:%|٪|percent)\s*(?:من|of)\s*(?:(?:إجمالي|total)\s*)?(?:التعرض(?:\s+(?:للقطاع|ل\s*قطاع|للقطاع|بالقطاع|القطاع))?|(?:حصة|نسبة|وزن)\s+(?:ال)?قطاع|(?:ال)?قطاع\s+(?:التعرض|exposure)|(?:sector\s+)?exposure\s+(?:of|to)?)/gi;
    for (const sentence of reply.replace(/[*_`]/g, "").split(/\n|[.!؟؛]\s+/)) {
        if (sentence.trim().startsWith("|")) continue;
        const normalized = normalizeDigitsAndNumberFormatting(sentence);
        for (const scenario of scenarios) {
            const stocks = Array.isArray(scenario.data.stocks) ? scenario.data.stocks : [];
            const symbolMentions = stocks.flatMap((stock: any) => {
                const symbol = String(stock.symbol || "").toUpperCase();
                if (!symbol) return [];
                const pattern = new RegExp(`\\b${symbol}\\b`, "gi");
                return [...normalized.matchAll(pattern)].map(match => ({ stock, symbol, index: match.index ?? 0 }));
            }).sort((a: any, b: any) => a.index - b.index);
            for (const match of normalized.matchAll(shareClaims)) {
                const claimIndex = match.index ?? 0;
                // Bind each percentage to the nearest preceding ticker in the same
                // sentence. If the prose does not make that relationship explicit,
                // leave it to the LLM reviewer instead of cross-checking every ticker
                // against every percentage and creating false rejections.
                const mention = [...symbolMentions].reverse().find((item: any) => item.index < claimIndex
                    && claimIndex - item.index <= 80);
                if (!mention || !mention.stock.sector) continue;
                const sector = String(mention.stock.sector).toLowerCase();
                const sectorWeight = stocks.filter((row: any) => String(row.sector || "").toLowerCase() === sector)
                    .reduce((sum: number, row: any) => sum + Number(row.allocation_pct || 0), 0);
                if (!(sectorWeight > 0) || !Number.isFinite(Number(mention.stock.allocation_pct))) continue;
                const expected = Number((Number(mention.stock.allocation_pct) / sectorWeight * 100).toFixed(2));
                const actual = Number(match[1]);
                if (Math.abs(actual - expected) > 0.03)
                    reasons.push(`scenario_sector_share_mismatch:${mention.symbol}:expected_${expected}`);
            }
        }
    }
    return [...new Set(reasons)];
}

function explicitPositionInputs(request: string) {
    const normalizedRequest = normalizeDigitsAndNumberFormatting(request);
    const average = normalizedRequest.match(/(?:متوسطي|متوسط(?:ي)?(?:\s+(?:(?:ال)?شراء|سعر\s+(?:ال)?شراء))?|سعر\s+شرائي|اشتريت(?:ه)?\s+بسعر)\s*(?:(?:هو|فيه|عند)\s*)?[:=]?\s*(\d+(?:\.\d+)?)/i);
    const quantity = normalizedRequest.match(/(?:معايا|معي|عندي)\s*(\d+(?:\.\d+)?)\s*(?:سهم|أسهم|اسهم)(?=\s|$|[،,.!?])/i)
        || normalizedRequest.match(/(?:كمية(?:\s+الأسهم)?|عدد\s+الأسهم)\s*(?:هي\s*)?[:=]?\s*(\d+(?:\.\d+)?)/i);
    const totalCost = normalizedRequest.match(/(?:بتكلفة|التكلفة\s+الإجمالية|تكلفة\s+إجمالية)\s*(\d+(?:\.\d+)?)\s*(ألف|مليون)?/i);
    const multiplier = totalCost?.[2] === "مليون" ? 1_000_000 : totalCost?.[2] === "ألف" ? 1_000 : 1;
    return { average: average?.[1], quantity: quantity?.[1], totalCost: totalCost ? String(Number(totalCost[1]) * multiplier) : undefined };
}

/** Explicit position inputs in the current request are part of the answer contract. */
export function checkUserPositionInputs(reply: string, request: string): string[] {
    const normalizedReply = normalizeDigitsAndNumberFormatting(reply);
    const reasons: string[] = [];
    const { average, quantity } = explicitPositionInputs(request);
    const numbers = [...normalizedReply.matchAll(/\d+(?:\.\d+)?/g)].map(match => Number(match[0]));
    if (average && !numbers.includes(Number(average))) reasons.push(`user_position_average_omitted:${average}`);
    if (quantity && !numbers.includes(Number(quantity))) reasons.push(`user_position_quantity_omitted:${quantity}`);
    const { totalCost } = explicitPositionInputs(request);
    if (totalCost && !/الكمية\s*\(أو\s+متوسط|الكمية\s+أو\s+متوسط/.test(normalizedReply) && /(?:متوسط|سعر\s+الشراء).{0,45}(?:ابعت|أرسل|اذكر|محتاج|مطلوب|ناقص)|(?:ابعت|أرسل|اذكر).{0,45}(?:متوسط|سعر\s+الشراء)/i.test(normalizedReply))
        reasons.push("unneeded_average_requested_when_total_cost_known");
    return reasons;
}

/** This validates output evidence/protocol only. It never routes user intent. */
export function checkAgenticDraft(reply: string, evidence: AgenticEvidence[], request = "", currentEvidence?: AgenticEvidence[]): string[] {
    const reasons: string[] = [];
    // Check claims about execution, not user intent. Earlier evidence cannot prove a new fetch.
    if (currentEvidence && !currentEvidence.some(e => e.availability !== "error" && e.availability !== "missing")) {
        for (const line of reply.split(/\n/)) if (/أعدت\s+(?:قراءة|جلب|التحقق)|(?:جلبت|حدّثت)\s+(?:بيانات|اتساع|سعر)|(?:راجعت|تأكدت)\s+من\s+(?:البيانات|المصدر)/.test(line)
            && !/لم\s+|دون\s+جلب|بدون\s+جلب|السابقة|السابق/.test(line)) reasons.push("claimed_refresh_without_current_tool");
    }
    const corporateReadClaim = /(?:فحصت|راجعت|تحق[ّ]?قت|بحثت|استعلمت).{0,45}(?:السجل|الإجراءات|التوزيعات)/.test(reply)
        && /إجراءات\s*رأسمالية|الإجراءات\s*الرأسمالية|سجل\s*(?:الأحداث|التوزيعات)/.test(reply);
    if (corporateReadClaim && !(currentEvidence || evidence).some(e => e.tool === "get_corporate_actions" && e.availability !== "error"))
        reasons.push("corporate_action_read_claim_without_tool");
    if (!reply.trim()) reasons.push("empty_response");
    if (/\b(?:get_corporate_actions|get_live_quote|get_fundamentals|get_sector_peers|get_market_breadth|get_stock(?:_levels)?|get_market|get_comparison|get_news|get_recommendations|get_technical_scan|get_accumulation_stocks|calculate_position|manage_portfolio|screen_stocks|analyze_portfolio_risk|list_chart_strategies|apply_chart_strategy|compare_strategies_history|enable_autonomous_recommendations|disable_autonomous_recommendations|stock_prices|stock_technical_indicators|stock_scans_summary|ai_chat_sessions|ai_chat_messages|resistance_relation|date_kind|event_date|record_date|final_close_confirmed|session_complete|price_type|live_quote_available|corporate_actions_adjusted)\b/.test(reply)) reasons.push("internal_implementation_names_in_response");
    const substantive = reply.replace(/\[[^\]]*\]\(https?:\/\/[^)]*\)/g, "").replace(/https?:\/\/\S+/g, "")
        .replace(/✅ تحليل EGX Bots[^\n]*/g, "").replace(/📢[^\n]*/g, "");
    if (!/[\p{L}]{2}/u.test(substantive)) reasons.push("response_has_no_substantive_answer");
    const deadEndOnly = substantive.replace(/[\s.!؟،,:;؛*_`-]+/g, " ").trim();
    if (/^(?:غير مكتمل|مسودة ناقصة|رد بعيد عن السؤال|تعذر التحليل|لم ينجز الطلب|الرد ناقص|الرد غير مكتمل|الإجابة غير مكتملة|المسودة ناقصة|لم أتمكن من إكمال الإجابة|تعذر إكمال الإجابة|لم تكتمل الإجابة|لا أستطيع رؤية الصورة المرفقة)$/.test(deadEndOnly)
        || /لم يكتمل التحقق من إجابة موثوقة/.test(substantive)) reasons.push("response_has_no_substantive_answer");
    const quoteTimes = (currentEvidence || evidence)
        .flatMap(e=>evidenceRows(e.data)).filter(r=>r.live_quote_available && r.fetched_at)
        .map(r=>new Date(r.fetched_at)).filter(d=>Number.isFinite(d.getTime()))
        .map(d=>new Intl.DateTimeFormat("en-GB",{timeZone:"Africa/Cairo",hour:"2-digit",minute:"2-digit",hour12:false}).format(d));
    if (quoteTimes.length) for (const raw of reply.split("\n")) {
        if (!/جلب|retriev|fetch/i.test(raw)) continue;
        const line=normalizeEvidenceNumbers(raw);
        const clocks=[...line.matchAll(/(\d{1,2}):(\d{2})(?::\d{2})?\s*(ص|م)?\s*(?:بتوقيت|بالتوقيت|توقيت)?\s*(?:القاهرة|Cairo)/gi),
            ...line.matchAll(/(?:القاهرة|Cairo)\s*[:：،,)]?\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*(ص|م)?/gi)];
        for (const clock of clocks) {
            let hour=Number(clock[1]);if(clock[3])hour=hour%12+(clock[3]==="م"?12:0);
            const value=String(hour).padStart(2,"0")+":"+clock[2];
            if(!quoteTimes.includes(value))reasons.push("quote_fetch_time_cairo_mismatch");
        }
    }
    if (/DSML|<\/?tool_call|<\/?function_call/i.test(reply)) reasons.push("internal_tool_protocol_in_response");
    evidence = evidence.map(compactEvidence);
    const facts = agenticFacts(evidence);
    const unsupportedVolumeRank = reply.split(/[\n.!؟]/).some(clause =>
        /(?:الأعلى\s+حجم|اعلى\s+حجم|أعلى\s+حجم\s+تداول|الأكثر\s+تداول)/.test(clause)
        && !/(?:لا\s|ليس|لم\s|غير\s|نسبي)/.test(clause));
    if (unsupportedVolumeRank && !facts.some(f => f.field === "volume")) reasons.push("volume_ranking_without_volume_evidence");
    const officialCapitalEvent = evidence.filter(e => e.tool === "get_corporate_actions" && e.availability !== "error")
        .flatMap(e => evidenceRows(e.data)).flatMap(row => row.events || [])
        .some(event => event.official_source === true && event.action_date && ["stock_split","bonus_shares","rights_issue","capital_increase","capital_reduction"].includes(event.action_type));
    if (!officialCapitalEvent && reply.split(/[\n.]/).some(clause =>
        /(?:قد\s+(?:يعكس|تعكس)|غالب[اًا]*|يرج[ّ]?ح|ناتج|بسبب|يفسر|تفسر).{0,100}(?:تجزئة|زيادة\s*رأس|حدث.{0,20}رأس|تعديل.{0,15}رأس)/.test(clause)
        && !/لا\s+(?:يثبت|تثبت|يرج[ّ]?ح|يمكن)|لم\s+(?:يثبت|يتأكد)/.test(clause))) reasons.push("capital_action_cause_without_official_event");
    const inputs = explicitPositionInputs(request);
    const requestSymbols = [...new Set((request.match(/\b[A-Z]{2,6}\b/g) || []).filter(symbol => symbol !== "RSI"))];
    const positionSymbol = requestSymbols.length === 1 ? requestSymbols[0] : null;
    if (positionSymbol && inputs.totalCost) facts.push({id:`${positionSymbol}:user_cost`,symbol:positionSymbol,
        field:"cost_basis",value:Number(inputs.totalCost),unit:"egp",as_of:null,source:"user_request",tool:"user_input",fetched_at:new Date().toISOString()});
    reasons.push(...checkResistanceRelations(reply, evidence));
    reasons.push(...checkSnapshotInterpretations(reply, evidence));
    reasons.push(...checkScenarioSectorShareClaims(reply, evidence));
    reasons.push(...checkStrategyClaims(reply, evidence));
    for (const line of reply.replace(/[*_`]/g, "").split(/\n|[.!؟؛]\s+|(?:\s*[،,]\s*(?:بينما|في\s+حين|أما|مقابل|على\s+عكس)\s+)|\s+(?:بينما|في\s+حين)\s+/)) {
        if (!/نشاط|حجم\s+نسبي/.test(line) || !/أقل\s+من\s+متوسط|دون\s+المتوسط|أعلى\s+من\s+متوسط/.test(line)) continue;
        const names = evidence.flatMap(e => e.symbols).filter(symbol => new RegExp(`\\b${symbol}\\b`, "i").test(line));
        const blanket = /كل|كلا|الثلاثة|الجميع/.test(line);
        const hasBelow = /أقل\s+من\s+متوسط|دون\s+المتوسط/.test(line);
        const hasAbove = /أعلى\s+من\s+متوسط/.test(line);
        for (const row of evidence.flatMap(e => evidenceRows(e.data))) {
            const volume = row.r_vol ?? row.relative_volume ?? row.vol_ratio;
            if (!Number.isFinite(volume) || (!names.includes(row.symbol) && !blanket)) continue;
            let below = hasBelow;
            if (hasBelow && hasAbove && names.length > 1) {
                const symMatch = new RegExp(`\\b${row.symbol}\\b`, "i").exec(line);
                if (symMatch) {
                    const tail = line.slice(symMatch.index);
                    const bIdx = tail.search(/أقل\s+من\s+متوسط|دون\s+المتوسط/);
                    const aIdx = tail.search(/أعلى\s+من\s+متوسط/);
                    if (bIdx >= 0 && aIdx >= 0) below = bIdx < aIdx;
                    else if (aIdx >= 0) below = false;
                }
            }
            if (below ? volume >= 1 : volume <= 1) reasons.push(`relative_volume_baseline_contradiction:${row.symbol}`);
        }
    }
    if (inputs.totalCost && !inputs.quantity && !inputs.average && /(?:التكلفة|تكلفة).{0,100}(?:تعني\s+كمية|تحدد\s+كمية|أقل\s+من\s+\d+\s+سهم)/.test(reply.replace(/\n/g," ")))
        reasons.push("historical_cost_does_not_determine_quantity_at_current_close");
    const newsRows = evidence.filter(e => e.tool === "get_news" && e.availability !== "error")
        .flatMap(e => evidenceRows(e.data));
    if (newsRows.some(r => r.date_kind === "aggregation") && !newsRows.some(r => r.event_date || r.published_at || r.publication_date)) {
        for (const line of reply.replace(/[*_`]/g, "").split(/\n|[.!؟؛]\s+/)) {
            if (/(?:أحدث\s+خبر|الأحدث\s+فعلي[ًاا]*|تاريخ\s+(?:النشر|نشره)|يوم\s+صدور|نُشر|خبر.{0,30}بتاريخ).{0,140}\b20\d{2}-\d{2}-\d{2}\b/.test(line)
                && !/رصد|سجل|تجميع|غير موثق|غير متحقق|لا يثبت|لا يمكن/.test(line))
                reasons.push("news_record_date_is_not_publication_date");
        }
    }
    const screen = evidence.filter(e => e.tool === "screen_stocks" && e.data?.status === "success").at(-1);
    const methodology = String(screen?.data?.methodology || "");
    const numerator = "\\(\\s*(?:المقاومة|resistance)\\s*[-−]\\s*(?:الإغلاق|close)\\s*\\)\\s*[÷/]\\s*";
    for (const line of reply.replace(/[*_`]/g, "").split("\n")) {
        // Bind each symbolic formula to its own denominator label; a reply may
        // compare both formulas without changing the screen's methodology.
        const defaultDenominator = methodology.includes("distance=(resistance-close)/close*100") ? "close"
            : methodology.includes("distance=(resistance-close)/resistance*100") ? "resistance" : null;
        if (!defaultDenominator) continue;
        for (const formula of line.matchAll(new RegExp(numerator + "(الإغلاق|close|المقاومة|resistance)", "gi"))) {
            const labels = [...line.slice(0,formula.index).matchAll(/(?:القسمة|النسبة|المسافة).{0,20}على\s+(?:أساس\s+)?(الإغلاق|المقاومة)/g)];
            const label = labels.at(-1)?.[1];
            const expected = label ? label === "الإغلاق" ? "close" : "resistance" : defaultDenominator;
            const actual = /الإغلاق|close/i.test(formula[1]) ? "close" : "resistance";
            if (actual !== expected) reasons.push("screen_distance_formula_contradiction");
        }
    }
    if (screen) {
        for (const line of reply.replace(/[*_`]/g, "").split(/\n|[.!؟؛]\s+/)) {
            if (/^(?:هل|\*?هل)\s/.test(line.trim()) || line.trim().endsWith("؟")) continue;
            const positiveRows = evidenceRows(screen.data).filter(row => Number.isFinite(row.close) && row.close > 0 && row.resistance >= row.close);
            const reversal = /(?:ينقلب|يتغير|يختلف|تنقلب|قد\s+يظهر\s+اختلاف).{0,30}(?:ترتيب|ترتيبهما)|(?:ترتيب|ترتيبهما).{0,30}(?:ينقلب|يتغير|يختلف|تنقلب)/.exec(line);
            if (positiveRows.length >= 2 && reversal && !/(?:لا|لن|ليس|مش|غير)\s*$/.test(line.slice(0,reversal.index)) && !/(?:ترتيب|ترتيبهما)[\s:：،-]+(?:لا|لن)\s+(?:ينقلب|يتغير|يختلف)/.test(reversal[0]))
                reasons.push("screen_distance_order_monotonicity_contradiction");
            const equality = /(?:متطابق(?:ة|تان|تين|ان)?|متساوي(?:ة|تان|تين|ان)?|نفس\s+(?:النسبة|النسب|القيمة|القيم))/.exec(line);
            if (/ترتيب|الترتيب|ranking|order/i.test(line) && !/النسب|النسبة|القيم|القيمة|percent|value/i.test(line)) continue;
            if (!equality || !/الإغلاق|الاغلاق|close/i.test(line) || !/المقاومة|resistance/i.test(line)) continue;
            if (/(?:ليس|ليست|ليسا|مش|غير|لا)\s*$/.test(line.slice(0, equality.index))) continue;
            const unequal = evidenceRows(screen.data).some(row => Number.isFinite(row.close) && row.close > 0
                && Number.isFinite(row.resistance) && row.resistance > 0 && Math.abs(row.resistance - row.close) > 1e-9);
            if (unequal) reasons.push("screen_distance_denominators_not_equivalent");
        }
    }
    reasons.push(...checkAttribution(reply, facts));
    if (request) reasons.push(...checkUserPositionInputs(reply, request));
    const supplied = explicitPositionInputs(request);
    for (const e of evidence.filter(e => e.tool === "calculate_position" && e.availability !== "error")) {
        for (const r of evidenceRows(e.data)) {
            if (supplied.quantity && r.quantity !== Number(supplied.quantity)) reasons.push("position_quantity_differs_from_request");
            if (supplied.average && r.entry_price !== Number(supplied.average)) reasons.push("position_average_differs_from_request");
        }
    }
    if (request && /(?:أخبار|اخبار|خبر|news)/i.test(request)) {
        const requestedNewsSymbols = [...new Set(evidence.filter(e=>e.tool === "get_news" && e.availability !== "error")
            .flatMap(e=>Array.isArray(e.arguments?.symbols) ? e.arguments.symbols : []).map((s:any)=>String(s).toUpperCase()))];
        const plain = reply.replace(/[*_`]/g, "");
        const heading = /(?:^|\n)\s*(?:#{1,6}\s*)?(?:أحدث\s+(?:الأخبار?|خبر\s+متاح)|الأخبار?|خبر\s+متاح|news)\s*[:：]?/im.exec(plain);
        const newsText = heading
            ? plain.slice(heading.index + heading[0].length).split(/\n\s*(?:#{1,6}\s+|(?:السعر اللحظي|الخلاصة|المتاح وغير المتاح)\s*[:：]?)/i)[0]
            : plain;
        for (const symbol of requestedNewsSymbols) {
            const hasSymbol = new RegExp(`(?<![A-Z0-9])${symbol}(?![A-Z0-9])`, "i").test(newsText);
            const hasNoNewsClaim = /(?:لا\s+توجد|غياب|عدم\s+وجود|دون|مفيش)\s+(?:أخبار|اخبار|إفصاحات|افصاحات|بيانات\s+إخبارية)/i.test(plain) || /(?:أخبار|اخبار).{0,35}(?:غير\s+متاح|مفقود|لا\s+تتوفر|لم\s+تسجل|فارغ)/i.test(plain);
            const emptyForSymbol = evidence.filter(e => e.tool === "get_news" && e.availability !== "error" && e.arguments?.symbols?.includes(symbol))
                .every(e => Array.isArray(e.data?.news) && !e.data.news.some((n: any) => n.symbol === symbol));
            const supportedSingleEmpty = requestedNewsSymbols.length === 1 && hasNoNewsClaim && emptyForSymbol;
            if (!hasSymbol && !supportedSingleEmpty) reasons.push(`requested_news_symbol_omitted:${symbol}`);
        }
    }
    // Verify comparative distance statements from the same dated comparison,
    // independently of whether all quoted values themselves are grounded.
    const latestComparisons=new Map<string,AgenticEvidence>();
    for (const e of evidence.filter(e=>e.tool === "get_comparison" && e.availability !== "error"))
        latestComparisons.set(evidenceRows(e.data).map(r=>r.symbol).filter(Boolean).sort().join("/"),e);
    for (const e of latestComparisons.values()) {
        const quotes=evidenceRows(e.data).filter(r=>r.symbol && r.close != null);
        if (quotes.length < 2) continue;
        const dates=quotes.map(r=>String(r.date || r.as_of || e.data_time || "").slice(0,10));
        if (!dates[0] || dates.some(d=>d !== dates[0])) continue;
        for (const raw of reply.split(/\n|(?<=[.!؟])\s+/)) {
            const line=raw.replace(/[*_`]/g, "");
            // Plural claims apply to every stock in the comparison, even when
            // the sentence omits tickers (for example, "both are below EMA50").
            const blanket = /(?:الاثنان|الاثنين|كلاهما|كلا السهمين|both|all\s+(?:stocks|shares))/i.test(line);
            const blanketRelation = line.match(/(?<!ال)(فوق|أعلى من|اعلى من|تحت|أسفل|اسفل|above|below)\s*(?:الـ\s*)?EMA\s*(50|200)/i);
            const beforeRelation = line.slice(Math.max(0, blanketRelation ? blanketRelation.index! - 35 : 0), blanketRelation?.index || 0);
            const hypotheticalOrNegated = /إذا|اذا|لو|أمس|امس|سابق|\bif\b/i.test(beforeRelation)
                || /(?:ليس|مش|غير|(?:^|\s)لا(?:\s|$))\s*(?:كان|يكون|هو|were|was|is|are)?\s*$/i.test(beforeRelation.slice(-18));
            if (blanket && blanketRelation && !hypotheticalOrNegated) {
                const above = /فوق|أعلى|اعلى|above/i.test(blanketRelation[1]);
                const namedInSentence = quotes.filter(r => new RegExp(`\\b${r.symbol}\\b`, "i").test(line));
                for (const row of (namedInSentence.length ? namedInSentence : quotes)) {
                    const close = Number(row.close), average = Number(row[`ema_${blanketRelation[2]}`]);
                    if (!Number.isFinite(close) || !Number.isFinite(average)) continue;
                    if ((above && close <= average) || (!above && close >= average))
                        reasons.push(`price_average_relation_contradiction:${row.symbol}:ema_${blanketRelation[2]}`);
                }
            }
            const named=quotes.filter(r=>new RegExp(`\\b${r.symbol}\\b`,"i").test(line));
            if (named.length !== 1 || /إذا|اذا|لو|أمس|امس|سابق/.test(line)) continue;
            const periods=[...line.matchAll(/EMA\s*(50|200)/gi)].map(m=>m[1]);
            if (new Set(periods).size !== 1) continue;
            const relation=line.match(/أقرب|اقرب|أبعد|ابعد/);
            if (!relation || /(?:ليس|مش|غير)\s*$/.test(line.slice(0,relation.index)) || /RSI|التشبع\s+البيعي/.test(line)) continue;
            const field=`ema_${periods[0]}`;
            const distances=quotes.map(r=>({symbol:r.symbol,average:Number(r[field]),close:Number(r.close)}))
                .filter(r=>Number.isFinite(r.average) && r.average > 0 && Number.isFinite(r.close))
                .map(r=>({...r,distance:Math.abs(r.close-r.average)/r.average}));
            const subject=distances.find(r=>r.symbol === named[0].symbol);
            if (!subject || distances.length !== quotes.length) continue;
            const closer=/أقرب|اقرب/.test(relation[0]);
            if (distances.some(r=>r.symbol !== subject.symbol && (closer ? r.distance < subject.distance-0.0001 : r.distance > subject.distance+0.0001)))
                reasons.push(`average_distance_ranking_contradiction:${subject.symbol}:${field}`);
        }
    }
    // Compare claimed above/below relations to the actual quote, not merely whether both numbers exist.
    let owner: string | null = null;
    const allRows = evidence.flatMap(e => evidenceRows(e.data));
    const latestRowsBySymbol = new Map<string, any>();
    for (const row of allRows) {
        if (!row.symbol) continue;
        const prior = latestRowsBySymbol.get(row.symbol);
        const date = String(row.date || row.current_date || row.as_of || "").slice(0, 10);
        const priorDate = String(prior?.date || prior?.current_date || prior?.as_of || "").slice(0, 10);
        if (!prior || date >= priorDate) latestRowsBySymbol.set(row.symbol, row);
    }
    const rows = [...latestRowsBySymbol.values()];
    const known = [...new Set(rows.map(r=>r.symbol).filter(Boolean))];
    for (const raw of reply.split("\n")) {
        const line = raw.replace(/[*_`]/g, "");
        const named = known.filter(s=>new RegExp(`\\b${s}\\b`).test(line));
        if (named.length === 1) owner=named[0];
        if (named.length > 1 || !owner || /^\s*#{1,6}\s/.test(raw) || /(?:إذا|اذا|لو|عند اختراق|هدف|مستهدف|وقف)/.test(line)) continue;
        // A generic/disclaimer line ("being above EMA50 only describes the snapshot")
        // makes no relation claim about the previous owner; do not inherit it.
        if (named.length === 0 && (/لا\s*(?:يثبت|يعني|يدل|تثبت|تكفي|يمكن)|يصف\s+موقع|بشكل\s+عام|عموم|ملاحظة|تنبيه/.test(line) || /(?:الأسهم|الاسهم|أغلب|اغلب|معظم|الشركات|النماذج|المجموعة|القطاع|السوق|stocks|shares)/.test(line))) continue;
        const row = [...rows].reverse().find(r=>r.symbol === owner && r.close != null);
        if (!row) continue;
        for (const relation of line.matchAll(/(?<!ال)(فوق|أعلى من|اعلى من|تحت|أسفل|اسفل|above|below)\s*(?:الـ\s*)?EMA\s*(50|200)/gi)) {
            if (/(?:ليس|مش|لا|غير)\s*$/.test(line.slice(Math.max(0,relation.index!-12),relation.index))) continue;
            // A generic clause that precedes the stock it later names is not a claim about the previous owner.
            if (named.length === 1 && line.search(new RegExp(`\\b${named[0]}\\b`)) > relation.index!) continue;
            const close=Number(row.close), average=Number(row[`ema_${relation[2]}`]);
            if (!Number.isFinite(close) || !Number.isFinite(average)) continue;
            const above=/فوق|أعلى|اعلى|above/i.test(relation[1]);
            const relativeDiff = Math.abs(close - average) / average;
            // If close and average are virtually identical (within 0.8% parity/testing band),
            // describing the position as at/near/above/below is within snapshot rounding tolerance.
            if (relativeDiff > 0.008) {
                if ((above && close < average) || (!above && close > average)) reasons.push(`price_average_relation_contradiction:${owner}:ema_${relation[2]}`);
            }
        }
    }
    // Check numbers in markdown rows against the named stock, including rows with no currency unit.
    const headingSymbols = [...reply.matchAll(/(?:^|\n)\s*(?:#{1,4}[^\n]*|[^\n]*(?:تحليل سهم|سهم)\s+[^\n]*)\(([A-Z]{3,6})\)/g)]
        .map(m => m[1].toUpperCase())
        .filter(s => !["RSI", "MACD", "EMA", "EPS", "EGX", "PRO", "VIP", "USD", "EGP", "DCF", "SME"].includes(s));
    const allSymbols = [...new Set([...evidence.flatMap(e => e.symbols), ...headingSymbols])];
    const stockSymbols = allSymbols.filter(s => !["EGX", "RSI", "MACD", "EMA", "EPS", "PRO", "VIP", "USD", "EGP", "DCF", "SME"].includes(s));
    const portfolioFacts = facts.filter(f => f.symbol === "PORTFOLIO" || !f.symbol);
    let currentSymbol: string | null = stockSymbols.length === 1 ? stockSymbols[0] : null;
    let rankColIdx: number = -1;
    let inTable = false;
    let tableHadStockRow = false;
    let tableColSymbols: Array<string | null> = [];
    let isComparisonTable = false;
    let headers: string[] = [];
    let marketSection = false;
    const companyFields = (fields: FactRecord["field"][] | undefined, symbol: string) =>
        fields?.length === 1 && fields[0] === "market_value"
        && evidence.some(e => ["get_fundamentals","get_sector_peers"].includes(e.tool) && e.symbols.includes(symbol))
        && facts.some(f => f.symbol === symbol && f.field === "market_cap")
        && !facts.some(f => f.symbol === symbol && f.field === "market_value")
            ? ["market_cap" as const] : fields;

    const matchesFact = (val: number, targetFacts: FactRecord[], precision?: number): boolean => {
        const candidateFacts = targetFacts;
        return candidateFacts.some(f => {
            const fractionalScreenPrice = f.tool === "screen_stocks" && Math.abs(f.value) < 1
                && ["price", "close", "resistance"].includes(f.field);
            const distancePrecision = precision != null && ["distance_from_support_pct", "distance_from_resistance_pct"].includes(f.field);
            const tol = distancePrecision ? Math.max(0.02, 0.5 * 10 ** -precision! + 1e-8) : fractionalScreenPrice ? Math.max(0.00005, Math.abs(f.value) * 0.0005) : Math.max(0.02, Math.abs(f.value) * 0.005);
            if (Math.abs(val - f.value) <= tol) return true;
            // If the recorded fact is negative (e.g. loss or drop), reporting the positive magnitude is standard in financial tables/prose.
            if (f.value < 0 && Math.abs(val - Math.abs(f.value)) <= tol) return true;
            if (f.field === "backtest_drawdown_pct" && val < 0 && Math.abs(Math.abs(val) - f.value) <= tol) return true;
            if (val < 0 && f.value > 0 && Math.abs(Math.abs(val) - f.value) <= tol && !["change_pct", "profit_pct", "macd", "macd_signal", "macd_hist"].includes(f.field)) return true;
            return false;
        });
    };

    for (const rawLine of reply.split("\n")) {
        const line = rawLine.trim();
        const lineSymbols = stockSymbols.filter(s => new RegExp(`\\b${s}\\b`, "i").test(line));
        const lineSymbol = lineSymbols.length === 1 ? lineSymbols[0] : null;
        if (lineSymbol) {
            currentSymbol = lineSymbol;
            marketSection = false;
        } else if (lineSymbols.length > 1) {
            currentSymbol = null;
            marketSection = false;
        } else if (/\bEGX\b/i.test(line) && /مؤشر|سوق|اتساع|breadth|market/i.test(line)) {
            marketSection = true;
            currentSymbol = null;
        }

        if (!line.startsWith("|")) {
            if ((/اتساع|breadth/i.test(line) && evidence.some(e=>e.tool === "get_market_breadth"))
                || (/سيولة\s*السوق|ملخص\s*السيولة|توزيع\s*السيولة|إجمالي\s*(?:السيولة|التداول)/i.test(line) && evidence.some(e => e.tool === "get_market" || e.tool === "get_market_breadth"))) marketSection = true;
            inTable = false;
            tableHadStockRow = false;
            tableColSymbols = [];
            isComparisonTable = false;
            // Blank lines and explanatory prose do not erase the stock section.
            rankColIdx = -1;
            continue;
        }

        const isNewTable = !inTable;
        if (!inTable) {
            inTable = true;
            tableHadStockRow = false;
            tableColSymbols = [];
            isComparisonTable = false;
            headers = [];
        }

        if (/^\|[\s\-:|]+\|$/.test(line)) continue;

        const cells = line.split("|").slice(1, -1).map(c => c.trim());

        if (isNewTable && cells.some(c => /ترتيب|مركز|أولوية|تصنيف|أفضلية|^#$|^م$|^ت$|رقم|rank|tier|category/i.test(c))) {
            headers = cells;
            rankColIdx = cells.findIndex(c => /ترتيب|مركز|أولوية|تصنيف|أفضلية|^#$|^م$|^ت$|رقم|rank|tier|category/i.test(c));
            continue;
        }

        if (isNewTable) headers = cells;

        // Detect comparison table where multiple columns are stock symbols (e.g. | وجه المقارنة | COMI | EAST |)
        if (isNewTable || tableColSymbols.length === 0) {
            const detectedCols = cells.map(cell => stockSymbols.find(s => new RegExp(`\\b${s}\\b`, "i").test(cell)) || null);
            if (detectedCols.filter(Boolean).length >= 2) {
                isComparisonTable = true;
                tableColSymbols = detectedCols;
                continue;
            }
        }

        if (isComparisonTable) {
            if (/ترتيب|مركز|مرتب[ةه]|أولوية|تصنيف|أفضلية|^#$|^م$|^ت$|رقم|rank|tier|category|تاريخ|التاريخ|الجلسة|جلسة|date|session|المؤشر|مؤشر|القطاع|قطاع|index|sector/i.test(cells[0])) continue;
            for (let colIdx = 0; colIdx < cells.length; colIdx++) {
                const colSymbol = tableColSymbols[colIdx];
                if (!colSymbol) continue;
                const cell = cells[colIdx];
                if (!/\d/.test(cell)) continue;
                const compoundReasons = checkCompoundMetricCell(cells[0], cell, colSymbol, facts);
                if (compoundReasons) { reasons.push(...compoundReasons); continue; }
                const clean = cleanCellText(cell);
                const matches = [...clean.matchAll(/[-+]?\d+(?:\.\d+)?/g)];
                const fields = companyFields(tableMetricFields(cells[0]), colSymbol);
                const isPercentage = /[%٪]/.test(cell);
                const effectiveFields = isPercentage && (!fields || !fields.includes("change_pct")) && (fields?.includes("close") || fields?.includes("price") || !fields)
                    ? [...(fields || []), "change_pct" as const]
                    : fields;
                const targetFacts = facts.filter(f => f.symbol === colSymbol && (!effectiveFields || effectiveFields.includes(f.field)));
                for (const match of matches) {
                    const n = Number(match[0]);
                    if (!matchesFact(n, targetFacts)) {
                        reasons.push(`table_value_not_grounded:${colSymbol}:${n}`);
                    }
                }
            }
            continue;
        }

        if (!cells.some(c => /\d/.test(c))) continue;

        const isSummaryRow = cells.some(c => /^(?:(?:ال)?إجمالي|(?:ال)?مجموع|(?:ال)?محفظ[ةه]|(?:إجمالي|مجموع)\s*(?:ال)?محفظ[ةه]|(?:ال)?كلي|عدد\s*(?:المراكز|الأسهم|الصفقات)|المراكز(?:\s*المفتوحة)?|total|summary|overall)$/i.test(c.replace(/[*_#]/g, "").trim()));

        if (lineSymbols.length > 0) {
            tableHadStockRow = true;
        }

        let symbol: string | null = null;
        const stockQuantityRow = currentSymbol && !tableHadStockRow && /عدد\s*(?:الأسهم|المراكز|الصفقات)|المراكز/i.test(cells[0]);
        if (isSummaryRow && !stockQuantityRow) {
            symbol = "PORTFOLIO";
        } else if (lineSymbols.length === 1) {
            symbol = lineSymbols[0];
        } else if (lineSymbols.length > 1) {
            symbol = lineSymbols.join("/");
        } else if (!tableHadStockRow) {
            symbol = currentSymbol;
        } else {
            symbol = null;
        }

        // Breadth and market liquidity metrics belong to the dated market sample, never the last peer row.
        const isSectorTable = headers.length > 0
            && /(?:قطاع|sector)/i.test(headers[0].replace(/[*_`]/g, "").trim())
            && evidence.some(e => Array.isArray(e.data?.sector_liquidity) && e.data.sector_liquidity.length > 0);
        const marketEvidence = evidence.some(e => (e.tool === "get_market_breadth" || e.tool === "get_market") && (e.symbols?.includes("EGX") || Boolean(e.data?.egx30 || e.data?.market_liquidity || e.data?.total != null)));
        const marketScope = marketSection || currentSymbol === "EGX" || allSymbols.length === 1 && allSymbols[0] === "EGX";
        const totalLabel = (/إجمالي|مجموع|total/i.test(cells[0]) || /عدد.*(?:الأسهم|العينة)/.test(cells[0])) && !/سيول[ةه]|تداول|جنيه|مليون|مليار|قيمة|تدفق/i.test(cells[0]);
        const breadthFields = marketEvidence && marketScope && totalLabel && !/صاعد|هابط|ثابت/.test(cells[0])
            ? ["breadth_total" as const] : tableMetricFields(cells[0]);
        if (isSectorTable) symbol = "EGX";
        if (marketEvidence && marketSection && lineSymbols.length === 0 && !tableHadStockRow) symbol = "EGX";
        if (lineSymbols.length === 0 && breadthFields?.some(f => f.startsWith("breadth_"))
            && marketEvidence) symbol = "EGX";
        const scenarioRow = scenarioTableRow(evidence, cells, lineSymbols, headers);
        if (scenarioRow?.symbol === "PORTFOLIO") symbol = "PORTFOLIO";
        else if (!symbol && scenarioRow) symbol = scenarioRow.symbol || "PORTFOLIO";
        if (!symbol) {
            const metricFields = !tableHadStockRow ? tableMetricFields(cells[0]) : undefined;
            const strictTechnicalMetric = metricFields?.some(f => ["support", "resistance", "rsi", "macd", "macd_signal", "macd_hist", "ema_50", "ema_200", "pe_ratio", "eps", "market_cap"].includes(f));
            if (strictTechnicalMetric && facts.filter(f => metricFields!.includes(f.field)).length === 0) {
                reasons.push("ungrounded_technical_table_without_evidence");
            }
            continue;
        }
        const dates = evidence.flatMap(e => evidenceRows(e.data)).filter(r => r.symbol === symbol)
                .flatMap(r => [
                    r.date, r.current_date, r.scan_date, r.signal_date, r.indicators_date,
                    ...(r.strategy_metrics?.length ? [r.start_date] : []),
                    r.last_week_summary?.baseline_date, r.last_week_summary?.start_date, r.last_week_summary?.end_date,
                    ...(Array.isArray(r.recent_sessions) ? r.recent_sessions.map((s: any) => s.date) : [])
                ]).filter(Boolean).map(d => String(d).slice(0,10));
        for (const date of line.match(/\b\d{4}-\d{2}-\d{2}\b/g) || []) {
            if (!dates.includes(date)) reasons.push(`table_date_not_grounded:${symbol}:${date}`);
        }
        const dateColumn = headers.findIndex(header => /^(?:(?:تاريخ|التاريخ|الجلسة|تاريخ الجلسة|date|session))$/i.test(header.replace(/[*_`]/g, "").trim()));
        const datedSession = dateColumn >= 0 ? groundedTableDate(cells[dateColumn] || "", dates) : null;
        if (dateColumn >= 0 && !datedSession) reasons.push(`table_date_not_grounded:${symbol}:${cells[dateColumn]}`);

        for (let idx = 0; idx < cells.length; idx++) {
            if (idx === rankColIdx || idx === dateColumn || cells[idx].includes(symbol)) continue;
            const screenRow = evidence.filter(e => e.tool === "screen_stocks").flatMap(e => evidenceRows(e.data)).find(row => row.symbol === symbol);
            const header = headers[idx] || "";
            const compoundReasons = checkCompoundMetricCell(header, cells[idx], symbol, facts)
                ?? (!tableHadStockRow ? checkCompoundMetricCell(cells[0], cells[idx], symbol, facts) : null);
            if (compoundReasons) { reasons.push(...compoundReasons); continue; }
            const explicitDenominator = /(?:أساس|على|مقام|÷)/.test(header) && /الإغلاق|الاغلاق|المقاومة/.test(header)
                ? /الإغلاق|الاغلاق/.test(header) ? "close" : "resistance" : null;
            const formula = normalizeDigitsAndNumberFormatting(cells[idx].replace(/[*_`]/g, "")).match(/^\s*\(\s*(\d+(?:\.\d+)?)\s*[-−]\s*(\d+(?:\.\d+)?)\s*\)\s*[÷/]\s*(\d+(?:\.\d+)?)\s*[×*]\s*(\d+(?:\.\d+)?)(?:\s*=\s*([-+]?\d+(?:\.\d+)?)\s*[%٪]?)?\s*$/);
            if (screenRow && formula) {
                const [a,b,denom,factor,result] = formula.slice(1).map(Number);
                const expectedDenom = explicitDenominator ? screenRow[explicitDenominator]
                    : /\/resistance\*100/.test(String(screen?.data.methodology)) ? screenRow.resistance : screenRow.close;
                const exact = (value:number,expected:number) => Math.abs(value-expected) <= Math.max(1e-6,Math.abs(expected)*1e-7);
                const computed = (a-b)/denom*factor;
                if (!exact(a,screenRow.resistance) || !exact(b,screenRow.close) || !exact(denom,expectedDenom) || factor !== 100
                    || (formula[5] != null && Math.abs(result-computed) > 0.5*10**-(formula[5].split(".")[1]?.length || 0)+1e-8))
                    reasons.push(`table_distance_formula_not_grounded:${symbol}`);
                continue;
            }
            if (screenRow && explicitDenominator && Number.isFinite(screenRow.close) && screenRow.close > 0 && screenRow.resistance > 0) {
                const expected = (screenRow.resistance-screenRow.close)/screenRow[explicitDenominator]*100;
                const cell = normalizeDigitsAndNumberFormatting(cleanCellText(cells[idx])).match(/^([-+]?\d+(?:\.\d+)?)\s*[%٪]?$/);
                if (cell) {
                    const precision = cell[1].split(".")[1]?.length || 0;
                    if (Math.abs(Number(cell[1])-expected) > 0.5*10**-precision+1e-8) reasons.push(`table_value_not_grounded:${symbol}:${Number(cell[1])}`);
                    continue;
                }
            }
            const distanceColumn = /مساف|الموقع.*(?:إغلاق|اغلاق)|بعد.*(?:إغلاق|اغلاق)/i.test(headers[idx] || "");
            const levelField: FactRecord["field"] | undefined = /دعم/.test(cells[0]) ? "distance_from_support_pct"
                : /مقاوم/.test(cells[0]) ? "distance_from_resistance_pct" : undefined;
            const rowFields = !tableHadStockRow ? (symbol === "EGX" ? breadthFields : tableMetricFields(cells[0])) : undefined;
            const isCommentaryCol = (
                /(?:الوصف(?:\s+الفني)?|القراءة(?:\s+والتقييم)?|ملاحظات|التعليق|التفسير|الدلالة|الشرح|البيان|الإشارة|الوضع\s+الفني|ملخص|الحالة(?:\s+الفنية)?)/i.test(header)
                || /(?:خبر|أخبار|اخبار|عنوان|عناوين|إفصاح|افصاح|إفصاحات|افصاحات|تفاصيل|ملخص(?:\s+الخبر)?|news|headline|headlines|summary|disclosure|source|مصدر|رابط)/i.test(header)
                || (evidence.some(e => e.tool === "get_news") && /(?:نص|موضوع|حدث|بيان)/i.test(header))
            ) && !/سعر|إغلاق|اغلاق|قيمة(?:\s+السهم|\s+السوقية)?|مستوى|عائد|ربح%|price|close|target|stop|دعم|مقاوم/i.test(header);
            if (isCommentaryCol) continue;
            const verticalMetricValue = Boolean(rowFields?.length)
                && (/^(?:(?:السعر|سعر|القيمة|قيمة|المستوى|مستوى|price|value|level)(?:\s*(?:[\/،-]|أو)\s*(?:السعر|سعر|القيمة|قيمة|المستوى|مستوى))?(?:\s*\([^)]*\))?)$/i.test(header.replace(/[*_`]/g," ").trim())
                    || (rowFields?.some(f => f.startsWith("breadth_")) && /^(?:العدد|عدد|count)$/i.test(header.trim())));
            let fields = screenRow && /مساف|بعد|قرب/.test(header) ? ["distance_from_resistance_pct" as const] : distanceColumn && levelField ? [levelField]
                : isCommentaryCol ? undefined
                : verticalMetricValue ? rowFields
                : (scenarioRow ? scenarioMetricFields(headers[idx]) : tableMetricFields(headers[idx]))
                    || (currentSymbol && idx < 2 ? tableMetricFields(cells[0]) : undefined);
            // Resolve the short shared label only with unambiguous company evidence.
            if (fields?.length === 1 && fields[0] === "market_value"
                && evidence.some(e => (e.tool === "get_fundamentals" || e.tool === "get_sector_peers") && e.symbols.includes(symbol!))
                && facts.some(f => f.symbol === symbol && f.field === "market_cap")
                && !facts.some(f => f.symbol === symbol && f.field === "market_value")) fields = ["market_cap"];
            const allocationFacts = scenarioRow ? buildFactRecords([{ tool: "analyze_portfolio_risk", source: "scenario-calculation",
                data: [{ symbol, position_pct: scenarioRow.allocation_pct, value: scenarioRow.allocated_capital,
                    scenario_loss_pct: scenarioRow.scenario_loss_pct, scenario_loss_amount: scenarioRow.scenario_loss_amount }] }]) : [];
            const relevant = scenarioRow && fields?.some(field => ["position_pct", "value", "scenario_loss_pct", "scenario_loss_amount"].includes(field)) ? allocationFacts
                : symbol === "PORTFOLIO" ? portfolioFacts : facts.filter(f => f.symbol === symbol);
            const strategyRows = evidence.flatMap(e => evidenceRows(e.data));
            const knownStrategies = [
                ...strategyRows.flatMap(r => r.strategy_metrics || []),
                ...strategyRows.filter(r => r.analysis?.strategyId).map(r => ({
                    strategy_id: r.analysis.strategyId,
                    strategy_name: r.analysis.strategyId
                }))
            ];
            const namedStrategy = knownStrategies.find(m => line.includes(m.strategy_id) || (m.strategy_name && line.includes(m.strategy_name)));
            const strategyRelevant = namedStrategy ? relevant.filter(f => (!f.field.startsWith("backtest_") && !f.field.startsWith("chart_")) || f.id.includes(`:${namedStrategy.strategy_id}:`)) : relevant;
            // A metric label may itself quote a dated baseline price. Validate
            // those label numbers as prices, not as the percentage in the value cell.
            if (idx === 0 && rowFields?.length) fields = undefined;
            const weeklyChangeValue = idx > 0 && rowFields?.includes("change_pct") && /أسبوع|اسبوع/.test(cells[0]);
            const arabicMonthRegex = /(?<![0-9])\d{1,2}\s+(?:يناير|فبراير|مارس|أبريل|ابريل|مايو|يونيو|يوليو|أغسطس|اغسطس|سبتمبر|أكتوبر|اكتوبر|نوفمبر|ديسمبر)(?:\s+\d{4})?/gi;
            const resolvedArabicRowDates = [...line.matchAll(arabicMonthRegex)].map(m => groundedTableDate(m[0], dates)).filter((d): d is string => Boolean(d));
            const baseRowDates = weeklyChangeValue ? [] : datedSession ? [datedSession] : [...new Set([...(line.match(/\b\d{4}-\d{2}-\d{2}\b/g) || []), ...resolvedArabicRowDates])];
            const mentionsSpot = /(?:السعر|سعر|الإغلاق|اغلاق|إغلاق)\s*(?:الحالي|الأخير|اليوم)/i.test(line);
            const rowDates = baseRowDates.length && mentionsSpot && dates[0] ? [...new Set([...baseRowDates, dates[0]])] : baseRowDates;
            const datedRelevant = rowDates.length ? strategyRelevant.filter(f => !["close","high","low","change_pct"].includes(f.field) || (f.as_of && rowDates.includes(f.as_of.slice(0,10)))) : strategyRelevant;
            const explicitSpotPriceRef = !tableHadStockRow && (/(?:السعر|سعر|الإغلاق|اغلاق|إغلاق|close|price)/i.test(cells[idx]) || /(?:السعر|سعر|الإغلاق|اغلاق|إغلاق|close|price)/i.test(cells[0]))
                && !/سعر.*(?:شراء|دخول)|(?:أعلى|اعلى|الأعلى|الاعلى|أدنى|ادنى|الأدنى|الادنى)\s*سعر/i.test(cells[0]);
            const effectiveFields = fields && explicitSpotPriceRef ? [...new Set<FactRecord["field"]>([...fields, "close", "price"])] : fields;
            const targetFacts = effectiveFields ? datedRelevant.filter(f => effectiveFields.includes(f.field)) : datedRelevant;
            // Portfolio screenshots often place the cash gain/loss and its
            // percentage together in one cell under a single "return" column
            // (for example: "−784 EGP ▼2.74%"). The visible image evidence
            // records those as two distinct facts. Let both ground that cell,
            // while still requiring an exact matching fact for every number.
            const combinedImageReturn = evidence.some(e => e.tool === "image_vision" && e.data_type === "image-derived")
                && Boolean(fields?.includes("profit_pct"))
                && /ربح|خسار|عائد|return|profit/i.test(headers[idx] || "")
                && /[%٪]/.test(cells[idx]);
            const cellFacts = combinedImageReturn
                ? strategyRelevant.filter(f => fields?.includes(f.field) || f.field === "profit_value")
                : targetFacts;
            const cellWithoutGroundedArabicDates = cells[idx].replace(arabicMonthRegex, m => groundedTableDate(m, dates) ? " " : m);
            let clean = cleanCellText(cellWithoutGroundedArabicDates);
            if (isCommentaryCol) {
                // In commentary / qualitative description columns (e.g. "الوصف الفني", "ملاحظات"),
                // strip any descriptive percentages, dates, and session counts so they are not evaluated as stock prices.
                clean = clean
                    .replace(/[-+]?\d+(?:\.\d+)?\s*[%٪]/g, " ")
                    .replace(/(?:جلسة|بتاريخ|تاريخ|يوم|في)?\s*\b\d{1,2}[-/]\d{1,2}\b/g, " ");
            }
            if (fields?.includes("backtest_final_equity")) {
                // An explicitly labeled starting amount is a different fact from final equity.
                const initial = evidence.filter(e => e.tool === "compare_strategies_history" && e.availability !== "error" && e.symbols.includes(symbol))
                    .map(e => e.data?.assumptions?.initialCapital).filter(Number.isFinite);
                clean = clean.replace(/\(\s*(?:من|رأس المال الابتدائي|رأس المال الأولي|initial capital)\s*([-+]?\d+(?:\.\d+)?)\s*(?:جنيه)?\s*\)/gi,
                    (full, value) => initial.includes(Number(value)) ? " " : full);
            }
            for (const match of clean.matchAll(/[-+]?\d+(?:\.\d+)?/g)) {
                const n = Number(match[0]);
                const prec = match[0].includes(".") ? match[0].split(".")[1].length : undefined;
                if (!matchesFact(n, cellFacts, prec) || (match[0].startsWith("+") && !matchesFact(n, cellFacts.filter(f => f.value >= 0), prec) && matchesFact(-n, cellFacts.filter(f => f.value < 0), prec)))
                    reasons.push(`table_value_not_grounded:${symbol}:${n}`);
            }
        }
    }
    return [...new Set(reasons)];
}

/**
 * Non-blocking corrections for image-derived values. These never veto a reply;
 * they ask the writer to fix or flag a contradiction between the profit amount
 * and its percentage for the same position, or a stated total that does not add
 * up. Kept separate from checkAgenticDraft so a real answer is corrected in
 * place instead of being replaced by a fallback.
 */
export function advisoryImageConsistency(reply: string, evidence: AgenticEvidence[]): string[] {
    const issues: string[] = [];
    const cites = (symbol: string) => new RegExp(`(?<![A-Z0-9])${symbol}(?![A-Z0-9])`, "i").test(reply);
    for (const e of evidence) {
        if (e.tool !== "image_vision" || e.availability === "error") continue;
        for (const row of evidenceRows(e.data)) {
            const symbol = String(row.symbol || "").toUpperCase();
            if (!symbol || !cites(symbol)) continue;
            const amount = Number(row.profit_value);
            const pct = Number(row.profit_loss_pct);
            if (Number.isFinite(amount) && Number.isFinite(pct) && amount !== 0 && pct !== 0
                && Math.sign(amount) !== Math.sign(pct)) {
                issues.push(`صورة ${symbol}: مبلغ الربح/الخسارة (${amount}) لا يطابق إشارة العائد (${pct}%). صحّح الإشارة من الصورة، أو وضّح أن العمود غير متحقق بدل عرض الرقمين كناتج واحد.`);
            }
        }
    }
    return [...new Set(issues)];
}

/**
 * Generic, non-blocking correction: a section heading that declares a count
 * (e.g. "عناصر (9)" or "9 مراكز") must match the number of data rows in the
 * table that follows it. Only explicit row/entity counts qualify; dates, candle windows and metric values do not.
 */
export function advisoryTableRowCountConsistency(reply: string): string[] {
    const issues: string[] = [];
    const lines = reply.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const heading = lines[i].trim();
        if (!heading || heading.startsWith("|")) continue;
        const cleanHeading = normalizeEvidenceNumbers(heading).replace(/[*_`#]/g, "")
            .replace(/\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b/g, "تاريخ");
        const entities = "(?:عناصر|عنصر|صفوف|صف|مراكز|مركز|أسهم|اسهم|سهم|صناديق|صندوق|استراتيجيات|استراتيجية|items?|rows?|holdings?|positions?|funds?|stocks?|strategies)";
        const before = new RegExp(`(${entities})\\s*[:：]?\\s*\\(?\\s*(\\d+)\\s*\\)?`, "i").exec(cleanHeading);
        const after = new RegExp(`(\\d+)\\s*${entities}(?![\\w\u0600-\u06ff])`, "i").exec(cleanHeading);
        const declaredCount = before?.[2] || after?.[1];
        if (!declaredCount) continue;
        let j = i + 1;
        while (j < lines.length && lines[j].trim() === "") j++;
        if (!lines[j] || !lines[j].trim().startsWith("|")) continue;
        let rows = 0, separatorSeen = false;
        for (let k = j; k < lines.length && lines[k].trim().startsWith("|"); k++) {
            if (/^\|[\s\-:|]+\|$/.test(lines[k].trim())) { separatorSeen = true; continue; }
            if (separatorSeen) rows++;
        }
        if (separatorSeen && rows > 0 && rows !== Number(declaredCount))
            issues.push(`عنوان القسم يذكر ${declaredCount} عنصراً بينما الجدول التالي يعرض ${rows} صفوف؛ وحّد العدد مع الصفوف المعروضة أو صحّح العنوان.`);
    }
    return [...new Set(issues)];
}

export function safeAgenticFallback(evidence: AgenticEvidence[], _reason: string, userMessage?: string): string {
    const lines: string[] = [];
    // Evidence passed here should already be scoped to the current request. Keep
    // the first available rows only as a bounded fallback and never resurrect
    // unrelated symbols from an older turn.
    for (const e of evidence.filter(e => e.availability !== "error")) {
        const planned = renderPlannedReadEvidence(e.tool, e.data);
        if (planned) lines.push(planned);
        if (e.tool === "get_market" && e.data?.status === "success" && e.data?.market_liquidity) {
            const ml = e.data.market_liquidity;
            const secs = Array.isArray(e.data.sector_liquidity) ? e.data.sector_liquidity.slice(0, 6) : [];
            const topStocks = Array.isArray(e.data.top_liquidity_stocks) ? e.data.top_liquidity_stocks.slice(0, 6) : [];
            lines.push(`\nملخص سيولة السوق الكلية بتاريخ ${ml.session_date || e.data.session_date || "أحدث جلسة"}:`);
            lines.push("| المقياس | القيمة |", "|---|---|");
            if (ml.total_turnover_million_egp != null) lines.push(`| إجمالي السيولة المتداولة (مليون ج.م) | ${ml.total_turnover_million_egp} |`);
            if (ml.avg_20d_turnover_million_egp != null) lines.push(`| متوسط السيولة لـ 20 جلسة (مليون ج.م) | ${ml.avg_20d_turnover_million_egp} |`);
            if (ml.turnover_vs_20d_pct != null) lines.push(`| نسبة السيولة من متوسط 20 جلسة % | ${ml.turnover_vs_20d_pct}% |`);
            if (ml.advancing_turnover_million_egp != null) lines.push(`| سيولة الأسهم الصاعدة (مليون ج.م) | ${ml.advancing_turnover_million_egp} (${ml.advancing_turnover_pct}%) |`);
            if (ml.declining_turnover_million_egp != null) lines.push(`| سيولة الأسهم الهابطة (مليون ج.م) | ${ml.declining_turnover_million_egp} (${ml.declining_turnover_pct}%) |`);
            if (ml.top5_concentration_pct != null) lines.push(`| تركز السيولة في أعلى 5 أسهم % | ${ml.top5_concentration_pct}% |`);
            if (ml.top10_concentration_pct != null) lines.push(`| تركز السيولة في أعلى 10 أسهم % | ${ml.top10_concentration_pct}% |`);
            if (secs.length > 0) {
                lines.push("\nتوزيع السيولة على القطاعات:", "| القطاع | السيولة (مليون ج.م) | حصة السوق % | التغير المرجح % | القائد |", "|---|---:|---:|---:|---|");
                for (const s of secs) {
                    lines.push(`| ${s.sector_ar || s.sector} | ${s.turnover_million_egp} | ${s.market_share_pct}% | ${s.weighted_change_pct}% | ${s.top_stock_symbol || "—"} |`);
                }
            }
            if (topStocks.length > 0) {
                lines.push("\nأعلى الأسهم استحواذاً على السيولة:", "| السهم | الإغلاق | التغير % | السيولة (مليون ج.م) | حصة السوق % | الحجم النسبي |", "|---|---:|---:|---:|---:|---:|");
                for (const st of topStocks) {
                    lines.push(`| ${st.symbol} | ${st.close} | ${st.change_pct}% | ${st.turnover_million_egp} | ${st.market_share_pct}% | ${st.r_vol ?? "—"} |`);
                }
            }
        }
        if (e.tool === "compare_strategies_history") {
            const result = renderBacktestEvidence(e.data);
            if (result) lines.push(result);
        }
        if (e.tool === "screen_stocks" && e.data?.status === "success") {
            const d=e.data;
            if (d.date && d.filters) {
                lines.push(`\nشاشة فنية بتاريخ ${d.date}: الشروط RSI بين ${d.filters.rsi_min} و${d.filters.rsi_max}، والحجم النسبي ${d.filters.relative_volume_inclusive === false ? ">" : "≥"} ${d.filters.relative_volume_min}، والمسافة من مقاومة أعلى 20 جلسة ${d.filters.resistance_distance_inclusive === false ? "<" : "≤"} ${d.filters.max_resistance_distance_pct}%.`);
                if (d.stocks?.length) {
                    const hasSessionSnapshot = stockPricePresentation(d.date).price_type === "current_session_snapshot";
                    lines.push(hasSessionSnapshot ? "| السهم | السعر المسجل | RSI | الحجم النسبي | المقاومة | البعد عنها % |" : "| السهم | الإغلاق | RSI | الحجم النسبي | المقاومة | البعد عنها % |","|---|---:|---:|---:|---:|---:|");
                    for(const r of d.stocks.slice(0,10)) lines.push(`| ${r.symbol} | ${r.close} | ${r.rsi_14} | ${r.r_vol} | ${r.resistance} | ${r.distance_from_resistance_pct} |`);
                    if (hasSessionSnapshot) lines.push("أسعار اليوم لقطات جلسة متاحة؛ اكتمال الجلسة والإغلاق النهائي غير مؤكدين.");
                } else lines.push("لم تظهر أسهم تطابق الشروط في البيانات المتاحة لهذه الجلسة.");
                lines.push("المساوي للمقاومة عندها، والأقل تحتها؛ أعلى 20 جلسة يشمل جلسة اللقطة، فلا يثبت قرب السعر أو مساواته اختراق مقاومة سابقة.");
                if(d.scan_complete===false) lines.push("المسح جزئي: بعض المرشحين تجاوزوا حد الفحص أو لا يتوفر لهم تاريخ 20 جلسة.");
            } else lines.push("لا تتوفر لقطة مؤرخة لإتمام المسح الفني حالياً.");
        }
        if (e.tool === "calculate_position" && e.data?.status === "success") {
            for (const r of e.data.positions || []) {
                if (r.quantity == null) {
                    lines.push(`\nحساب مؤقت للسهم ${r.symbol} دون حفظ: التكلفة الإجمالية المعروفة ${r.cost} جنيه. الكمية غير معروفة؛ ابعت عدد الأسهم لإكمال حساب القيمة والربح.`);
                    continue;
                }
                lines.push(`\nحساب مؤقت للسهم ${r.symbol} دون حفظ: ${r.quantity} سهم بمتوسط شراء ${r.entry_price ?? "مشتق من التكلفة والكمية"} جنيه، التكلفة ${r.cost} جنيه.`);
                if (r.market_value != null) lines.push(`على إغلاق ${r.close} بتاريخ ${r.date}: قيمة المركز ${r.market_value} جنيه، الربح/الخسارة ${r.profit_loss_val} جنيه (${r.profit_loss_pct}%). لا يشمل العمولات.`);
                else lines.push("لا يتوفر إغلاق مؤرخ لحساب القيمة والربح/الخسارة.");
            }
        }
        if (e.tool === "analyze_portfolio_risk" && e.data?.mode === "scenario") {
            const d=e.data;
            lines.push(`\nهذا سيناريو افتراضي من رأس مال ${d.capital} جنيه، بتوزيع ${d.assumption === "equal_weight" ? "متساوٍ مفترض" : "النسب التي حددتها"}؛ لا يمثل المراكز المحفوظة ولم يتم حفظه.`);
            lines.push("| السهم | القطاع من بيانات الشركة | الصناعة | من رأس المال % | المبلغ بالجنيه | من تعرض القطاع % | محفوظ بالحساب؟ |","|---|---|---|---:|---:|---:|---|");
            for(const r of d.stocks) {
                const sector = (d.sector_exposure || []).find((item:any) => item.sector === r.sector && item.allocated_capital > 0);
                const sectorShare = sector ? Number((r.allocated_capital / sector.allocated_capital * 100).toFixed(2)) : null;
                lines.push(`| ${r.symbol} | ${r.sector || "غير متاح"} | ${r.industry || "غير متاح"} | ${r.allocation_pct} | ${r.allocated_capital} | ${sectorShare ?? "غير متاح"} | ${r.saved ? "نعم" : "لا"} |`);
            }
            for(const r of d.sector_exposure) lines.push(`قطاع ${r.sector || "غير محدد"}: ${r.allocation_pct}% (${r.allocated_capital} جنيه).`);
            for(const r of d.industry_exposure || []) lines.push(`صناعة ${r.industry || "غير محدد"}: ${r.allocation_pct}% (${r.allocated_capital} جنيه).`);
            if(d.classification_note) lines.push(d.classification_note);
            if(d.rounding_note)lines.push(d.rounding_note);
            if(!d.sector_concentration_complete) lines.push("بيانات قطاع سهم أو أكثر غير متاحة؛ تجميع القطاعات جزئي ولا يصح اعتباره كاملاً.");
            lines.push(`اختبار حساسية حسابي فقط، وليس توقعاً: هبوط افتراضي 5% = ${d.stress_scenarios_not_forecasts[0].loss} جنيه، و10% = ${d.stress_scenarios_not_forecasts[1].loss} جنيه.`);
        }
        if (e.tool === "get_recommendations" && e.data?.status === "success") {
            const d = e.data;
            const ps = d.performance_summary;
            if (ps && ps.total_recommendations > 0) {
                lines.push(`\nملخص أداء التوصيات للفترة (${d.timeframe || "all"}): إجمالي التوصيات ${ps.total_recommendations} (المغلقة: ${ps.closed_count}، المفتوحة: ${ps.open_count})، نسبة النجاح ${ps.win_rate_pct != null ? `${ps.win_rate_pct}%` : "غير محدد"} (${ps.win_count} رابحة مقابل ${ps.loss_count} خاسرة)، متوسط العائد ${ps.avg_return_pct != null ? `${ps.avg_return_pct}%` : "غير محدد"}.`);
            }
            if (d.recommendations?.length) {
                lines.push("| السهم | الإشارة | تاريخ التوصية | سعر الدخول | المستهدف | وقف الخسارة | الحالة | العائد % |", "|---|---|---|---:|---:|---:|---|---:|");
                for (const r of d.recommendations.slice(0, 15)) {
                    const returnVal = r.realized_return_pct != null ? `${r.realized_return_pct}%` : r.unrealized_return_pct != null ? `${r.unrealized_return_pct}%` : "—";
                    lines.push(`| ${r.symbol || "—"} | ${r.signal || "BUY"} | ${r.signal_date || "—"} | ${r.entry_price ?? "—"} | ${r.target_price ?? "—"} | ${r.stop_loss ?? "—"} | ${r.status || "—"} | ${returnVal} |`);
                }
                if (d.truncated) {
                    lines.push(`معروض عينة من ${d.recommendations.length} من إجمالي ${d.total_count} توصية للفترة.`);
                }
            } else if (d.note) {
                lines.push(`\n${d.note}`);
            }
        }
        if (e.tool === "get_news") {
            const d = e.data;
            if (d?.news?.length) {
                lines.push("\nعناوين الأخبار الموثقة من المصدر:");
                for (const item of d.news.slice(0, 5)) {
                    const headlines = (item.headlines || []).slice(0, 3).join(" | ");
                    lines.push(`• سهم ${item.symbol || "—"} (${item.date || "—"}): ${headlines || "لا توجد تفاصيل"}`);
                }
            } else if (d?.note) {
                lines.push(`\n${d.note}`);
            } else if (e.symbols?.length) {
                lines.push(`\nمصدر المنصة لم يرجع عناوين موثقة لـ ${e.symbols.join("، ")} خلال آخر 7 أيام؛ هذا لا يثبت غياب أخبار خارج تغطيته ولا يحدد سبب الحركة.`);
            }
        }
    }
    const stockRows = evidence.filter(e => ["get_stock", "get_stock_levels", "get_comparison", "get_live_quote"].includes(e.tool)
        && e.availability !== "error" && e.availability !== "missing").flatMap(e => evidenceRows(e.data));
    const userWantsHistory = Boolean(userMessage && /(?:تاريخ|جلسات|إقفال\s+سابق|الأسبوع\s+الماضي|من\s+أسبوع|جلسة\s+سابقة|تغيرات\s+الأسبوع|أسبوع\s+فات|تاريخ\s+السعر)/i.test(userMessage));
    const stockExplanation = renderStockRecovery(stockRows, { includeRecentSessions: userWantsHistory });
    if (stockExplanation) lines.push(stockExplanation);
    for (const e of evidence) if (e.data?.persisted === true) lines.push(`عملية المحفظة ${e.data.operation} للسهم ${e.data.symbol}: تم تأكيد تعديل المركز؛ لا تكرر العملية تلقائياً.${e.data.cash_updated === false && e.data.operation === "sell" ? " لم يتغير الرصيد النقدي." : ""}`);
    if (evidence.some(e => e.availability === "error")) lines.push("تعذر تنفيذ بعض أدوات البيانات؛ لا تعتبر نتائجها فارغة أو عملياتها محفوظة.");
    const alreadyDetailed = lines.some(l => l.includes("المسح جزئي") || l.includes("لا توجد أخبار") || l.includes("لا توجد عناوين") || l.includes("لا توجد توصيات") || l.includes("سجل الجلسات الأخيرة"));
    if (!alreadyDetailed && evidence.some(e => e.availability === "missing" || e.availability === "partial")) lines.push("بعض البيانات المطلوبة غير متاحة أو غير مكتملة في المصدر.");
    return lines.length ? lines.join("\n") : "لم تصل بيانات مؤكدة للإجابة عن الطلب الحالي. أعد المحاولة بعد قليل؛ لن أعرض أسعارًا أو نتائج اختبار غير محسوبة.";
}

