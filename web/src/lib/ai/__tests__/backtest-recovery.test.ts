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
