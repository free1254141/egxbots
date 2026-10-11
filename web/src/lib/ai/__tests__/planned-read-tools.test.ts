import {executeAgenticTool} from '../agentic-tools';
import {executePlannedReadTool,PLANNED_READ_TOOLS_SCHEMA} from '../planned-read-tools';
import {toAgenticEvidence,checkAgenticDraft,safeAgenticFallback} from '../agentic-publication';
function db(rows:any[],error:any=null) {
 const queries:any[]=[];
 return {queries,client:{from:(table:string)=>{const q={table,ops:[] as any[]};queries.push(q);const chain:any=new Proxy({}, {get:(_,key)=>key==='then'?(yes:any,no:any)=>Promise.resolve({data:rows,error}).then(yes,no):(...args:any[])=>{q.ops.push([key,...args]);return chain;}});return chain;}}};
}
const f=[{symbol:'COMI',name:'CIB',updated_at:'2026-07-05T10:00:00Z',data:{peRatio:7.02499,eps:19.255,marketCap:449265492676,sector:'Finance',industry:'Regional Banks'}},{symbol:'ADIB',updated_at:'2026-07-05',data:{sector:'Finance',industry:'Regional Banks',peRatio:null,eps:null}},{symbol:'HRHO',data:{sector:'Finance',industry:'Investment Banks/Brokers'}}];
test('new catalog has three distinct read tools',()=>{expect(PLANNED_READ_TOOLS_SCHEMA.map(t=>t.function.name)).toEqual(['get_fundamentals','get_sector_peers','get_market_breadth']);});
test('fundamentals preserve dates, units, missing fields and missing symbols with one read',async()=>{
 const d=db(f);const r=await executePlannedReadTool('get_fundamentals',{symbols:['comi.ca','ZZZZ99']},d.client,'2026-10-11');
 expect(r.stocks[0]).toMatchObject({symbol:'COMI',pe_ratio:7.02499,eps:19.255,date:'2026-07-05',financial_period:null,stale:true});
 expect(r.stocks[1].availability).toBe('missing');expect(r.availability).toBe('partial');
 expect(r.stocks[0].missing_fields).toContain('price_to_book');expect(r.stocks[0]).not.toHaveProperty('dividend_yield_pct');
 expect(d.queries).toHaveLength(1);expect(d.queries[0].ops).toContainEqual(['limit',10]);expect(d.queries[0].ops.find((o:any)=>o[0]==='select')[1]).not.toContain('*');
 const e=toAgenticEvidence('get_fundamentals',{symbols:['COMI']},r);expect(e.availability).toBe('partial');expect(e.source).toBe('supabase:stock_fundamentals');
});
test('peers share actual industry, not the broad Finance classification',async()=>{
 const d=db(f);const r=await executePlannedReadTool('get_sector_peers',{symbol:'COMI'},d.client,'2026-10-11');
 expect(r.classification_basis).toBe('industry');expect(r.stocks.map((s:any)=>s.symbol)).toEqual(['COMI','ADIB']);expect(r.displayed_peers).toBe(1);expect(d.queries).toHaveLength(1);expect(d.queries[0].ops).toContainEqual(['limit',501]);
});
test('peer absence and query cap are explicit',async()=>{
 expect((await executePlannedReadTool('get_sector_peers',{symbol:'ZZZZ99'},db(f).client,'2026-10-11')).availability).toBe('missing');
 expect((await executePlannedReadTool('get_sector_peers',{symbol:'COMI'},db([...f,...Array(498).fill({symbol:'X',data:{}})]).client,'2026-10-11')).scan_complete).toBe(false);
});
test('breadth uses one dated snapshot and excludes unknown changes instead of calling them flat',async()=>{
 const rows=[{symbol:'A',date:'2026-10-07',change_pct:2},{symbol:'B',date:'2026-10-07',change_pct:-1},{symbol:'C',date:'2026-10-07',change_pct:0},{symbol:'D',date:'2026-10-07',change_pct:null},{symbol:'E',date:'2026-10-06',change_pct:10}];
 const d=db(rows);const r=await executePlannedReadTool('get_market_breadth',{},d.client,'2026-10-11');
 expect(r.stocks[0]).toMatchObject({date:'2026-10-07',breadth_total:3,breadth_advancing:1,breadth_declining:1,breadth_unchanged:1,breadth_ad_ratio:1});expect(r.stocks[0].breadth_advancing_pct).toBeCloseTo(100/3);expect(r.excluded_missing_change).toBe(1);expect(r.availability).toBe('partial');expect(d.queries).toHaveLength(1);expect(d.queries[0].ops).toContainEqual(['limit',1000]);
});
test('no declining stocks cannot create an infinite ratio and incomplete scans stay partial',async()=>{
 const r=await executePlannedReadTool('get_market_breadth',{},db(Array.from({length:1000},(_,i)=>({symbol:String(i),date:'2026-10-07',change_pct:1}))).client,'2026-10-11');
 expect(r.stocks[0].breadth_ad_ratio).toBeNull();expect(r.scan_complete).toBe(false);expect(r.availability).toBe('partial');
});
test.each(['get_fundamentals','get_market_breadth','get_sector_peers'])('database failures never masquerade as no data: %s',async name=>{
 const r=await executeAgenticTool(name,{symbols:['COMI'],symbol:'COMI'},db([],new Error('denied')).client,'user');expect(r.status).toBe('error');expect(r.availability).toBe('error');
});
test('new tools enforce required inputs without database reads',async()=>{
 const d=db([]);expect((await executeAgenticTool('get_fundamentals',{symbols:[]},d.client,'user')).status).toBe('error');
 expect((await executeAgenticTool('get_sector_peers',{symbol:'COMI',max_results:100},d.client,'user')).status).toBe('error');expect(d.queries).toHaveLength(0);
});
test('new numeric metrics bind by symbol and field, not just to any number in a row',async()=>{
 const r=await executePlannedReadTool('get_fundamentals',{symbols:['COMI']},db(f).client,'2026-10-11');const e=[toAgenticEvidence('get_fundamentals',{symbols:['COMI']},r)];
 const draft='COMI\n| المقياس | القيمة |\n|---|---|\n| مضاعف الربحية | 7.02 |\n| ربحية السهم | 19.255 |\n| القيمة السوقية للشركة | 449265492676 |';
 expect(checkAgenticDraft(draft,e)).toEqual([]);
 expect(checkAgenticDraft(draft.replace('19.255','7.02'),e)).toContain('table_value_not_grounded:COMI:7.02');
});

