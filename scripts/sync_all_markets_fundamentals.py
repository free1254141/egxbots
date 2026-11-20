"""
scripts/sync_all_markets_fundamentals.py
CLI runner for the unified 3-tier institutional fundamentals sync across all 4 markets:
  EGX (Egypt), TADAWUL (Saudi Arabia), QSE (Qatar), DFM & ADX (UAE).

Usage:
  python scripts/sync_all_markets_fundamentals.py --markets all
  python scripts/sync_all_markets_fundamentals.py --markets egx
  python scripts/sync_all_markets_fundamentals.py --markets all --dry-run --limit 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv("web/.env.local", override=False)

from api.fundamentals_sync import resolve_exchanges_arg, sync_markets_fundamentals


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync institutional financial & fundamental data for EGX, TASI, QSE, UAE.")
    parser.add_argument("--markets", default="all", help="Comma-separated markets: all, egx, tasi, qse, uae, dfm, adx")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent HTTP workers for StockAnalysis/yfinance")
    parser.add_argument("--skip-tv", action="store_true", help="Skip TradingView Tier 1")
    parser.add_argument("--skip-sa", action="store_true", help="Skip StockAnalysis Tier 2")
    parser.add_argument("--skip-yf", action="store_true", help="Skip yfinance Tier 3 gap-filler")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and compute without writing to Supabase")
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols per exchange (smoke test)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    exchanges = resolve_exchanges_arg(args.markets)
    print(f"Starting 3-tier fundamentals sync for exchanges: {exchanges} (dry_run={args.dry_run})")

    report = sync_markets_fundamentals(
        exchanges=exchanges,
        use_tradingview=not args.skip_tv,
        use_stockanalysis=not args.skip_sa,
        use_yfinance_fallback=not args.skip_yf,
        max_workers=args.workers,
        dry_run=args.dry_run,
        limit_per_exchange=args.limit,
    )

    print(f"\n=== FUNDAMENTALS SYNC COMPLETE ({report['elapsed_sec']}s) ===")
    for ex, info in report["markets"].items():
        print(
            f"\n[{ex}] total={info['total_symbols']} | upserted={info['upserted']} "
            f"| TV={info['tv_hits']} SA={info['sa_hits']} YF={info['yf_hits']}"
        )
        for k, v in info["coverage"].items():
            print(f"  {k:20s}: {v['count']:4d} / {info['total_symbols']:4d} ({v['pct']:5.1f}%)")


if __name__ == "__main__":
    main()
