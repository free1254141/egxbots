export function applyRecommendationQuotes(rows: any[], quotes: any[]) {
  const latest = new Map<string, any>();
  for (const quote of quotes) {
    const key = `${quote.exchange}:${quote.symbol}`;
    if (!latest.has(key) || quote.date > latest.get(key).date) latest.set(key, quote);
  }
  return rows.map(row => {
    if (row.status !== "open") return row;
    const quote = latest.get(`${row.exchange}:${row.symbol}`);
    const price = Number(quote?.close);
    const valid = Number.isFinite(price) && price > 0;
    const entry = Number(row.entry_price);
    return { ...row, last_close: valid ? price : null,
      profit_loss_pct: valid && entry > 0 ? (price / entry - 1) * 100 : null,
      price_date: valid ? quote.date : null,
      price_volume: valid && quote.volume != null ? Number(quote.volume) : null,
      price_updated_at: valid ? quote.updated_at : null };
  });
}
