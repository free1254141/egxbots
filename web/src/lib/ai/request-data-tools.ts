import { ARABIC_STOCK_MAPPINGS } from './symbol-aliases';
import { executeAgenticTool, cairoTimeframeBounds } from './agentic-tools';
import type { ChartHistoryCache } from './chart-strategy-tools';
import { isShariaCompliant } from '../shariaStocks';

const readBatches = new Set(['get_stock', 'get_stock_levels', 'get_comparison', 'get_fundamentals']);
export function requestToolCost(name: string, args: any): number {
    return readBatches.has(name) && Array.isArray(args?.symbols) ? Math.max(1, Math.ceil(args.symbols.length / 10)) : 1;
}
const normalizeArabic = (s: string) => s.replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/[\u0640\u064B-\u065F]/g, '').toLowerCase();
/** Name evidence for the LLM; never replace an explicit ticker or route intent. */
export function knownSymbolHints(message: string): Array<{ name: string; symbols: string[] }> {
    const text = normalizeArabic(message);
    return Object.entries(ARABIC_STOCK_MAPPINGS).filter(([name]) => /[\u0600-\u06FF]/.test(name))
        .sort(([a], [b]) => b.length - a.length).filter(([name]) => {
            const alias = normalizeArabic(name).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            return new RegExp(`(?:^|[^\\p{L}\\p{N}])${alias}(?=$|[^\\p{L}\\p{N}])`, 'u').test(text);
        }).slice(0, 30).map(([name, value]) => ({ name, symbols: Array.isArray(value) ? value : [value] }));
}

export const REQUEST_DATA_TOOLS_SCHEMA = [{ type: 'function', function: {
    name: 'get_corporate_actions',
    description: 'اقرأ سجل الإجراءات الرأسمالية والتوزيعات والأخبار المؤرخة للسهم المطلوب: اكتتاب، زيادة رأس مال، كوبون، تجزئة. ميّز المصدر الرسمي عن الخبر، وغياب السجل لا ينفي وجود الحدث أو يثبت أن الاكتتاب مفتوح اليوم.',
    parameters: { type: 'object', properties: { symbols: { type: 'array', items: { type: 'string' }, maxItems: 10 },
        action_type: { type: 'string', enum: ['rights_issue', 'capital_increase', 'capital_reduction', 'dividend', 'stock_split', 'bonus_shares', 'all'] } }, required: ['symbols'] }
} }];

