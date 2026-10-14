import {fetchLiveStockIndicators,isEgxSessionOpen} from './live-stock-updater';
import {reconcileStockQuote, stockQuoteMetadata} from './stock-quote';

export const LIVE_QUOTE_TOOL_SCHEMA = {type:'function',function:{
    name:'get_live_quote',
    description:'جلب جديد لسعر السهم من TradingView عند طلب السعر الحالي أو اللحظي أو إعادة تأكيد السعر. ليس إغلاقاً رسمياً ولا نضمن انعدام تأخير المزود. اعرض وقت الجلب وحدود المصدر؛ عند التعذر تعرض الأداة آخر إغلاق مخزن موسوماً كبديل. حتى 3 رموز، دون حفظ بيانات.',
    parameters:{type:'object',properties:{symbols:{type:'array',items:{type:'string'},minItems:1,maxItems:3}},required:['symbols']},
}};

export async function executeLiveQuoteTool(args:any,client:any){
    if(!Array.isArray(args.symbols)||!args.symbols.length||args.symbols.length>3)throw new Error('طلب السعر الحديث يقبل من 1 إلى 3 رموز');
    const stocks=await Promise.all(args.symbols.map(async(symbol:string)=>{
        const fetched=await fetchLiveStockIndicators(symbol,undefined,{allowClosedMarket:true,forceRefresh:true});
        if(fetched.success && fetched.data){
            const d=fetched.data;
            return {symbol,close:d.close,change_pct:d.change_pct,volume:d.volume,
                rsi_14:d.rsi_14,macd:d.macd,macd_signal:d.macd_signal,
                macd_hist:d.macd!=null&&d.macd_signal!=null?d.macd-d.macd_signal:null,
                ema_50:d.ema_50,ema_200:d.ema_200,bollinger_upper:d.bb_upper,bollinger_lower:d.bb_lower,
                date:null,quote_time:null,fetched_at:d.updated_at,
                fetched_at_cairo:new Intl.DateTimeFormat('en-GB',{timeZone:'Africa/Cairo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(d.updated_at)),quote_source:'tradingview',
                price_type:'provider_quote',live_quote_available:true,provider_delay:'unknown',
                market_session_open:isEgxSessionOpen(),from_cache:fetched.from_cache===true,
                limitations:['وقت الجلب ليس وقت آخر صفقة. زمن تأخير المزود غير موثق؛ ليست تغذية لحظية مضمونة أو إغلاقاً رسمياً.']};
        }
        const {data}=await client.from('stock_technical_indicators').select('date,close')
            .eq('exchange','EGX').eq('symbol',symbol).order('date',{ascending:false}).limit(1);
        const saved=await reconcileStockQuote(client,symbol,data?.[0], { preferLive: false });
        return {symbol,close:saved?.close??null,date:saved?.date??null,quote_source:saved?.quote_source??null,
            ...stockQuoteMetadata(saved),price_type:saved?.price_type || 'daily_close',live_quote_available:false,availability:saved?'partial':'missing',
            quote_time:null,fetched_at:null,provider_delay:'unknown',
            message:fetched.unsupported?'لا تتوفر تغذية لهذا الرمز لدى المصدر.':'تعذر جلب سعر جديد من المزود؛ البديل إغلاق مخزن وليس سعراً لحظياً.',
            limitations:['هذه القيمة بديل من قاعدة البيانات؛ لم يؤكدها المزود في هذا الطلب.']};
    }));
    return {status:'success',availability:stocks.every(r=>r.live_quote_available)?'available':stocks.every(r=>r.availability==='missing')?'missing':'partial',stocks};
}