test('fundamental currency prose cannot borrow another field',async()=>{
 const r=await executePlannedReadTool('get_fundamentals',{symbols:['COMI']},db(f).client,'2026-10-11');const e=[toAgenticEvidence('get_fundamentals',{symbols:['COMI']},r)];
 expect(checkAgenticDraft('COMI ربحية السهم 19.255 جنيه.',e)).toEqual([]);
 expect(checkAgenticDraft('COMI القيمة السوقية للشركة 449265492676 جنيه.',e)).toEqual([]);
 expect(checkAgenticDraft('COMI ربحية السهم 7.02 جنيه.',e).length).toBeGreaterThan(0);
});

test('verified new-tool evidence has a useful recovery with missing values, not fabricated zeroes',async()=>{
 const r=await executePlannedReadTool('get_fundamentals',{symbols:['COMI','ADIB']},db(f).client,'2026-10-11');const e=[toAgenticEvidence('get_fundamentals',{symbols:['COMI','ADIB']},r)];
 const reply=safeAgenticFallback(e,'ignored');expect(reply).toContain('19.255');expect(reply).toContain('غير متاح');expect(reply).not.toContain('تعذر إكمال');expect(checkAgenticDraft(reply,e)).toEqual([]);
});

test('short market cap labels bind company snapshots',async()=>{
 const r=await executePlannedReadTool('get_fundamentals',{symbols:['COMI']},db(f).client,'2026-10-11');const e=[toAgenticEvidence('get_fundamentals',{symbols:['COMI']},r)];
 expect(checkAgenticDraft('COMI\n| الحقل | القيمة |\n|---|---|\n| القيمة السوقية | 449,265,492,676 جنيه |',e)).toEqual([]);
 expect(checkAgenticDraft('| الرمز | القيمة السوقية (جنيه) |\n|---|---|\n| COMI | 449,265,492,676 |',e)).toEqual([]);
 expect(checkAgenticDraft('| الرمز | القيمة السوقية |\n|---|---|\n| COMI | 19.255 |',e)).toContain('table_value_not_grounded:COMI:19.255');
});
