import { advisoryFactRelations } from '../fact-relations';
import { toAgenticEvidence } from '../agentic-publication';

const stock = (symbol: string, data: Record<string, unknown>) => toAgenticEvidence('get_stock', {symbols: [symbol]}, {stocks: [{symbol, date: '2026-10-13', ...data}]});
const f = stock('FWRY', {macd: -0.077, macd_signal: -0.086});
const e = stock('EPPK', {entry_price: 9.78, current_price: 9.78, current_date: '2026-10-13'});
const older = stock('EITP', {current_date: '2026-10-12', entry_price: 8.2, current_price: 8});

test('negative MACD comparison is scoped to its own claim', () => {
    expect(advisoryFactRelations('FWRY: MACD تحت الإشارة.', [f])[0]).toContain('-0.077 مقابل -0.086');
    expect(advisoryFactRelations('FWRY: MACD فوق الإشارة، والاثنان تحت الصفر.', [f])).toEqual([]);
    expect(advisoryFactRelations('FWRY: السعر تحت EMA50؛ MACD فوق الإشارة.', [f])).toEqual([]);
});
test('Arabic numerals are accepted without reversing negative values', () => {
    const values = stock('FWRY', {macd: '−٠٫٠٧٧', macd_signal: '−٠٫٠٨٦'});
    expect(advisoryFactRelations('FWRY: MACD تحت الإشارة.', [values])).toHaveLength(1);
});
test('a negated or conditional relationship is not an assertion', () => {
    expect(advisoryFactRelations('FWRY: MACD ليس تحت الإشارة. لو MACD تحت الإشارة يتغير السيناريو.', [f])).toEqual([]);
});
test('equal price endpoints cannot prove a return to entry', () => {
    expect(advisoryFactRelations('EPPK: السهم عاد إلى نقطة الدخول.', [e])[0]).toContain('عائداً حالياً صفراً');
    expect(advisoryFactRelations('EPPK: آخر سعر يساوي الدخول والعائد الحالي صفر.', [e])).toEqual([]);
    expect(advisoryFactRelations('EPPK: لا نقدر نقول رجع للدخول دون مسار الأسعار.', [e])).toEqual([]);
});
test('a recorded path avoids an endpoint-only suggestion', () => {
    expect(advisoryFactRelations('EPPK: رجع للدخول.', [stock('EPPK', {entry_price: 9.78, current_price: 9.78, history: [9.78, 10, 9.78]})])).toEqual([]);
});
test('symbols keep independent relationships', () => {
    const second = stock('CRST', {macd: -2, macd_signal: -1});
    expect(advisoryFactRelations('FWRY: MACD فوق الإشارة.\nCRST: MACD تحت الإشارة.', [f, second])).toEqual([]);
    expect(advisoryFactRelations('FWRY: MACD فوق الإشارة.\nCRST: MACD فوق الإشارة.', [f, second])).toHaveLength(1);
});
test('quote date comparison does not change the recommendation publication date', () => {
    const wrong = advisoryFactRelations('EITP: تاريخ آخر سعر أحدث من EPPK.', [e, older]);
    expect(wrong).toHaveLength(1);
    expect(wrong[0]).toContain('2026-10-12');
    expect(advisoryFactRelations('EPPK: تاريخ آخر سعر أحدث من EITP.', [e, older])).toEqual([]);
});
test('technical evidence cannot prove institutional buying', () => {
    expect(advisoryFactRelations('FWRY: السهم عليه تجميع مؤسسي مؤكد.', [f])).toHaveLength(1);
    expect(advisoryFactRelations('FWRY: التجميع لا يثبت شراء المؤسسات.', [f])).toEqual([]);
});
test('drawdown uses loss magnitude and retains ties', () => {
    const compare = toAgenticEvidence('compare_strategies_history', {}, {symbol: 'CRST', date: '2026-10-13', strategy_metrics: [
        {strategy_id: 'SMC', maxDrawdownPct: 12.75}, {strategy_id: 'MACD', maxDrawdownPct: 40.5},
        {strategy_id: 'Wyckoff', maxDrawdownPct: -12.75}
    ]});
    expect(advisoryFactRelations('CRST: MACD هي الأقل هبوطاً.', [compare])[0]).toContain('SMC و Wyckoff');
    expect(advisoryFactRelations('CRST: SMC هي الأقل هبوطاً مع تعادل Wyckoff.', [compare])).toEqual([]);
});
test('latest dated snapshot replaces older values without contamination', () => {
    const prior = stock('FWRY', {date: '2026-10-12', macd: -2, macd_signal: -1});
    expect(advisoryFactRelations('FWRY: MACD فوق الإشارة.', [f, prior])).toEqual([]);
    expect(advisoryFactRelations('MACD تحت الإشارة.', [])).toEqual([]);
});