export async function executeRequestTool(name: string, args: any, db: any, userId: string, cache: ChartHistoryCache,
    access: { isPro: boolean }): Promise<any> {
    if (name === 'get_recommendations') {
        // The access decision is supplied by the authenticated route, never tool arguments.
        const legacy = await executeAgenticTool(name, { ...args, status: args.status || 'open', limit: 200 }, db, userId, cache);
        if (legacy.status !== 'success') return legacy;
        const snapshot = await db.from('short_swing_checkpoints').select('payload,computed_at')
            .eq('checkpoint_key', 'short_swings_latest').limit(1);
        const saved = snapshot.data?.[0], swings = saved?.payload?.swings;
        const shortAvailable = !snapshot.error && swings?.status === 'ok';
        const status = args.status || 'open', timeframe = args.timeframe || 'all';
        const bounds = cairoTimeframeBounds();
        const since = timeframe === 'this_week' ? bounds.thisWeekStartIso
            : timeframe === 'last_week' ? bounds.lastWeekStartIso
            : timeframe === 'this_month' ? bounds.thisMonthStartIso
            : timeframe === 'last_month' ? bounds.lastMonthStartIso
            : timeframe === 'last_30_days' ? bounds.last30DaysStartIso
            : timeframe === 'last_90_days' ? bounds.last90DaysStartIso
            : null;
        const before = timeframe === 'last_week' ? bounds.thisWeekStartIso
            : timeframe === 'last_month' ? bounds.lastMonthEndIso
            : null;
        const filtered = (r: any) => (!args.symbols?.length || args.symbols.some((s: string) => s.toUpperCase().replace(/\.CA$/, '') === r.symbol))
            && (!args.sharia_only || isShariaCompliant(r.symbol))
            && (!since || String(r.signal_date || '') >= since.slice(0, 10))
            && (!before || String(r.signal_date || '') < before.slice(0, 10));
        const shorts: any[] = [];
        if (shortAvailable) for (const [closed, trades] of [[false, swings.active_trades], [true, swings.closed_trades]] as const) {
            if (status === 'open' && closed || status === 'closed' && !closed) continue;
            for (const t of Array.isArray(trades) ? trades : []) {
                const row = { source_kind: 'short_swings', recommendation_type: 'صفقة قصيرة', id: t.signal_id,
                    symbol: t.symbol, name: t.name_ar || t.name_en, signal: 'BUY', status: closed ? 'closed' : 'open',
                    is_sharia_compliant: isShariaCompliant(t.symbol),
                    sharia_index: isShariaCompliant(t.symbol) ? "EGX33" : null,
                    signal_date: t.signal_date || t.entry_date, entry_date: t.entry_date,
                    entry_price: t.is_pending_entry ? null : t.entry_price,
                    reference_close: t.is_pending_entry ? t.reference_close : null,
                    current_price: closed ? null : t.current_price, current_date: closed ? null : t.price_date || t.as_of || swings.as_of,
                    exit_price: closed ? t.exit_price : null, exit_date: closed ? t.exit_date : null,
                    stop_loss: t.trailing_stop ?? t.stop_loss ?? null, target_price: null,
                    realized_return_pct: closed ? t.return_pct : null, unrealized_return_pct: closed ? null : t.is_pending_entry ? null : t.return_pct,
                    is_pending_entry: Boolean(t.is_pending_entry), snapshot_date: swings.as_of };
                if (filtered(row)) shorts.push(row);
            }
        }
        const legacyRows = legacy.recommendations.map((r: any) => ({ ...r, source_kind: 'model_signals', recommendation_type: 'توصية نماذج' }));
        const all = [...legacyRows, ...shorts].map(r => recommendationVisibility(r, access.isPro));
        const offset = Number.isInteger(args.offset) && args.offset >= 0 ? args.offset : 0;
        const limit = Number.isInteger(args.limit) && args.limit > 0 && args.limit <= 200 ? args.limit : 15;
        all.sort((a, b) => String(b.signal_date || '').localeCompare(String(a.signal_date || ''))
            || String(a.source_kind).localeCompare(String(b.source_kind)) || String(a.symbol || '').localeCompare(String(b.symbol || '')));
        const page = all.slice(offset, offset + limit);
        const total = legacy.total_count + shorts.length;
        const completeSources = shortAvailable && !legacy.truncated;
        const truncated = offset + page.length < total;
        return { status: 'success', availability: completeSources && !truncated ? 'available' : 'partial',
            recommendations: page, count: page.length, returned_count: page.length, total_count: total, offset,
            sharia_only: Boolean(args.sharia_only),
            performance_summary: legacy.performance_summary,
            next_offset: truncated ? offset + page.length : null, truncated, is_page: offset > 0 || page.length < total, sources_complete: completeSources,
            source_counts: { model_signals: legacy.total_count, short_swings: shortAvailable ? shorts.length : null },
            status_filter: status, timeframe, access: access.isPro ? 'pro' : 'free',
            locked_count: all.filter(r => r.is_locked).length,
            snapshot_date: shortAvailable ? swings.as_of : null,
            latest_recommendation_date: legacy.latest_recommendation_date,
            latest_returned_quote_date: [legacy.latest_returned_quote_date, shortAvailable ? swings.as_of : null].filter(Boolean).sort().at(-1) || null,
            note: `${access.isPro ? 'المصادر المنشورة متاحة للبرو دون تشفير.' : 'التوصيات الحديثة المحمية تظل مشفرة وفق صلاحية الحساب.'} ${offset > 0 || page.length < total ? `معروض ${page.length} من إجمالي ${total} توصية مطابقة للفترة؛ اذكر ملخص الأداء الإحصائي (نسبة النجاح ومتوسط العائد) ثم اعرض الصفقات البارزة المعروضة في جدول دون محاولة سرد كل الصفقات.` : 'اذكر الإحصاءات والصفقات المعروضة بدقة.'} ${!completeSources ? 'تعذر إكمال مصدر أو تجاوز المصدر القديم حد القراءة؛ هذه نتائج جزئية وليست كل التوصيات.' : ''} سعر الدخول الفعلي منفصل عن الإشارة المعلقة؛ تاريخ التوصية منفصل عن تاريخ السعر.` };
    }
    if (readBatches.has(name) && Array.isArray(args.symbols) && args.symbols.length > 10) {
        if (args.symbols.length > 30) return { status: 'error', availability: 'error', message: 'الطلب يتجاوز الحد المسموح 30 رمزًا؛ قسم الطلب.' };
        const results = [];
        for (let i = 0; i < args.symbols.length; i += 10)
            results.push(await executeAgenticTool(name, { ...args, symbols: args.symbols.slice(i, i + 10) }, db, userId, cache));
        const field = name === 'get_stock_levels' ? 'levels' : name === 'get_comparison' ? 'comparison' : 'stocks';
        const failed = results.filter(r => r.status !== 'success');
        return { status: failed.length === results.length ? 'error' : 'success', availability: failed.length ? 'partial' : results.some(r => r.availability === 'partial' || r.availability === 'missing') ? 'partial' : 'available',
            [field]: results.flatMap(r => r[field] || []), requested_symbols: args.symbols,
            batches: results.length, failed_batches: failed.length, note: failed.length ? 'بعض دفعات البيانات تعذرت؛ أجب من الناجح وحدد الرموز الناقصة.' : 'جُمعت قائمة الرموز على دفعات ضمن حد الأداة دون حفظ محفظة.' };
    }
    return executeAgenticTool(name, args, db, userId, cache);
}

export function recommendationVisibility(row: any, isPro: boolean, now = new Date()): any {
    if (isPro) return { ...row, is_locked: false };
    const cutoff = new Date(now.getTime() - 15 * 86400000);
    const date = Date.parse(row.signal_date || '');
    const closed = ['win', 'loss', 'closed'].includes(row.status);
    const exitDate = Date.parse(row.closed_date || '');
    const recent = !Number.isFinite(date) || date > cutoff.getTime()
        || closed && row.source_kind === 'model_signals' && (!Number.isFinite(exitDate) || exitDate > cutoff.getTime());
    const highReturn = row.source_kind === 'model_signals' && !closed && Number(row.unrealized_return_pct) > 50;
    const locked = row.source_kind === 'short_swings' ? !closed && (recent || row.is_pending_entry) : recent || highReturn;
    if (!locked) return { ...row, is_locked: false };
    return { source_kind: row.source_kind, recommendation_type: row.recommendation_type, symbol: null,
        status: row.status, signal_date: row.signal_date, is_locked: true, note: 'تفاصيل التوصية متاحة للبرو؛ لا تستنتج الرمز أو المستويات.' };
}
