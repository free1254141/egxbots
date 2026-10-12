import { checkAttribution } from '../answer-gate';
import { buildFactRecords } from '../facts';

const facts = buildFactRecords([{tool:'get_market',source:'database',data_time:'2026-10-12',
  data:{top_losers:[{symbol:'CPME',change:-13.0435}]}}]);

test('ordinary daily decline wording uses the sourced daily change, not backtest drawdown', () => {
  expect(checkAttribution('هبوط CPME بنسبة -13.04% في الجلسة.', facts)).toEqual([]);
  expect(checkAttribution('أكبر هبوط اليوم في CPME بنسبة -13.04%.', facts)).toEqual([]);
  expect(checkAttribution('هبوط CPME بنسبة -20% في الجلسة.', facts)).not.toEqual([]);
});

test('explicit maximum drawdown cannot borrow a daily change of the same magnitude', () => {
  expect(checkAttribution('CPME أقصى هبوط -13.04%.', facts)).not.toEqual([]);
  expect(checkAttribution('CPME **أقصى  هبوط** -13.04%.', facts)).not.toEqual([]);
  const backtest = buildFactRecords([{tool:'get_strategy_backtest',source:'fixture',data_time:'2026-10-12',
    data:{symbol:'CPME',backtest_drawdown_pct:13.04}}]);
  // Build the typed fact explicitly: the backtest tool uses nested metrics in production.
  const drawdown = {...facts[0],field:'backtest_drawdown_pct' as const,value:13.04};
  expect(checkAttribution('CPME أقصى هبوط 13.04%.', [...backtest,drawdown])).toEqual([]);
});
