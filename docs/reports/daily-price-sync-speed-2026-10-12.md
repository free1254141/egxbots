# Daily price sync speed and incident — 2026-10-12

## Evidence

Close run `6b9d6e00-fdfd-4967-a34c-9097f6ef02c7` started at 17:00:02 Cairo
(14:00:02 UTC). Its ledger remained at `sync_prices` started with
`total_symbols=0`, while HF stdout showed 140/284 symbols processed, 120 successful,
and further connection failures through 18:16 Cairo. It was progressing slowly;
the persisted counter was not a live progress counter.

TradingView connections were lost repeatedly. Yahoo proxy requests timed out
after eight seconds, and some symbols returned 404. Four full provider attempts
per symbol and two workers compounded the delay. TradingView's socket timeout
bounded each read, so heartbeats could extend the overall request indefinitely.

## Changed behavior

- `price_sync_policy.py`: a per-client monotonic TradingView history deadline
  defaults to 20 seconds (`TRADINGVIEW_REQUEST_BUDGET`, clamped 5–45). Both
  websocket and underlying fragmented-frame reads use the remaining budget.
  Even when tvDatafeed swallows a deadline and parses partial bars, the wrapper
  rejects that result. Connections close and client methods restore in `finally`.
  This bounds the history request, not database calls/DNS/all providers combined.
- Retry cap is now two attempts total. SmartSync defaults change from
  3 retries / 10-second waits / 1.5-second throttle / 2 workers to
  1 retry / 2-second waits / 0.3-second throttle / 4 workers.
  Worker configuration is clamped to 1–6 with safe invalid-value handling.
- `smart_sync.py`: the executor bounds concurrency; results are collected in
  completion order. Duplicate symbols are fetched once; individual failures
  remain in the results instead of aborting the entire batch.
- `tradingview_integration.py`: Yahoo 404s are remembered per ticker for 15 minutes
  (maximum 1,024 entries). TradingView remains eligible for a retry. A lock protects
  proxy failure state. Direct success no longer resets a broken proxy's counter,
  allowing the existing three-failure/60-second cooldown to activate.
- `daily_bot_run.py`: initial progress and updates after 20 completed symbols,
  60 seconds when another symbol completes, and completion persist the real
  processed/success/total/elapsed values. One existing `started` entry is updated;
  progress never marks a stage successful and does not write a ledger per symbol.

Same-day `refresh_latest=True`, dated OHLCV writes, failed-symbol reporting and
existing coverage/readiness gates remain in effect. Fewer retries may leave a
symbol missing during a prolonged outage; missing prices must remain failures.

## Verification before upload

49 targeted offline tests passed: endless heartbeats, fragmented reads, swallowed
deadlines, cleanup, retry recovery/caps, concurrency, deduplication, write failures,
progress failure isolation, actual fetch-path Yahoo fallback, 404 expiry, proxy
cooldown, coverage, scheduler heartbeats and existing stage/social recovery.
Python compilation and `git diff --check` passed.

An offline 40-symbol simulation with identical 20ms provider latency measured
0.406s with two workers and 0.203s with four; both completed all 40 symbols.
This measures simulated concurrency, not production daily runtime.

One read-only live TradingView check requested ten COMI daily bars. The provider
disconnected after 1.28s and returned no bars; real provider availability was not
verified. No database writes, full daily replay, backtest or paid generation was
performed as a test.

## Deployment and rollback

Previous HF: `50d033b0cdc6ba4393f4279dbe33270f061b174d`.
Uploaded HF: `81d0ac7ec5c90a0509ea86edf60e1763e9e224bf`.
Git runtime/tests commit: `3d5ad0d759eeecd9d4a0f3069f75ca977cac36f6` (pushed to main).
Only the four runtime Python files above were uploaded in one commit. Models,
cache snapshots, secrets and development tests were excluded.

The user explicitly selected immediate upload and interruption of today's active
run. Upload success alone does not confirm runtime readiness. Later stages of that
run must not be claimed complete: existing recovery of a started price stage does
not guarantee all never-started stages will execute. No manual ledger rewrite or
full replay was issued.

Post-deployment verification at approximately 18:32 Cairo: HF runtime and runtime
SHA matched the uploaded revision, stage was `RUNNING`, domain was `READY`, and
`/health` returned HTTP 200 with `{"status":"ok"}`. The interrupted old run was
marked `failed`, completed_at 18:31:25 Cairo; this is not successful completion
of today's full daily pipeline. No production duration/coverage improvement has
yet been measured with the new code.

Rollback restores the same four paths from the previous HF revision in one commit.
It restores former retries/deadlines/concurrency/progress behavior; it does not undo
already saved prices. Exclude unrelated local short-swings cache/report changes.
