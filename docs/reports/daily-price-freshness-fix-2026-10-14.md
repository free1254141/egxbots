# Daily session price verification — 14 October 2026

## Proven defect and scope

The close run reported 233 successful history synchronizations, but only224
symbols had a row dated14 October. The database's stock_prices.updated_at had no
update trigger, and sync_df_to_supabase did not send it on updates. Therefore a
midday insertion timestamp could not establish a successful close refresh.

This repair changes the price stage, its writer and bounded recovery. It does
not rerun today's job, signals, images or notifications. Provider absence remains
visible; the repair does not guarantee a suspended/illiquid instrument has a bar.

## After the change

- Every daily price write advances updated_at with a UTC provider-fetch/write
  timestamp. It is not an exchange closing timestamp.
- The EGX writer rejects invalid OHLCV. The existing flat nontrading quote rules
  remain unchanged on HF; do not infer tradability from an accepted stored quote.
- After synchronization, daily_price_verification reads explicit OHLCV/date/time
  projections in chunks of100, with a strict limit. A successful result requires
  a valid expected-session row refreshed after this phase's synchronization began.
- Missing, invalid or cached midday bars get one EODHD request for the original
  ticker and exact session. No guessed ticker substitution, fuzzy-name matching,
  mechanical ADRI/ADCI substitution or corporate identity merge is introduced.
- Alternate requests are capped at80 and two workers, with12-second transport
  timeout and no nested retries. Readback must succeed even after a provider
  claims a successful write. Beyond the cap, rows remain visibly unresolved.
- Ledger coverage counts verified current-session refreshes. Provider-success
  count, alternate recovery list, failed ticker reason and refresh timestamp are
  recorded separately. Unverified observed quotes are excluded from entries.
- Confirmed alternate no-bar/404 ends retries for this phase, without labeling
  the instrument delisted. Next normal phase revisits it. Transport failures
  remain eligible for the existing single durable recovery attempt. That attempt
  verifies stored data too and does not repeat the alternate-source batch.
- Current per-instrument trading/freshness gates stay active. No old price is
  fabricated into an entry or exit, and privacy/RLS is unchanged.

## Verification and deployment boundary

69 targeted offline tests passed on the local code: current/old/malformed bars,
midday reuse rejection, write timestamps, alternate readback, retry exhaustion,
request limits, critical-price lane, existing recovery, TradingView deadlines,
parallel sync and actual midday recommendation isolation. Python compilation and
diff whitespace checks passed. No full production daily replay was used as a test.

HF baseline: ffbc888012b420716c6f6fa13e6219ff8e54a9bc, RUNNING.
HF already differs from local main in unrelated RSS, liquidity and early short
monitoring work. The deployment bundle applies only this task's delta onto that
exact HF baseline, rather than uploading whole local files with those differences.
Bundle paths: api/daily_bot_run.py, daily_stage_recovery.py,
daily_price_verification.py, recommendation_freshness.py, stock_ai.py.
14 targeted price-verification/writer tests passed against the staged writer.
An additional preexisting early-short-monitoring ordering assertion fails on the
HF baseline's late ordering; that unrelated performance change is not silently
included or claimed fixed by this price deployment. The same run reached normal
midday completion and did not execute ordinary recommendation operations.

No active daily run existed at the pre-deployment check. Upload uses parent_commit
to reject concurrent HF revision changes. No models, credentials, snapshots,
inventory JSON or unrelated local changes are in the bundle.

## Rollback and operational acceptance

Restore the four modified HF files from the baseline SHA and remove the new
daily_price_verification.py if rolling back as one batch. Never undo price rows
or delete today's audit/checkpoints to replay delivery.

The next normal daily run must show explicit coverage.session and verified_after,
updated price timestamps, alternate_recovered and failure_details. Compare those
with an aggregate over the same date/universe. The old14 October233/275 ledger
is historical and remains unchanged. The patch does not claim today's52 missing
inventory symbols or42 provider failures have all acquired new prices.

Different provider tickers and duplicate ISINs remain a separate identity issue:
the inventory contains ambiguous duplicates, so an automatic merge would risk
mixing instruments/share classes. Exact original-symbol EODHD fallback avoids
that substitution. Preserve explicit missing-data states when both sources lack
a session bar.
