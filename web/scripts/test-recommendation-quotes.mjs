import assert from 'node:assert/strict';
import { applyRecommendationQuotes } from '../src/lib/recommendation-quotes.ts';
const closed = { symbol: 'A', exchange: 'EGX', status: 'win', last_close: 12, profit_loss_pct: 20 };
const rows = [{ symbol: 'A', exchange: 'EGX', status: 'open', entry_price: 10, last_close: 8 }, closed,
  { symbol: 'B', exchange: 'EGX', status: 'open', entry_price: 5, last_close: 7 }];
const result = applyRecommendationQuotes(rows, [
  {symbol:'A',exchange:'EGX',date:'2026-10-07',close:9},
  {symbol:'A',exchange:'EGX',date:'2026-10-11',close:11},
  {symbol:'A',exchange:'US',date:'2026-10-12',close:100}]);
assert.equal(result[0].last_close, 11);
assert.ok(Math.abs(result[0].profit_loss_pct - 10) < 1e-10);
assert.equal(result[0].price_date, '2026-10-11');
assert.equal(result[1], closed);
assert.equal(result[2].last_close, null);
assert.equal(result[2].profit_loss_pct, null);
assert.equal(applyRecommendationQuotes(rows, [{symbol:'A',exchange:'EGX',date:'2026-10-11',close:0}])[0].last_close, null);
console.log('PASS: newest quote, exchange isolation, closed outcomes, missing/invalid prices');
