import { executeRequestTool, knownSymbolHints, requestToolCost, recommendationVisibility } from '../request-data-tools';
import { advisoryFactRelations } from '../fact-relations';
import { checkAgenticDraft, safeAgenticFallback, toAgenticEvidence } from '../agentic-publication';
import { AGENTIC_TOOLS_SCHEMA } from '../agentic-pipeline';

function database(legacy:any[]=[], active:any[]=[], closed:any[]=[], unavailable=false) {
    const operations:any[]=[];
    const db={from:(table:string)=>{
        const state:any={table,eq:[],ins:[],limit:0,select:'',head:false};
        const chain:any=new Proxy({}, {get:(_,key)=>{
            if(key==='then')return (resolve:any)=>{
                operations.push({...state});
                let data:any[]=[],count:number|undefined,error:any=null;
                if(table==='scan_results'){
                    data=legacy.filter(r=>state.ins.every(([field,vals]:any[])=>vals.includes(r[field])));
                    if(state.head){count=data.length;data=[];}else data=data.slice(0,state.limit||200);
                } else if(table==='short_swing_checkpoints') {
                    data=unavailable?[]:[{payload:{swings:{status:'ok',as_of:'2026-10-13',active_trades:active,closed_trades:closed}}}];
                    if(unavailable)error={message:'read unavailable'};
                } else if(table==='stock_technical_indicators')data=[{close:9.78,date:'2026-10-13'}];
                else if(table==='stock_fundamentals')data=state.ins[0][1].map((symbol:string)=>({symbol,updated_at:new Date().toISOString(),data:{peRatio:5,eps:2,marketCap:100}}));
                else if(table==='corporate_actions')data=[{symbol:'KORA',action_type:'capital_increase',title:'زيادة رأس المال',published_at:'2026-10-10',action_date:null,url:'https://news.example/article',source:'news'}];
                return Promise.resolve({data,count,error}).then(resolve);
            }
            return (...args:any[])=>{if(key==='select'){state.select=args[0];state.head=args[1]?.head===true;} if(key==='eq')state.eq.push(args);if(key==='in')state.ins.push(args);if(key==='limit')state.limit=args[0];return chain;};
        }});return chain;
    }};
    return {db,operations};
}
const legacy=[{id:'r1',symbol:'EPPK',entry_price:9.78,status:'open',created_at:'2026-09-17',updated_at:'2026-09-17'},
 {id:'r2',symbol:'EITP',entry_price:8.2,status:'open',created_at:'2026-09-17',updated_at:'2026-09-17'}];
const short={signal_id:'AJWA_2026-10-06',symbol:'AJWA',entry_price:197.736,signal_date:'2026-10-06',entry_date:'2026-10-07',
 current_price:208.92,price_date:'2026-10-13',trailing_stop:198.329,return_pct:5.66};

test('Pro receives every open published source and the actual trailing stop',async()=>{
 const {db,operations}=database(legacy,[short]);
 const result=await executeRequestTool('get_recommendations',{status:'open'},db,'u',new Map(),{isPro:true});
 expect(result).toMatchObject({total_count:3,returned_count:3,truncated:false,sources_complete:true,source_counts:{model_signals:2,short_swings:1}});
 expect(result.recommendations.map((r:any)=>r.symbol).sort()).toEqual(['AJWA','EITP','EPPK']);
 expect(result.recommendations.find((r:any)=>r.symbol==='AJWA')).toMatchObject({entry_price:197.736,stop_loss:198.329,signal_date:'2026-10-06',current_date:'2026-10-13',target_price:null,is_locked:false});
 expect(operations.filter(q=>q.table==='scan_results'&&q.select.includes('entry_price'))[0].eq).toContainEqual(['is_public',true]);
});

test('tool arguments cannot grant Pro or leak a fresh short signal',async()=>{
 const {db}=database(legacy,[{...short,signal_date:new Date().toISOString().slice(0,10)}]);
 const result=await executeRequestTool('get_recommendations',{status:'open',is_pro:true},db,'u',new Map(),{isPro:false});
 expect(JSON.stringify(result)).not.toContain('AJWA');expect(JSON.stringify(result)).not.toContain('197.736');
 expect(result.recommendations.find((r:any)=>r.source_kind==='short_swings')).toMatchObject({symbol:null,is_locked:true});
});

test('missing short snapshot stays partial, never claims all recommendations',async()=>{
 const {db}=database(legacy,[],[],true);
 const result=await executeRequestTool('get_recommendations',{status:'open'},db,'u',new Map(),{isPro:true});
 expect(result).toMatchObject({availability:'partial',sources_complete:false,source_counts:{short_swings:null}});
 expect(result.note).toContain('نتائج جزئية');
});

test('history can be continued without claiming a page is the entire archive',async()=>{
 const history=Array.from({length:80},(_,i)=>({...short,signal_id:'h'+i,symbol:'AJWA',exit_date:'2026-10-12',exit_price:205,return_pct:4}));
 const {db}=database([],[],history);
 const first=await executeRequestTool('get_recommendations',{status:'closed',limit:50},db,'u',new Map(),{isPro:true});
 const second=await executeRequestTool('get_recommendations',{status:'closed',offset:first.next_offset,limit:50},db,'u',new Map(),{isPro:true});
 expect(first).toMatchObject({total_count:80,count:50,next_offset:50,truncated:true});
 expect(second).toMatchObject({total_count:80,count:30,next_offset:null,truncated:false});
 expect(new Set([...first.recommendations,...second.recommendations].map(r=>r.id)).size).toBe(80);
});

