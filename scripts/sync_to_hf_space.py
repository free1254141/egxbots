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
    "api/agentic_chat/auth_guard.py",
    "api/agentic_chat/pipeline.py",
    "api/agentic_chat/prompts.py",
    "api/agentic_chat/router.py",
    "api/agentic_chat/tools_execution.py",
    "api/agentic_chat/tools_schema.py",
    "api/main.py",
    "api/cache_invalidation.py",
    "api/telegram_vip_chat.py",
    "api/native_telegram_vip_chat.py",
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

    commit_msg = "Deploy Python Agentic Chatbot backend & loadtest benchmark guard"
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
