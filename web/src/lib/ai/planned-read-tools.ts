/** Additive, read-only tools. No writes, external refreshes or changes to existing tools. */
export const PLANNED_READ_TOOL_NAMES = new Set(['get_fundamentals', 'get_sector_peers', 'get_market_breadth']);
const symbolsParameter = {type:'array',items:{type:'string'},minItems:1,maxItems:10};
export const PLANNED_READ_TOOLS_SCHEMA = [
 {type:'function',function:{name:'get_fundamentals',description:'قراءة البيانات الأساسية المخزنة: مضاعف الربحية وربحية السهم والقيمة السوقية والتصنيف. وضح تاريخ تحديث اللقطة والحقول الناقصة؛ ليست قوائم مالية حديثة ولا تاريخ فترة مالية. لا تستنتج مضاعف الدفترية أو نمو الإيرادات عند غيابهما.',parameters:{type:'object',properties:{symbols:symbolsParameter},required:['symbols']}}},
 {type:'function',function:{name:'get_sector_peers',description:'نظراء السهم من تصنيف الصناعة المخزن (أو القطاع عند غياب الصناعة) مع البيانات الأساسية المتاحة وتاريخها. التصنيف العام Finance لا يعني البنوك. لا تقدم ترتيب شراء أو تقييماً للأرخص من بيانات قديمة أو ناقصة.',parameters:{type:'object',properties:{symbol:{type:'string'},max_results:{type:'integer',minimum:1,maximum:10,description:'عدد النظراء فقط، لا يشمل السهم الأصلي. لثلاثة نظراء استخدم 3؛ السهم الأصلي يضاف تلقائياً.'}},required:['symbol']}}},
 {type:'function',function:{name:'get_market_breadth',description:'اتساع وسيولة أحدث جلسة يومية مخزنة للأسهم ذات تغير سعري صالح: صاعد/هابط/ثابت ونسبة الصاعدة ونسبة الصاعد إلى الهابط، مع إجمالي قيمة التداول بالجنيه وتوزيع السيولة بين الأسهم الصاعدة والهابطة ومقارنتها بمتوسط 20 جلسة وأعلى الأسهم سيولة. ليس بيانات لحظية ولا عضوية مؤشر EGX30 ولا صافي شراء مؤسسي.',parameters:{type:'object',properties:{}}}},
];
const number = (v:unknown):number|null => typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null;
const normalize = (v:unknown) => String(v).trim().toUpperCase().replace(/\.CA$/i,'');
const limit = (v:unknown, fallback:number) => {if(v == null)return fallback;if(!Number.isInteger(v)||Number(v)<1||Number(v)>10)throw new Error('عدد النتائج يجب أن يكون بين 1 و10');return Number(v);};
const symbols = (args:any) => {if(!Array.isArray(args.symbols)||!args.symbols.length||args.symbols.length>10)throw new Error('أدخل من 1 إلى 10 رموز');return [...new Set<string>(args.symbols.map(normalize))];};
function fundamental(row:any, today:string) {
 const d = row.data && typeof row.data === 'object' ? row.data : {};
 const observed = typeof row.updated_at === 'string' ? row.updated_at.slice(0,10) : null;
 const stale = !observed || !Number.isFinite(Date.parse(observed)) || observed > today || (Date.parse(today)-Date.parse(observed))/86400000 > 90;
 const metrics = {pe_ratio:number(d.peRatio),eps:number(d.eps),market_cap:number(d.marketCap)};
 return {symbol:row.symbol,name:row.name_ar||row.name||d.name||null,sector:d.sector||null,industry:d.industry||null,...metrics,
   date:observed,snapshot_updated_at:row.updated_at||null,financial_period:null,stale,
   missing_fields:[...Object.keys(metrics).filter(k=>metrics[k as keyof typeof metrics] == null),'price_to_book','revenue_growth_pct'],
   availability:stale||Object.values(metrics).some(v=>v==null)?'partial':'available'};
}
export async function executePlannedReadTool(name:string,args:any,db:any,today:string):Promise<any> {
 if(name==='get_fundamentals') {
  const requested=symbols(args);
  const {data,error}=await db.from('stock_fundamentals').select('symbol,name,name_ar,data,updated_at').eq('exchange','EGX').in('symbol',requested).limit(10);
  if(error)throw new Error('تعذر قراءة البيانات الأساسية');
  const stocks=requested.map(symbol=>{const row=(data||[]).find((r:any)=>r.symbol===symbol);return row?fundamental(row,today):{symbol,availability:'missing',missing_fields:['all_fundamentals'],date:null};});
  return {status:'success',availability:stocks.every(r=>r.availability==='missing')?'missing':stocks.some(r=>r.availability!=='available')?'partial':'available',stocks,
   limitations:['تاريخ تحديث السجل لا يثبت تاريخ الفترة المالية أو حداثة التقييم.','لا تتوفر مضاعفات الدفترية أو نمو الإيرادات من هذا المصدر.']};
 }
 if(name==='get_sector_peers') {
  if(!args.symbol)throw new Error('رمز السهم مطلوب');
  const symbol=normalize(args.symbol),max=limit(args.max_results,5);
  const {data,error}=await db.from('stock_fundamentals').select('symbol,name,name_ar,data,updated_at').eq('exchange','EGX').order('symbol',{ascending:true}).limit(501);
  if(error)throw new Error('تعذر قراءة تصنيف النظراء');
  const rows=data||[], target=rows.find((r:any)=>r.symbol===symbol);
  if(!target)return {status:'success',availability:'missing',symbol,stocks:[],reason:'لا يوجد تصنيف موثق للرمز في العينة المخزنة.'};
  const basis=target.data?.industry?'industry':target.data?.sector?'sector':null;
  if(!basis)return {status:'success',availability:'missing',symbol,stocks:[fundamental(target,today)],reason:'تصنيف الصناعة والقطاع غير متاح.'};
  const peers=rows.filter((r:any)=>r.symbol!==symbol && r.data?.[basis]===target.data[basis] && r.data?.isListed!==false);
  return {status:'success',availability:'partial',symbol,classification_basis:basis,classification:target.data[basis],
   stocks:[{...fundamental(target,today),role:'target'},...peers.slice(0,max).map((r:any)=>({...fundamental(r,today),role:'peer'}))],
   requested_peers:max,peers_found_in_snapshot:peers.length,displayed_peers:Math.min(peers.length,max),scan_complete:rows.length<501,
   limitations:['نظراء التصنيف المخزن وليسوا قائمة شراء أو ترتيب قيمة عادلة.','التغطية والتواريخ تخص المصدر المخزن؛ التصنيف القطاعي العام قد يجمع صناعات مختلفة.']};
 }
 if(name==='get_market_breadth') {
  const {data,error}=await db.from('stock_technical_indicators').select('symbol,date,change_pct,close,volume,vol_sma20,r_vol,cmf_20,rsi_14').eq('exchange','EGX').order('date',{ascending:false}).order('symbol',{ascending:true}).limit(1000);
  if(error)throw new Error('تعذر قراءة اتساع السوق');
  const rows=data||[],date=rows[0]?.date;
  if(!date)return {status:'success',availability:'missing',stocks:[],reason:'لا توجد جلسة مخزنة لحساب الاتساع.'};
  const latest=[...new Map(rows.filter((r:any)=>r.date===date).map((r:any)=>[r.symbol,r])).values()] as any[];
  const valid=latest.filter(r=>number(r.change_pct)!==null),advancing=valid.filter(r=>number(r.change_pct)!>0).length,declining=valid.filter(r=>number(r.change_pct)!<0).length;
  const complete=rows.length<1000||rows[rows.length-1].date!==date;
  let totalTurnover=0,avg20dTurnover=0,advTurnover=0,decTurnover=0,unchTurnover=0,surgeCount=0,posCmfCount=0,negCmfCount=0;
  const turnoverRows:any[]=[];
  for(const r of valid){
   const c=number(r.close),v=number(r.volume),v20=number(r.vol_sma20),chg=number(r.change_pct)!,rv=number(r.r_vol),cmf=number(r.cmf_20),rsi=number(r.rsi_14);
   if(rv!==null&&rv>=2)surgeCount++;
   if(cmf!==null&&cmf>0.05)posCmfCount++;
   if(cmf!==null&&cmf<-0.05)negCmfCount++;
   if(c!==null&&c>0&&v!==null&&v>0){
    const tv=c*v;
    totalTurnover+=tv;
    if(v20!==null&&v20>0)avg20dTurnover+=c*v20;
    if(chg>0)advTurnover+=tv;
    else if(chg<0)decTurnover+=tv;
    else unchTurnover+=tv;
    turnoverRows.push({symbol:r.symbol,date,close:c,change_pct:chg,volume:Math.round(v),turnover_egp:Math.round(tv),turnover_million_egp:Number((tv/1e6).toFixed(2)),r_vol:rv,rsi_14:rsi,cmf_20:cmf});
   }
  }
  turnoverRows.sort((a,b)=>b.turnover_egp-a.turnover_egp);
  const topTurnover=totalTurnover>0?turnoverRows.slice(0,10).map(item=>({...item,market_share_pct:Number(((item.turnover_egp/totalTurnover)*100).toFixed(2))})):[];
  const top5Share=totalTurnover>0?Number(((turnoverRows.slice(0,5).reduce((s,x)=>s+x.turnover_egp,0)/totalTurnover)*100).toFixed(2)):null;
  const top10Share=totalTurnover>0?Number(((turnoverRows.slice(0,10).reduce((s,x)=>s+x.turnover_egp,0)/totalTurnover)*100).toFixed(2)):null;
  const liquidityFields=totalTurnover>0?{
   total_turnover_egp:Math.round(totalTurnover),
   total_turnover_million_egp:Number((totalTurnover/1e6).toFixed(2)),
   total_turnover_billion_egp:Number((totalTurnover/1e9).toFixed(3)),
   avg_20d_turnover_egp:avg20dTurnover>0?Math.round(avg20dTurnover):null,
   avg_20d_turnover_million_egp:avg20dTurnover>0?Number((avg20dTurnover/1e6).toFixed(2)):null,
   turnover_vs_20d_ratio:avg20dTurnover>0?Number((totalTurnover/avg20dTurnover).toFixed(2)):null,
   turnover_vs_20d_pct:avg20dTurnover>0?Number(((totalTurnover/avg20dTurnover)*100).toFixed(2)):null,
   advancing_turnover_egp:Math.round(advTurnover),
   advancing_turnover_million_egp:Number((advTurnover/1e6).toFixed(2)),
   advancing_turnover_pct:Number(((advTurnover/totalTurnover)*100).toFixed(2)),
   declining_turnover_egp:Math.round(decTurnover),
   declining_turnover_million_egp:Number((decTurnover/1e6).toFixed(2)),
   declining_turnover_pct:Number(((decTurnover/totalTurnover)*100).toFixed(2)),
   unchanged_turnover_egp:Math.round(unchTurnover),
   unchanged_turnover_million_egp:Number((unchTurnover/1e6).toFixed(2)),
   unchanged_turnover_pct:Number(((unchTurnover/totalTurnover)*100).toFixed(2)),
   top5_concentration_pct:top5Share,
   top10_concentration_pct:top10Share,
   unusual_volume_surge_count:surgeCount,
   positive_cmf_count:posCmfCount,
   negative_cmf_count:negCmfCount,
  }:{};
  const stats={symbol:'EGX',date,breadth_total:valid.length,breadth_advancing:advancing,breadth_declining:declining,breadth_unchanged:valid.length-advancing-declining,
    breadth_advancing_pct:valid.length?100*advancing/valid.length:null,breadth_ad_ratio:declining?advancing/declining:null,...liquidityFields};
  return {status:'success',availability:!valid.length?'missing':!complete||valid.length!==latest.length?'partial':'available',date,stocks:[stats],...(totalTurnover>0?{liquidity_summary:liquidityFields,top_liquidity_stocks:topTurnover}:{}),
   scan_complete:complete,excluded_missing_change:latest.length-valid.length,coverage:'أسهم أحدث جلسة مخزنة ذات تغير سعري صالح؛ ليست جميع الأوراق أو عضوية مؤشر بعينه.',
   limitations:['نسبة الصاعدة = الصاعدة ÷ إجمالي الأسهم ذات تغير صالح ×100.','نسبة الصاعد إلى الهابط غير متاحة إذا كان عدد الهابطة صفراً.','ليس سعراً لحظياً أو صافي شراء مؤسسي.']};
 }
 throw new Error('أداة قراءة غير مدعومة');
}

