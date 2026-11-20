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
    "api/agentic_chat/pipeline.py",
    "api/agentic_chat/prompts.py",
    "api/agentic_chat/router.py",
    "api/agentic_chat/tools_execution.py",
    "api/agentic_chat/tools_schema.py",
    "api/agentic_chat/user_preferences.py",
    "api/agentic_chat/vision.py",
    "api/main.py",
    "api/acceleration_score.py",
    "api/daily_bot_run.py",
    "api/daily_job_scheduler.py",
    "api/daily_stage_recovery.py",
    "api/council.py",
    "api/update_ml_scores.py",
    "api/macro_correlation.py",
    "api/payment_common.py",
    "api/portfolio_or_optimizer.py",
    "Dockerfile",
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
    "api/routers/short_swings.py",
    "api/routers/scan_ai_fast.py",
    "api/perf_utils.py",
    "api/plan_limits.py",
    "api/daily_job_outcome.py",
    "api/sharia_stocks.py",
    "api/egx_canonical_names.py",
    "api/routers/offload.py",
    "api/routers/offload_public.py",
    "api/routers/offload_user.py",
    "api/routers/easykash.py",
    "api/routers/direct_wallet.py",
    "jobs/send_failed_payment_recovery.py",
    "api/scheduled_automations_worker.py",
    "api/easykash_payments.py",
    "api/direct_wallet_payments.py",
    "api/daily_report_dispatch.py",
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
