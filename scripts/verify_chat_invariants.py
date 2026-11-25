"""
Pre-deploy offline invariant & regression gate for EGX Bots AI Chat and Quant Engine.

Run locally before any commit, push, or Hugging Face deployment:
    python scripts/verify_chat_invariants.py

Checks (zero remote network / DB / LLM / log calls):
1. Python syntax compilation (`py_compile`) for all AI Chat, Quant, Optimizer, and Automation modules.
2. Hugging Face manifest parity (`scripts/sync_to_hf_space.py` `FILES_TO_SYNC` includes every local
   `api.*` module imported by `api/agentic_chat/*.py`, `api/portfolio_or_optimizer.py`, and
   `api/scheduled_automations_worker.py`, plus all files inside `api/agentic_chat/`).
3. Offline deterministic pytest regression suites (Quant, Optimizer/HRP/DCA, Output Guard, Aliases,
   Intraday pacing, Scheduled Automations, Quota, and Telegram handlers).
"""

from __future__ import annotations

import ast
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parent.parent

CRITICAL_MODULES = [
    *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "api" / "agentic_chat").glob("*.py")),
    "api/portfolio_or_optimizer.py",
    "api/scheduled_automations_worker.py",
    "api/saudi_stock_aliases.py",
    "api/stock_aliases.py",
    "api/quant_engine.py" if (ROOT / "api" / "quant_engine.py").exists() else "",
]
CRITICAL_MODULES = [m for m in CRITICAL_MODULES if m]

OFFLINE_TEST_SUITES = [
    "api/tests/test_intraday_and_cache_hardening.py",
    "api/tests/test_quant_intelligence_engine.py",
    "api/tests/test_portfolio_or_optimizer.py",
    "api/tests/test_bcd522ec_audit_fixes.py",
    "api/tests/test_scheduled_automations.py",
    "api/tests/test_chat_audit_2026_11_22_fixes.py",
    "api/tests/test_quota_and_bonus.py",
    "api/tests/test_telegram_command_isolation.py",
    "api/tests/test_telegram_photo_support.py",
]


def _compile_all() -> None:
    targets = CRITICAL_MODULES + [t for t in OFFLINE_TEST_SUITES if (ROOT / t).exists()]
    for rel in targets:
        py_compile.compile(str(ROOT / rel), doraise=True)
    print(f"[OK] py_compile passed for {len(targets)} Python files.")


def _load_hf_manifest() -> Set[str]:
    ns: dict = {}
    sync_src = (ROOT / "scripts" / "sync_to_hf_space.py").read_text(encoding="utf-8")
    tree = ast.parse(sync_src, filename="scripts/sync_to_hf_space.py")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "FILES_TO_SYNC":
                    val = ast.literal_eval(node.value)
                    return {str(x).replace("\\", "/") for x in val}
    raise RuntimeError("Could not locate FILES_TO_SYNC in scripts/sync_to_hf_space.py")


def _check_hf_manifest_imports() -> None:
    manifest = _load_hf_manifest()
    missing: list[str] = []

    for rel in CRITICAL_MODULES:
        if rel not in manifest:
            missing.append(f"MISSING_FROM_MANIFEST: {rel}")

        src = (ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(src, filename=rel)
        for node in ast.walk(tree):
            candidates: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("api"):
                mod = node.module
                candidates.append(mod)
                for alias in node.names:
                    candidates.append(f"{mod}.{alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("api"):
                        candidates.append(alias.name)
            for dotted in candidates:
                parts = dotted.split(".")
                py_rel = "/".join(parts) + ".py"
                pkg_rel = "/".join(parts) + "/__init__.py"
                if (ROOT / py_rel).exists() and py_rel not in manifest:
                    missing.append(f"{rel} imports {py_rel} (not in FILES_TO_SYNC)")
                elif (ROOT / pkg_rel).exists() and pkg_rel not in manifest:
                    missing.append(f"{rel} imports {pkg_rel} (not in FILES_TO_SYNC)")

    if missing:
        raise RuntimeError("HF sync manifest gaps detected:\n  - " + "\n  - ".join(sorted(set(missing))))
    print(f"[OK] HF sync manifest covers all {len(CRITICAL_MODULES)} modules and their local api.* imports.")


def _run_offline_pytest() -> int:
    suites = [t for t in OFFLINE_TEST_SUITES if (ROOT / t).exists()]
    cmd = [sys.executable, "-m", "pytest", *suites, "-q"]
    print(f"[RUN] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    return int(proc.returncode)


def main() -> int:
    _compile_all()
    _check_hf_manifest_imports()
    rc = _run_offline_pytest()
    if rc == 0:
        print("[PASS] All chat/quant/optimizer/automation offline invariants passed.")
    else:
        print(f"[FAIL] pytest exited with code {rc}.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
