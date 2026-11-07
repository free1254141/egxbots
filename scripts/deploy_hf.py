"""Deploy updated Python backend files to Hugging Face Space (weeasdwee/AI_BOT).

Strict Project Rule:
- ONLY sync updated Python files (.py) and backend configurations (e.g. api/, jobs/, scripts/, requirements*.txt, daily_job_config.json, Dockerfile).
- NEVER sync web/ (Next.js frontend), static images/icons, Android APKs, docs, or non-Python assets.
"""

import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env")

ALLOWED_EXACT_FILES = {
    "requirements.txt",
    "requirements-social.txt",
    "daily_job_config.json",
    "Dockerfile",
    "Procfile",
    "app.py",
}

ALLOWED_DIRS = ("api/", "jobs/", "scripts/")


def is_allowed_hf_file(fpath: str) -> bool:
    norm = fpath.replace("\\", "/").lstrip("./")
    fname = os.path.basename(norm)

    # Must not be inside web/, docs/, android/, or hidden folders
    if norm.startswith(("web/", "docs/", "android/", ".gemini/", ".git/", ".cache/")):
        return False

    # Allow specific config files
    if fname in ALLOWED_EXACT_FILES:
        return True

    # Must be a Python file in allowed directories or root
    if norm.endswith(".py"):
        if norm.startswith(ALLOWED_DIRS) or "/" not in norm:
            return True

    return False


def main():
    token = os.getenv("HF_TOKEN")
    if not token:
        print("[ERROR] HF_TOKEN not found in environment or .env", file=sys.stderr)
        sys.exit(1)

    from huggingface_hub import HfApi, CommitOperationAdd, CommitOperationDelete

    base_ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD~1"
    target_ref = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

    cmd = ["git", "-c", "core.quotepath=false", "diff", "--name-status", f"{base_ref}..{target_ref}"]
    out = subprocess.check_output(cmd, text=True, encoding="utf-8")

    ops = []
    skipped = []

    for line in out.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]

        if status.startswith("R"):
            old_path, new_path = parts[1], parts[2]
            if is_allowed_hf_file(old_path):
                ops.append(CommitOperationDelete(path_in_repo=old_path))
            if is_allowed_hf_file(new_path) and Path(new_path).exists():
                ops.append(CommitOperationAdd(path_in_repo=new_path, path_or_fileobj=new_path))
            else:
                skipped.append(new_path)
        elif status == "D":
            fpath = parts[1]
            if is_allowed_hf_file(fpath):
                ops.append(CommitOperationDelete(path_in_repo=fpath))
            else:
                skipped.append(fpath)
        else:
            fpath = parts[1]
            if is_allowed_hf_file(fpath):
                if Path(fpath).exists():
                    ops.append(CommitOperationAdd(path_in_repo=fpath, path_or_fileobj=fpath))
            else:
                skipped.append(fpath)

    print(f"[HF Deploy] Total Python/backend operations: {len(ops)}")
    if skipped:
        print(f"[HF Deploy] Filtered out {len(skipped)} non-python/frontend files (e.g. {skipped[:3]}...)")

    if not ops:
        print("[HF Deploy] No updated Python or backend files to deploy.")
        return

    commit_msg = sys.argv[3] if len(sys.argv) > 3 else f"Sync Python backend updates ({target_ref})"
    api = HfApi(token=token)
    info = api.create_commit(
        repo_id="weeasdwee/AI_BOT",
        repo_type="space",
        operations=ops,
        commit_message=commit_msg,
    )
    print(f"[HF Deploy] Success! Commit: {info.oid}")
    print(f"[HF Deploy] URL: {info.commit_url}")


if __name__ == "__main__":
    main()
