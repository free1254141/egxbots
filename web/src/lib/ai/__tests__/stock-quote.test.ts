import {executeAgenticTool} from '../agentic-tools';
import {reconcileStockQuote} from '../stock-quote';
import {presentReplyLabels} from '../reply-labels';

jest.mock('../live-stock-updater', () => ({
    ...jest.requireActual('../live-stock-updater'),
    fetchLiveStockIndicators: jest.fn().mockResolvedValue({ success: false, error: 'offline' }),
    isEgxSessionOpen: jest.fn().mockReturnValue(false)
}));

function db(rows: Record<string, any[]>) {
    const queries: any[] = [];
    const client = {from(table: string) {
        const ops: any[] = []; queries.push({table,ops});
        const chain: any = new Proxy({}, {get:(_,key:string)=>key==='then'
            ? (yes:any,no:any)=>Promise.resolve({data:rows[table] || [],error:null}).then(yes,no)
            : (...args:any[])=>{ops.push([key,...args]);return chain;}});
        return chain;
    }};
    return {client,queries};
}
const snapshot={symbol:'GTWL',date:'2026-10-11',close:153.2,change_pct:-4.25,rsi_14:24.64,ema_50:178.82};
const prices=[{date:'2026-10-11',close:146.9},{date:'2026-10-07',close:160}];

test.each(['get_stock','get_comparison'])('%s uses price candles when same-day indicators disagree',async tool=>{
    const d=db({stock_prices:prices,stock_technical_indicators:[snapshot]});
    const result=await executeAgenticTool(tool,{symbols:['GTWL']},d.client,'offline-user');
    const row=(result.stocks || result.comparison)[0];
    expect(row).toMatchObject({symbol:'GTWL',close:146.9,date:'2026-10-11',quote_source:'stock_prices',indicators_stale:true});
    expect(row.rsi_14).toBeNull();expect(row.ema_50).toBeNull();
    expect(row.change_pct).toBeCloseTo(-8.1875,tool==='get_stock'?1:5);
    expect(d.queries.every(q=>q.ops.some((op:any[])=>op[0]==='limit'))).toBe(true);
    expect(d.queries.every(q=>!q.ops.some((op:any[])=>op[0]==='select'&&op[1]==='*'))).toBe(true);
});

test('corrected quantity is valued at the price table without writing a saved center',async()=>{
    const d=db({stock_prices:prices,stock_technical_indicators:[snapshot]});
    const result=await executeAgenticTool('calculate_position',{symbol:'GTWL',quantity:2114,entry_price:73.82},d.client,'offline-user');
    expect(result).toMatchObject({status:'success',persisted:false});
    expect(result.positions[0]).toMatchObject({close:146.9,quantity:2114,entry_price:73.82,cost:156055.48,market_value:310546.6,profit_loss_val:154491.12,profit_loss_pct:99});
    expect(d.queries.some(q=>q.ops.some((op:any[])=>['insert','update','delete','upsert'].includes(op[0])))).toBe(false);
});

test('saved portfolio and temporary positions use the same freshest close',async()=>{
    const d=db({stock_prices:prices,stock_technical_indicators:[snapshot],positions:[{symbol:'GTWL',quantity:1934,entry_price:63.9}]});
    const result=await executeAgenticTool('manage_portfolio',{operation:'view'},d.client,'offline-user');
    expect(result.positions[0]).toMatchObject({current_price:146.9,indicators_stale:true,rsi:null});
});

test('an older price table does not replace a newer indicator close',async()=>{
    const d=db({stock_prices:[{date:'2026-10-07',close:160}]});
    expect(await reconcileStockQuote(d.client,'GTWL',snapshot,{preferLive:false})).toMatchObject({close:153.2,date:'2026-10-11',indicators_stale:false});
});

test('a current matching indicator snapshot retains its indicators',async()=>{
    const d=db({stock_prices:prices});
    expect(await reconcileStockQuote(d.client,'GTWL',{...snapshot,close:146.9},{preferLive:false})).toMatchObject({rsi_14:24.64,indicators_stale:false,close:146.9});
});

test('prices still return when indicators have not been calculated',async()=>{
    const d=db({stock_prices:prices});
    const row=await reconcileStockQuote(d.client,'GTWL',null,{preferLive:false});
    expect(row).toMatchObject({close:146.9,indicators_available:false,indicators_date:null});
});

test('presentation translates field keys without changing stock symbols or numbers',()=>{
    expect(presentReplyLabels('GTWL king_ai_score = 0.51; accumulation_score 10; momentum_and_volume'))
        .toBe('GTWL تقييم KING = 0.51; درجة التجميع 10; الزخم والنشاط النسبي');
    expect(presentReplyLabels('MACD وRSI وGTWL وtrend_macd')).toBe('MACD وRSI وGTWL وtrend_macd');
});
