import { advisoryMarketMeaning } from "../market-meaning-advisory";
import { toAgenticEvidence, checkAgenticDraft, safeAgenticFallback } from "../agentic-publication";
import { stockPricePresentation } from "../stock-quote";

const evidence = (row: any) => [toAgenticEvidence("get_stock",{symbols:["COMI"]},{status:"success",stocks:[{symbol:"COMI",date:"2026-10-13",close:100,...row}]})];
test("today snapshot does not become a final close from date/clock alone",()=>{
    jest.useFakeTimers().setSystemTime(new Date("2026-10-13T18:00:00Z"));
    expect(stockPricePresentation("2026-10-13")).toMatchObject({price_type:"current_session_snapshot",final_close_confirmed:false});
    expect(stockPricePresentation("2026-10-12")).toMatchObject({price_type:"daily_close",final_close_confirmed:false});
    expect(stockPricePresentation("2026-10-13",true)).toMatchObject({price_type:"daily_close",final_close_confirmed:true});
    jest.useRealTimers();
    expect(advisoryMarketMeaning("COMI: إغلاق اليوم 100 جنيه.",evidence({}),"2026-10-13")).toHaveLength(1);
    expect(advisoryMarketMeaning("## تحليل COMI — إغلاق 2026-10-13",evidence({}),"2026-10-13")).toHaveLength(1);
    expect(advisoryMarketMeaning("COMI: آخر سعر متاح للجلسة 100 جنيه.",evidence({}),"2026-10-13")).toEqual([]);
    expect(advisoryMarketMeaning("COMI: إغلاق اليوم 100 جنيه.",evidence({session_complete:true}),"2026-10-13")).toEqual([]);
});
test("evidence recovery labels today's price conditionally without changing its value",()=>{
    jest.useFakeTimers().setSystemTime(new Date("2026-10-13T18:00:00Z"));
    const current=safeAgenticFallback(evidence({}),"تعذر إكمال كل التفاصيل");
    expect(current).toContain("ليس إغلاقاً نهائياً مؤكداً");expect(current).toContain("100 جنيه بتاريخ 2026-10-13");
    expect(current).not.toContain("| COMI |");
    const historical=safeAgenticFallback(evidence({date:"2026-10-12"}),"تعذر إكمال كل التفاصيل");
    expect(historical).toContain("إغلاق يومي مخزن");
    jest.useRealTimers();
});
test("26.72 RSI is inside oversold rather than merely near, without blocking grounded draft",()=>{
    const e=evidence({rsi_14:26.72});
    expect(advisoryMarketMeaning("COMI: RSI قريب من التشبع البيعي.",e,"2026-10-13").join()).toContain("داخل النطاق");
    expect(advisoryMarketMeaning("COMI: RSI عند 26.72 يصف قرباً من منطقة التشبع البيعي، ولا يثبت وحده تخفيف ضغط البيع.",e,"2026-10-13").join()).toContain("داخل النطاق");
    expect(advisoryMarketMeaning("COMI: RSI داخل النطاق التقليدي للتشبع البيعي ولا يثبت ارتداداً.",e,"2026-10-13")).toEqual([]);
    expect(checkAgenticDraft("COMI: RSI قريب من التشبع البيعي.",e)).toEqual([]);
});
test("negative MACD may still be above its signal",()=>{
    expect(advisoryMarketMeaning("COMI: MACD سالب ولذلك تحت خط الإشارة.",evidence({macd:-1,macd_signal:-2}),"2026-10-13").join()).toContain("أعلى خط إشارته");
    expect(advisoryMarketMeaning("COMI: MACD سالب لكنه أعلى خط الإشارة.",evidence({macd:-1,macd_signal:-2}),"2026-10-13")).toEqual([]);
    expect(checkAgenticDraft("COMI: MACD سالب ولذلك تحت خط الإشارة.",evidence({macd:-1,macd_signal:-2}))).toEqual([]);
});
test("current equality does not establish historical stability and accumulation is not proof",()=>{
    expect(advisoryMarketMeaning("COMI: القيم متساوية ولذلك السعر مستقر تاريخياً.",evidence({}),"2026-10-13").join()).toContain("لا يثبت ثباتها");
    expect(advisoryMarketMeaning("COMI: درجة التجميع تثبت تجميعاً مؤسسياً.",evidence({accumulation_score:70}),"2026-10-13").join()).toContain("ليست إثباتاً");
    expect(advisoryMarketMeaning("COMI: درجة التجميع لا تثبت شراء مؤسسات.",evidence({accumulation_score:70}),"2026-10-13")).toEqual([]);
    expect(checkAgenticDraft("COMI: القيم متساوية ولذلك السعر مستقر تاريخياً.",evidence({}))).toEqual([]);
    expect(checkAgenticDraft("COMI: درجة التجميع تثبت تجميعاً مؤسسياً.",evidence({accumulation_score:70}))).toEqual([]);
});
test("drawdown ranking follows magnitude instead of returns",()=>{
    const e=[toAgenticEvidence("compare_strategies_history",{}, {status:"success",symbol:"COMI",strategy_metrics:[{strategy_id:"smc",strategy_name:"SMC",maxDrawdownPct:20},{strategy_id:"price_action",strategy_name:"البرايس أكشن",maxDrawdownPct:5}]})];
    expect(advisoryMarketMeaning("SMC smc هو الأقل هبوطاً.",e,"2026-10-13").join()).toContain("الأصغر في مقدار");
    expect(advisoryMarketMeaning("البرايس أكشن الأقل هبوطاً.",e,"2026-10-13")).toEqual([]);
    expect(checkAgenticDraft("SMC smc هو الأقل هبوطاً.",e)).toEqual([]);
});
