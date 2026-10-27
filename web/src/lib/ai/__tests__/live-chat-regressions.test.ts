import { sanitizeReply } from '../sanitizer';
import { executeAgenticTool } from '../agentic-tools';

test('MACD prose and the following markdown header survive final stream sanitization', () => {
    const paragraph = 'MACD أعلى من خط إشارته (-0.077 مقابل -0.086)، لكن القراءة وحدها لا تثبت اتجاهاً صاعداً.';
    const header = '| المستوى | السعر | المسافة من الإغلاق |';
    const reply = `# تحليل FWRY\n${paragraph}\n\n## القرب من الدعم والمقاومة\nالإغلاق: 18.63\n\n${header}\n|---|---|---|\n| الدعم | 17.50 | -6.07% |\n| المقاومة | 19.36 | +3.92% |`;
    const final = sanitizeReply(sanitizeReply(reply));
    expect(final).toContain(paragraph);
    expect(final).toContain(header);
    expect(final).toContain('الإغلاق: 18.63');
});

test('malformed stock rows are still removed without swallowing the next line', () => {
    const reply = 'BIOC محايد SIDEWAYS محايد STOCK تجميع |\nتحليل سليم محفوظ.';
    expect(sanitizeReply(reply)).not.toContain('SIDEWAYS');
    expect(sanitizeReply(reply)).toContain('تحليل سليم محفوظ.');
});

test('numbered English strategy metrics survive while English deliberation is removed', () => {
    const metric = '1. **SMC** — **10.56%**';
    const reply = `الترتيب حسب أقصى هبوط:\n${metric}\n2. الاتجاه وMACD — 17.55%\n\nI need to check the ranking before answering.\nLet me think about the numbers.`;
    const final = sanitizeReply(sanitizeReply(reply));
    expect(final).toContain(metric);
    expect(final).toContain('2. الاتجاه وMACD — 17.55%');
    expect(final).not.toContain('I need to');
    expect(final).not.toContain('Let me');
});

test('recommendation freshness includes returned quote dates and scopes each source', async () => {
    const results = [
        {data:[{symbol:'EPPK',entry_price:9.78,status:'open',created_at:'2026-09-17'}]},
        {count:1},
        {data:[{created_at:'2026-09-21'}]},
        {data:[]},
        {data:[{close:9.78,date:'2026-10-13'}]},
    ];
    const chain:any = new Proxy({}, {get:(_,key)=>key==='then'
        ? (resolve:any)=>Promise.resolve(results.shift()).then(resolve)
        : ()=>chain});
    const result = await executeAgenticTool('get_recommendations',{status:'open'},{from:()=>chain} as any,'u');
    expect(result).toMatchObject({
        latest_available_date_in_system:'2026-10-13',
        latest_recommendation_date:'2026-09-21',
        latest_returned_quote_date:'2026-10-13',
    });
    expect(result.date_scope).toContain('تاريخ التوصيات يشمل');
    expect(result.recommendations[0]).toMatchObject({signal_date:'2026-09-17',current_date:'2026-10-13'});
});
