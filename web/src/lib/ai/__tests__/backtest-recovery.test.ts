import {checkAgenticDraft,toAgenticEvidence,safeAgenticFallback} from '../agentic-publication';
import {fallbackEvidence} from '../agentic-recovery';
import {renderBacktestEvidence,advisoryBacktestMetricMeaning} from '../backtest-evidence';
const data={status:'success',symbol:'AJWA',date:'2026-10-07',start_date:'2024-11-04',candle_count:473,assumptions:{initialCapital:100000,commissionBps:10,slippageBps:10},strategy_metrics:[{strategy_id:'trend_macd',strategy_name:'الاتجاه وMACD',winRatePct:22.22222222222222,finalEquity:83604.93978982033,closedTrades:18,profitFactor:0.5254711898103166,maxDrawdownPct:42.33177659044249,totalReturnPct:-16.39506021017967}]};
const e=toAgenticEvidence('compare_strategies_history',{symbol:'AJWA',strategy_ids:['trend_macd']},data);
test.each(['-16.40%','−16.40%','−١٦٫٤٠٪','－16.40%'])('negative backtest return keeps its sign for %s',n=>{
 expect(checkAgenticDraft(`AJWA — الاتجاه وMACD\nالعائد التراكمي ${n}`,[e])).toEqual([]);
});
test('wrong return sign still rejects',()=>{
 expect(checkAgenticDraft('AJWA — الاتجاه وMACD\nالعائد التراكمي +16.40%',[e])).toContain('strategy_metric_mismatch:AJWA:trend_macd:totalReturnPct');
});
test.each(['رأس المال النهائي','القيمة النهائية','الرصيد النهائي'])('vertical %s binds value to final equity',label=>{
 const draft=`AJWA — الاتجاه وMACD\n| المقياس | القيمة |\n|---|---|\n| ${label} | 83,604.94 جنيه |`;
 expect(checkAgenticDraft(draft,[e])).toEqual([]);
 expect(checkAgenticDraft(draft.replace('83,604.94','93,604.94'),[e])).toContain('table_value_not_grounded:AJWA:93604.94');
});
test('recovery retains exact backtest metrics and scope',()=>{
 expect(fallbackEvidence([e],['AJWA'])).toEqual([e]);
 expect(fallbackEvidence([e],['COMI'])).toEqual([]);
 const reply=safeAgenticFallback([e],'internal_reviewer_failure');
 expect(reply).toContain('473 شمعة');expect(reply).toContain('22.22 | -16.40');expect(reply).toContain('83604.94');
 expect(reply).not.toContain('تعذر إكمال إجابة');expect(reply).not.toContain('internal_reviewer_failure');
 expect(renderBacktestEvidence({...data,strategy_metrics:[{...data.strategy_metrics[0],winRatePct:null}]})).toBeNull();
});
test.each([{ev:[]},{ev:[toAgenticEvidence('get_stock',{symbols:['AJWA']},{status:'error',message:'database unavailable'})]},{ev:[toAgenticEvidence('get_stock',{symbols:['AJWA']},{status:'success',availability:'missing',stocks:[]})]}])('no-data recovery cannot invent a backtest or leak technical failure',({ev})=>{
 const reply=safeAgenticFallback(fallbackEvidence(ev),'MODEL_HTTP_503');
 expect(reply).not.toContain('تعذر إكمال إجابة');expect(reply).not.toContain('MODEL_HTTP_503');expect(reply).not.toContain('22.22');
 expect(reply).toContain('بيانات');
});

test.each(['مع هبوط وسيط بلغ 42.33%','متوسط الهبوط 42.33%','average drawdown 42.33%'])('mislabeled drawdown requests correction: %s', draft=>{
 expect(advisoryBacktestMetricMeaning(draft,true)).toHaveLength(1);
 expect(advisoryBacktestMetricMeaning(draft,false)).toEqual([]);
});
test.each(['أقصى هبوط 42.33%','42.33% هو أقصى هبوط وليس متوسط الهبوط','متوسط الهبوط غير متاح، وأقصى هبوط 42.33%'])('qualified drawdown is accepted: %s', draft=>{
 expect(advisoryBacktestMetricMeaning(draft,true)).toEqual([]);
});

