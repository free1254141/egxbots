# Compound MACD validation and explanatory recovery

A three-stock comparison combined MACD, signal and histogram values in one column.
The publication gate incorrectly mapped the entire column to the histogram field,
rejected supported values, and replaced the analysis with a raw indicator dump.

Compound columns now bind each component to its declared metric and order, for
both row-oriented and transposed comparison tables. Rounding follows displayed
precision; swapped metrics, reversed signs, cross-stock values and incomplete
cells remain rejected.

Stock analysis and comparison recovery now explain the verified snapshots:
price position relative to averages, RSI zone, current MACD/signal relationship,
and available support/resistance scenarios. They do not emit the former quote
and indicator dump. Newer quotes cannot inherit older levels, and stale
indicators cannot be combined with a newer price. Missing evidence is explicit.
Timeout/provider failures use the same recovery, scoped to current tool evidence.

Validation: 240 offline tests passed across six suites; TypeScript no-emit and
Next.js production compilation in compile mode passed. Tests include the actual
runtime, provider failure, failed repair, combined columns, rounding, metric order,
signs, missing data and current-symbol isolation. No additional provider calls,
market reads, database writes or daily-job changes are introduced by recovery.
Production deployment and live verification must be reported separately.
Rollback: revert the code changes in this fix without resetting unrelated work.
