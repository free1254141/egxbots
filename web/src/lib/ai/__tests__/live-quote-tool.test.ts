import {executeAgenticTool} from '../agentic-tools';
import {fetchLiveStockIndicators} from '../live-stock-updater';
import {toAgenticEvidence,checkAgenticDraft} from '../agentic-publication';
jest.mock('../live-stock-updater',()=>({fetchLiveStockIndicators:jest.fn(),isEgxSessionOpen:()=>false}));
const provider=fetchLiveStockIndicators as jest.Mock;
const db=()=>({from:()=>{
 const q:any=new Proxy({},{get:(_,key:string)=>key==='then'?(yes:any,no:any)=>Promise.resolve({data:[{date:'2026-10-07',close:160}],error:null}).then(yes,no):()=>q});return q;
}});
beforeEach(()=>provider.mockReset());

test('a newly retrieved quote carries retrieval time without inventing a trade time or guaranteed realtime',async()=>{
 provider.mockResolvedValue({success:true,data:{close:146.9,change_pct:-8.19,rsi_14:23.7,macd:-13,macd_signal:-5,updated_at:'2026-10-11T15:00:00Z'}});
 const r=await executeAgenticTool('get_live_quote',{symbols:['GTWL']},db(),'offline');
 expect(provider).toHaveBeenCalledWith('GTWL',undefined,{allowClosedMarket:true,forceRefresh:true});
 expect(r.stocks[0]).toMatchObject({close:146.9,quote_source:'tradingview',live_quote_available:true,quote_time:null,date:null,provider_delay:'unknown',market_session_open:false});
 expect(r.stocks[0].fetched_at_cairo).toContain('18:00:00');
 expect(toAgenticEvidence('get_live_quote',{symbols:['GTWL']},r)).toMatchObject({data_type:'provider-snapshot',data_time:null});
});

test('provider failure returns a labeled stored close rather than fabricated live verification',async()=>{
 provider.mockResolvedValue({success:false,error:'provider unavailable'});
 const r=await executeAgenticTool('get_live_quote',{symbols:['GTWL']},db(),'offline');
 expect(r).toMatchObject({status:'success',availability:'partial'});
 expect(r.stocks[0]).toMatchObject({close:160,date:'2026-10-07',live_quote_available:false,fetched_at:null,price_type:'daily_close'});
 expect(r.stocks[0].message).toContain('ليس سعراً لحظياً');
});

test('four requested symbols are rejected before any provider call',async()=>{
 const r=await executeAgenticTool('get_live_quote',{symbols:['COMI','TMGH','SWDY','GTWL']},db(),'offline');
 expect(r.status).toBe('error');expect(provider).not.toHaveBeenCalled();
});

test('Cairo retrieval time follows DST rather than an assumed two-hour offset',()=>{
 const e=toAgenticEvidence('get_live_quote',{symbols:['GTWL']},{status:'success',stocks:[{symbol:'GTWL',close:146.9,fetched_at:'2026-10-11T15:00:00Z',live_quote_available:true}]});
 expect(checkAgenticDraft('GTWL سعر 146.9 جنيه. وقت الجلب 18:00 بتوقيت القاهرة.',[e],'',[e])).toEqual([]);
 expect(checkAgenticDraft('GTWL سعر 146.9 جنيه. وقت الجلب 17:00 بتوقيت القاهرة.',[e],'',[e])).toContain('quote_fetch_time_cairo_mismatch');
 expect(checkAgenticDraft('وقت الجلب 15:00 UTC (18:00 بتوقيت القاهرة).',[e],'',[e])).not.toContain('quote_fetch_time_cairo_mismatch');
});
