"""
scripts/chat_live_eval.py
Automated Live End-to-End Evaluation Gate for ARTORO Agentic Chat.

Run before pushing chat backend changes (`python scripts/chat_live_eval.py`)
to catch cross-market hijacking, poisoned error caching, stale-quote omissions,
broken currency labels, and mental-math / zakat hallucinations.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv(os.path.join(REPO_ROOT, ".env"))
load_dotenv(os.path.join(REPO_ROOT, "web", ".env.local"), override=False)

from api.agentic_chat.analysis_cache import get_vip_analysis_cache
from api.agentic_chat.pipeline import run_agentic_chat_stream


EvalCheck = Tuple[str, Callable[[Dict[str, Any]], bool]]


def _build_cases() -> List[Tuple[int, str, str, List[EvalCheck]]]:
    return [
        (
            1,
            "حلل سهم IENG",
            "EGX",
            [
                ("suggests INEG", lambda r: "INEG" in (r.get("reply") or "")),
                ("done cache_key falsy", lambda r: not r.get("cache_key")),
                (
                    "not saved in vip_stock_IENG cache",
                    lambda _r: get_vip_analysis_cache("vip_stock_IENG", market="EGX") is None,
                ),
            ],
        ),
        (
            2,
            "سهم FCMD ده سعره بايظ عندكم",
            "EGX",
            [
                ("mentions stale session date 2026-09-23", lambda r: "2026-09-23" in (r.get("reply") or "")),
            ],
        ),
        (
            3,
            "حلل اعمار",
            "DFM",
            [
                ("mentions EMAAR", lambda r: "EMAAR" in (r.get("reply") or "").upper()),
                ("uses د.إ currency", lambda r: "د.إ" in (r.get("reply") or "")),
                ("does not hijack EMFD", lambda r: "EMFD" not in (r.get("reply") or "").upper()),
                ("does not leak ج.م", lambda r: "ج.م" not in (r.get("reply") or "")),
            ],
        ),
        (
            4,
            "حلل اعمار",
            "EGX",
            [
                ("resolves EMFD in EGX", lambda r: "EMFD" in (r.get("reply") or "").upper()),
            ],
        ),
        (
            5,
            "حلل سهم QNBK.QA",
            "QSE",
            [
                ("uses ر.ق currency", lambda r: "ر.ق" in (r.get("reply") or "")),
                ("does not leak ج.م", lambda r: "ج.م" not in (r.get("reply") or "")),
                ("no Graham base-mixing 'خصم 23%'", lambda r: "خصم 23%" not in (r.get("reply") or "")),
            ],
        ),
        (
            6,
            "حلّل لي سهم PHDC فنياً وقولّي مناطق الدخول والخروج المناسبة",
            "EGX",
            [
                ("uses ج.م currency", lambda r: "ج.م" in (r.get("reply") or "")),
                ("no guessed '~2.0' support R/R", lambda r: "~2.0" not in (r.get("reply") or "")),
            ],
        ),
        (
            7,
            "قارن بين COMI و فوري بس قوليلي مين احسن للزكاة",
            "EGX",
            [
                ("no fabricated '1.5%' purification", lambda r: "1.5%" not in (r.get("reply") or "")),
                ("no fabricated '25 ج.م' zakat", lambda r: "25 ج.م" not in (r.get("reply") or "")),
            ],
        ),
        (
            8,
            "حلل سهم 2222",
            "TADAWUL",
            [
                ("uses ر.س currency", lambda r: "ر.س" in (r.get("reply") or "")),
            ],
        ),
    ]


async def _run_case(cid: int, msg: str, market: str, checks: List[EvalCheck]) -> Dict[str, Any]:
    t0 = time.time()
    done: Dict[str, Any] = {}
    err: Optional[str] = None
    try:
        async for chunk in run_agentic_chat_stream(
            message=msg,
            history=[],
            user_id="11111111-1111-1111-1111-111111111111",
            is_pro=True,
            market=market,
        ):
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    ev = json.loads(chunk[6:])
                    if ev.get("type") == "done":
                        done = ev
                except Exception:
                    pass
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"

    usage = done.get("usage") or {}
    rec: Dict[str, Any] = {
        "id": cid,
        "q": msg,
        "market": market,
        "cached": done.get("cached"),
        "cache_key": done.get("cache_key"),
        "lat_ms": int((time.time() - t0) * 1000),
        "cost": float(usage.get("cost_usd") or 0.0),
        "reply": done.get("reply") or "",
        "error": err,
    }
    check_results: List[Dict[str, Any]] = []
    for label, fn in checks:
        try:
            ok = (err is None) and bool(fn(rec))
        except Exception:
            ok = False
        check_results.append({"label": label, "passed": ok})
    rec["checks"] = check_results
    rec["passed"] = (err is None) and all(c["passed"] for c in check_results)
    return rec


async def _run_all(selected_ids: Optional[set], out_path: str) -> int:
    cases = [c for c in _build_cases() if not selected_ids or c[0] in selected_ids]
    results: List[Dict[str, Any]] = []
    total_cost = 0.0
    for cid, msg, market, checks in cases:
        rec = await _run_case(cid, msg, market, checks)
        results.append(rec)
        total_cost += float(rec.get("cost") or 0.0)
        status = "PASS" if rec["passed"] else "FAIL"
        failed_labels = [c["label"] for c in rec["checks"] if not c["passed"]]
        detail = f" | failed={failed_labels}" if failed_labels else ""
        if rec.get("error"):
            detail += f" | error={rec['error']}"
        print(
            f"[{status}] #{cid} {market:7s} | cached={rec['cached']} | key={rec['cache_key']} "
            f"| {rec['lat_ms']}ms | ${rec['cost']:.6f} | {msg}{detail}",
            flush=True,
        )

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    passed_count = sum(1 for r in results if r["passed"])
    print(f"\nSUMMARY: {passed_count}/{len(results)} PASS | total_cost=${total_cost:.6f} | saved={out_path}", flush=True)
    return 0 if passed_count == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live ARTORO chat regression evaluation.")
    parser.add_argument("--only", help="Comma-separated case IDs to run (e.g. 3,5)")
    parser.add_argument(
        "--out",
        default=os.path.join(tempfile.gettempdir(), "artoro_live_eval_results.json"),
        help="Path to write JSON evaluation results.",
    )
    args = parser.parse_args()
    selected = {int(x.strip()) for x in args.only.split(",") if x.strip()} if args.only else None
    return asyncio.run(_run_all(selected, args.out))


if __name__ == "__main__":
    sys.exit(main())