test('whole percent rounding of drawdown is accepted but another whole percent is not',()=>{
 const draft='AJWA — الاتجاه وMACD\nهبوط بلغ نحو 42% من قمة سابقة إلى قاع لاحق.';
 expect(checkAgenticDraft(draft,[e])).toEqual([]);
 expect(checkAgenticDraft(draft.replace('42%','41%'),[e])).toContain('strategy_metric_mismatch:AJWA:trend_macd:maxDrawdownPct');
});
test('starting capital beside final equity is grounded separately without accepting a wrong amount',()=>{
 const draft='AJWA — الاتجاه وMACD\n| المقياس | القيمة |\n|---|---|\n| رأس المال النهائي | 83,604.94 جنيه (من 100,000) |';
 expect(checkAgenticDraft(draft,[e])).toEqual([]);
 expect(checkAgenticDraft(draft.replace('100,000','110,000'),[e])).toContain('table_value_not_grounded:AJWA:110000');
 expect(checkAgenticDraft(draft.replace('83,604.94','100,000'),[e])).toContain('table_value_not_grounded:AJWA:100000');
});

// Production KORA failure: a daily price decline was mistaken for strategy drawdown.
const koraData={...data,symbol:'KORA',candle_count:60,start_date:'2026-07-20',date:'2026-10-14',strategy_metrics:[{strategy_id:'trend_macd',strategy_name:'الاتجاه وMACD',winRatePct:0,finalEquity:100000,closedTrades:0,profitFactor:null,maxDrawdownPct:0,totalReturnPct:0}]};
const koraEvidence=toAgenticEvidence('compare_strategies_history',{symbol:'KORA',strategy_ids:['trend_macd']},koraData);
const koraDraft=`KORA — الاتجاه وMACD
| المقياس | النتيجة |
|---|---|
| العائد الصافي | 0.00% |
| أقصى هبوط لرأس المال | 0.00% |
| نسبة الصفقات الرابحة | 0.00% |
| عدد الصفقات المغلقة | 0 |
| معامل الربح | غير متاح (لا صفقات مغلقة) |
| رأس المال النهائي | 100,000 جنيه |
التعديلات الرأسمالية غير متحقق منها، والهبوط الحاد المسجل (-56.18% في 2026-10-13) لا يثبت سبب الحركة.`;
test('KORA zero-trade backtest does not claim a daily price drop is strategy drawdown',()=>{
 expect(checkAgenticDraft(koraDraft,[koraEvidence])).toEqual([]);
 expect(checkAgenticDraft('KORA — الاتجاه وMACD\nأقصى هبوط لرأس المال 56.18%.',[koraEvidence])).toContain('strategy_metric_mismatch:KORA:trend_macd:maxDrawdownPct');
 expect(checkAgenticDraft(koraDraft.replace('هبوط لرأس المال | 0.00','هبوط لرأس المال | 56.18'),[koraEvidence]).length).toBeGreaterThan(0);
});
test('zero-trade recovery retains metrics with an undefined profit factor',()=>{
 const reply=safeAgenticFallback([koraEvidence],'review_rejected');
 expect(reply).toContain('60 شمعة');
 expect(reply).toContain('0.00 | 0.00 | 0.00 | 0 | غير متاح (لا صفقات مغلقة) | 100000.00');
 expect(reply).not.toContain('بعض البيانات المطلوبة غير متاحة');
 expect(checkAgenticDraft(reply,[koraEvidence])).toEqual([]);
 expect(renderBacktestEvidence({...koraData,strategy_metrics:[{...koraData.strategy_metrics[0],closedTrades:2}]})).toBeNull();
});
