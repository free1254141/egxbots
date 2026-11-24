"""
Deploy Python chatbot backend files to Hugging Face Space (weeasdwee/AI_BOT).
Strict Rule:
- ONLY sync Python files (.py) and backend configs (requirements.txt, etc.)
- NEVER sync web/, static assets, docs, or non-python packages.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from huggingface_hub import HfApi, CommitOperationAdd

load_dotenv(".env")

FILES_TO_SYNC = [
    "api/agentic_chat/__init__.py",
    "api/agentic_chat/analysis_cache.py",
    "api/agentic_chat/auth_guard.py",
    "api/agentic_chat/market_registry.py",
    "api/agentic_chat/output_guard.py",
    "api/agentic_chat/pipeline.py",
    "api/agentic_chat/prompts.py",
    "api/agentic_chat/quant_engine.py",
    "api/agentic_chat/router.py",
    "api/agentic_chat/tools_execution.py",
    "api/agentic_chat/tools_schema.py",
    "api/agentic_chat/user_preferences.py",
    "api/agentic_chat/vision.py",
    "api/__init__.py",
    "api/main.py",
    "api/health.py",
    "api/live_bot.py",
    "api/acceleration_score.py",
    "api/adaptive_learning.py",
    "api/adaptive_model_selector.py",
    "api/ai_brain_visualizer.py",
    "api/backtest_config.py",
    "api/backtest_optimizer.py",
    "api/backtest_radar.py",
    "api/chatbot_tools.py",
    "api/chatbot_validator.py",
    "api/corporate_actions_engine.py",
    "api/council_validator.py",
    "api/daily_bot_run.py",
    "api/daily_continuation.py",
    "api/daily_job_outcome.py",
    "api/daily_job_scheduler.py",
    "api/daily_market_outlook.py",
    "api/daily_price_verification.py",
    "api/daily_recovery_state.py",
    "api/daily_report_dispatch.py",
    "api/dividends_engine.py",
    "api/daily_social_reports.py",
    "api/daily_stage_recovery.py",
    "api/egx30_fetcher.py",
    "api/egx_inventory.py",
    "api/egx_trading_calendar.py",
    "api/free_data_provider.py",
    "api/fundamentals_refresh.py",
    "api/historical_similarity.py",
    "api/intraday_downloader.py",
    "api/intraday_provider.py",
    "api/intraday_scheduler.py",
    "api/lib/indicators.py",
    "api/local_storage.py",
    "api/market_status_gate.py",
    "api/market_strategy.py",
    "api/model_catalog.py",
    "api/model_utils.py",
    "api/native_social_reports.py",
    "api/news_sentiment_engine.py",
    "api/opportunity_analyzer.py",
    "api/portfolio_manager.py",
    "api/price_sync_policy.py",
    "api/recommendation_data.py",
    "api/recommendation_events.py",
    "api/recommendation_freshness.py",
    "api/recommendation_policy.py",
    "api/rss_budget.py",
    "api/short_swing_published.py",
    "api/signal_performance.py",
    "api/smart_sync.py",
    "api/social_facebook_publisher.py",
    "api/social_report_images.py",
    "api/strategy_engine.py",
    "api/strict_quality_labeler.py",
    "api/structured_logger.py",
    "api/support_analytics.py",
    "api/symbols_local.py",
    "api/telegram_antispam.py",
    "api/trade_liquidity.py",
    "api/trading_config.py",
    "api/tradingview_integration.py",
    "api/train_exchange_model.py",
    "api/trap_detector.py",
    "api/unified_features.py",
    "api/unified_labeling.py",
    "api/virtual_market_adapter.py",
    "api/council.py",
    "api/update_ml_scores.py",
    "api/macro_correlation.py",
    "api/payment_common.py",
    "api/portfolio_or_optimizer.py",
    "Dockerfile",
    "daily_job_config.json",
    "api/stock_aliases.py",
    "api/saudi_stock_aliases.py",
    "api/saudi_daily_runner.py",
    "api/saudi_price_sync.py",
    "api/saudi_trading_calendar.py",
    "api/saudi_train_models.py",
    "api/saudi_telegram_dispatch.py",
    "api/saudi_news_sync.py",
    "api/saudi_disclosures_sync.py",
    "api/gcc_metals_sync.py",
    "api/gcc_disclosures_sync.py",
    "api/gcc_news_sync.py",
    "api/short_swings_daily.py",
    "api/short_swings_engine.py",
    "api/scanner_alerts_engine.py",
    "api/saudi_scanner_alerts_engine.py",
    "api/scanner_alerts_scheduler.py",
    "jobs/__init__.py",
    "jobs/daily_disclosures_sync.py",
    "jobs/send_vip_telegram_daily_report.py",
    "scripts/accumulation_scanner.py",
    "scripts/disclosures/sync_egx_disclosures.py",
    "api/data/saudi_short_swings_cache.json",
    "api/data/short_swings_cache.json",
    "api/stock_ai.py",
    "api/models/KING_TASI.pkl",
    "api/models/KING_TASI.pkl.model_card.json",
    "api/models/model_TADAWUL.pkl",
    "api/models/model_TADAWUL.pkl.model_card.json",
    "scripts/saudi_pipeline_bootstrap.py",
    "scripts/saudi_backtest_and_systems.py",
    "api/telegram_pro_invites.py",
    "api/routers/__init__.py",
    "api/routers/short_swings.py",
    "api/routers/scan_ai.py",
    "api/routers/scan_ai_fast.py",
    "api/routers/scan_tech.py",
    "api/routers/similarity_admin.py",
    "api/routers/chatbot.py",
    "api/routers/automations.py",
    "api/routers/voice.py",
    "api/routers/admin.py",
    "api/routers/bot.py",
    "api/perf_utils.py",
    "api/plan_limits.py",
    "api/sharia_stocks.py",
    "api/egx_canonical_names.py",
    "api/routers/offload.py",
    "api/routers/offload_public.py",
    "api/routers/offload_user.py",
    "api/routers/easykash.py",
    "api/routers/direct_wallet.py",
    "jobs/send_failed_payment_recovery.py",
    "jobs/telegram_subscription_reminders.py",
    "api/scheduled_automations_worker.py",
    "api/easykash_payments.py",
    "api/direct_wallet_payments.py",
    "api/cache_invalidation.py",
    "api/hf_history_cache.py",
    "api/telegram_bot.py",
    "api/telegram_b2b.py",
    "api/telegram_vip_chat.py",
    "api/native_telegram_vip_chat.py",
    "api/support_chat.py",
    "api/support_ai_agent.py",
    "api/routers/support.py",
    "api/routers/marketing.py",
    "api/marketing_lifecycle.py",
    "api/marketing_links.py",
    "api/web_origin.py",
    "api/jobs/__init__.py",
    "api/jobs/telegram_subscription_reminders.py",
    "api/social_scheduler.py",
    "requirements.txt",
]


def main():
    token = os.getenv("HF_TOKEN")
    if not token:
        print("[ERROR] HF_TOKEN not found in environment or .env", file=sys.stderr)
        sys.exit(1)

    repo_id = "weeasdwee/AI_BOT"
    operations = []

    for fpath in FILES_TO_SYNC:
        norm_path = fpath.replace("\\", "/")
        p = Path(norm_path)
        if not p.exists():
            print(f"[WARN] File not found: {norm_path}")
            continue

        operations.append(
            CommitOperationAdd(
                path_in_repo=norm_path,
                path_or_fileobj=str(p),
            )
        )
        print(f"[READY] {norm_path} ({p.stat().st_size} bytes)")

    if not operations:
        print("[INFO] No operations to commit.")
        return

    commit_msg = "feat(gcc,payments,offload): sync updated Python backend files to HF Space"
    print(f"\n[DEPLOY] Committing {len(operations)} files to HF Space '{repo_id}'...")

    api = HfApi(token=token)
    info = api.create_commit(
        repo_id=repo_id,
        repo_type="space",
        operations=operations,
        commit_message=commit_msg,
    )

    print(f"[SUCCESS] Commit OID: {info.oid}")
    print(f"[SUCCESS] Commit URL: {info.commit_url}")


if __name__ == "__main__":
    main()