export function renderPlannedReadEvidence(name:string,data:any):string|null {
 if(!PLANNED_READ_TOOL_NAMES.has(name)||data?.status!=='success'||!data.stocks?.length||data.availability==='missing')return null;
 const show=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?String(Number(v.toFixed(3))):'غير متاح';
 if(name==='get_market_breadth'){
  const r=data.stocks[0];return [`اتساع العينة اليومية EGX بتاريخ ${r.date}:`, '| المقياس | القيمة |','|---|---|',
   `| إجمالي الأسهم ذات تغير صالح | ${show(r.breadth_total)} |`,`| الأسهم الصاعدة | ${show(r.breadth_advancing)} |`,`| الأسهم الهابطة | ${show(r.breadth_declining)} |`,`| الأسهم الثابتة | ${show(r.breadth_unchanged)} |`,
   `| نسبة الأسهم الصاعدة % | ${show(r.breadth_advancing_pct)} |`,`| نسبة الصاعد إلى الهابط | ${show(r.breadth_ad_ratio)} |`,data.coverage,...data.limitations,
   ...(data.scan_complete===false?['التغطية جزئية بسبب حد القراءة.']:[])].join('\n');
 }
 return ['بيانات أساسية من اللقطة المخزنة، وليست تقييماً حديثاً أو قائمة شراء:',
  '| السهم | مضاعف الربحية | ربحية السهم | القيمة السوقية للشركة | تاريخ تحديث اللقطة | الصناعة |','|---|---:|---:|---:|---|---|',
  ...data.stocks.map((r:any)=>`| ${r.symbol} | ${show(r.pe_ratio)} | ${show(r.eps)} | ${show(r.market_cap)} | ${r.date||'غير متاح'} | ${r.industry||'غير متاح'} |`),
  ...(name==='get_sector_peers'?[`عدد النظراء المعروض ${data.displayed_peers}؛ الأصل يضاف منفصلاً. التصنيف ${data.classification_basis==='industry'?'صناعة':'قطاع'}: ${data.classification||'غير متاح'}.`,...(data.displayed_peers < (data.requested_peers||0)?['المصدر لا يحتوي العدد المطلوب من النظراء ضمن التصنيف؛ لم نضف شركات من صناعة مختلفة.']:[])]:[]),
  'القيم النقدية بالجنيه. تاريخ تحديث السجل ليس فترة القوائم المالية؛ مضاعف الدفترية ونمو الإيرادات غير متاحين. اللقطات القديمة لا تصلح وحدها لتقييم اليوم.',
  ...(data.limitations||[])].join('\n');
}
