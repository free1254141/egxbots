# Portfolio overview and manual bookkeeping

## Result

All authenticated plans, including Free, can view the daily holdings summary, concentration including cash, read-only shock scenarios, existing historical comparison, and their private transaction history. This change adds no alerts, scheduled notifications, or per-visit AI calls. Existing stock-count limits still apply to purchases.

Daily movement uses current quantities on two exact matching EGX30 sessions. Adjusted prices are used consistently when available. A missing session makes the total unavailable instead of zero. This is a holdings simulation, not actual account performance. Cash stays fixed in the 5/10/20 percent shock scenarios. Unknown sectors remain explicit.

The existing positions table becomes mobile cards below 768px. Missing cost/price is neutral and unavailable in both the portfolio and navbar. Account snapshots are isolated by owner and stale requests cannot overwrite a later account.

## Manual ledger

Adding existing holdings is distinct from recording a purchase. Purchases deduct cost and recorded fees from cash; partial/full sales add net proceeds; deposits and withdrawals change cash. All updates and the event insert are one caller-scoped PostgreSQL transaction, with RLS, an owner lock and request-id deduplication. Errors roll back every write. A retry with different input under the same id is rejected. Recorded dates cannot reorder previously recorded ledger operations.

Apply `supabase/migrations/20261012092359_portfolio_transaction_ledger.sql` before enabling the new transaction endpoint. The route fails with 503 and does not claim success if the RPC is unavailable. Historical imports, quantity corrections and legacy sales do not constitute a complete trading ledger. Historical basket comparison continues to exclude cash flows and trades; the new ledger is not presented as reconstructed actual returns.

## Verification

- Targeted math, API, Free access, private caching, input validation, missing-data, mobile structure, transaction form and existing portfolio tests.
- PostgreSQL-compatible local database checks via `npm run test:portfolio-db`: fees, partial/full sales, deposits/withdrawals, duplicate requests, anonymous rejection, RLS isolation and rollback on event-insert failure.
- Production build uses a local empty-data fixture, not production credentials or mutations.
- The visual preview uses the real component markup with synthetic data; the shock control is local and does not submit transactions.
- Production deployment and live database application are separate release steps, not established by local tests.