test('different sources on the same ticker are not deduplicated; pending entry is not executed',async()=>{
 const {db}=database([{...legacy[0],symbol:'AJWA'}],[{...short,is_pending_entry:true,reference_close:210}]);
 const result=await executeRequestTool('get_recommendations',{status:'open'},db,'u',new Map(),{isPro:true});
 expect(result.recommendations).toHaveLength(2);
 expect(result.recommendations.find((r:any)=>r.source_kind==='short_swings')).toMatchObject({entry_price:null,reference_close:210,unrealized_return_pct:null,is_pending_entry:true});
});

test('19 read-only symbols are gathered in two bounded batches without portfolio writes',async()=>{
 const requested=Array.from({length:19},(_,i)=>'SYM'+i); const {db,operations}=database();
 const result=await executeRequestTool('get_fundamentals',{symbols:requested},db,'u',new Map(),{isPro:true});
 expect(result.stocks.map((r:any)=>r.symbol)).toEqual(requested);expect(result.batches).toBe(2);
 expect(operations.map(q=>q.ins[0][1].length)).toEqual([10,9]);
 expect(requestToolCost('get_fundamentals',{symbols:requested})).toBe(2);
});

test('a 19-asset scenario can calculate a complete allocation without saving positions',async()=>{
 const requested=Array.from({length:19},(_,i)=>'SYM'+i), {db,operations}=database();
 const result=await executeRequestTool('analyze_portfolio_risk',{capital:400000,symbols:requested,allocation_mode:'equal'},db,'u',new Map(),{isPro:true});
 expect(result.status).toBe('success');expect(result.stocks).toHaveLength(19);
 expect(result.stocks.reduce((sum:number,r:any)=>sum+r.allocated_capital,0)).toBeCloseTo(400000,2);
 expect(operations.filter(q=>q.table==='stock_fundamentals')[0].limit).toBe(19);
 expect(result.persisted).toBe(false);
});

test('name hints identify Kima while preserving explicit ticker intent',()=>{
 expect(knownSymbolHints('سهم كيما')).toContainEqual({name:'كيما',symbols:['EGCH']});
 expect(knownSymbolHints('KIMA')).toEqual([]);
 expect(knownSymbolHints('كيماويات مصر').some(r=>r.symbols.includes('EGCH'))).toBe(false);
 const ajwaHints = knownSymbolHints('اجواء و الاسكندريه');
 expect(ajwaHints.some(h => h.symbols.includes('AJWA'))).toBe(true);
 expect(ajwaHints.some(h => h.symbols.includes('ALCN'))).toBe(true);
});

test('corporate-action news is available but never promoted to an official confirmation',async()=>{
 const {db}=database();const result=await executeRequestTool('get_corporate_actions',{symbols:['KORA'],action_type:'rights_issue'},db,'u',new Map(),{isPro:true});
 expect(result.stocks[0].events[0]).toMatchObject({official_source:false,date_kind:'publication_only'});
 expect(AGENTIC_TOOLS_SCHEMA.some(t=>t.function.name==='get_corporate_actions')).toBe(true);
});

test('AMER proximity is corrected without vetoing the supported answer',()=>{
 const e=toAgenticEvidence('get_stock_levels',{symbols:['AMER']},{levels:[{symbol:'AMER',close:4.75,support:4.05,resistance:5.77,date:'2026-10-13'}]});
 expect(advisoryFactRelations('AMER أقرب للمقاومة نسبياً.',[e])).toHaveLength(1);
 expect(advisoryFactRelations('AMER أقرب للدعم.',[e])).toEqual([]);
 expect(advisoryFactRelations('AMER ليس أقرب للمقاومة.',[e])).toEqual([]);
});

test('distribution score 30 is grounded in its own field, not portfolio allocation',()=>{
 const e=toAgenticEvidence('get_stock',{symbols:['ABUK']},{stocks:[{symbol:'ABUK',close:84.33,date:'2026-10-13',distribution_score:30,accumulation_score:0}]});
 const draft='ABUK\n| المؤشر | القيمة |\n|---|---|\n| درجة التوزيع | 30 |\n| درجة التجميع | 0 |';
 expect(checkAgenticDraft(draft,[e])).toEqual([]);
 expect(checkAgenticDraft(draft.replace('| 30 |','| 31 |'),[e])).toContain('table_value_not_grounded:ABUK:31');
 const fallback=safeAgenticFallback([toAgenticEvidence('get_stock',{}, {stocks:[{symbol:'ABUK',close:84.33,date:'2026-10-13',rsi_14:31.06,macd:0.093,macd_signal:0.997}]}),
  toAgenticEvidence('get_stock_levels',{}, {levels:[{symbol:'ABUK',close:84.33,date:'2026-10-13',support:83,resistance:96.29}]})],'');
 expect(fallback).toContain('القوة النسبية 31.06');expect(fallback).toContain('الدعم عند 83');expect(fallback).toContain('MACD تحت خط إشارته');expect(fallback).not.toContain('RSI =');
});

test('closed classic identity remains locked for Free within the settlement delay',()=>{
 const r=recommendationVisibility({source_kind:'model_signals',symbol:'PRIVATE',status:'win',signal_date:'2026-09-01',closed_date:'2026-10-13',entry_price:50},false,new Date('2026-10-14'));
 expect(r).toMatchObject({symbol:null,is_locked:true});expect(JSON.stringify(r)).not.toContain('PRIVATE');
});
