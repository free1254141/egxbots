"""Periodic audit of ARTORO Agentic Chat cost, token consumption, and latency (Before vs After Update).

Usage:
    python scripts/audit_chat_cost_and_latency.py
    python scripts/audit_chat_cost_and_latency.py --limit 1000 --update-doc
    python scripts/audit_chat_cost_and_latency.py --limit 1000 --since 2026-11-21T17:32:00Z
"""

import argparse
from collections import Counter
import os
import re
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

CAIRO_TZ = timezone(timedelta(hours=2))

# Deployment cutoff for commit 94105490 / HF 0fd31aad (2026-11-17 21:11:33 Cairo = 19:11:33 UTC)
UPDATE_CUTOFF_UTC = "2026-11-17T19:11:33"

# DeepSeek-V3 (deepseek-chat) official pricing in USD per 1M tokens
PRICE_HIT_PER_1M = 0.028
PRICE_MISS_PER_1M = 0.280
PRICE_OUT_PER_1M = 0.420

# Baseline prompt prefix estimates used ONLY for legacy rows without measured `metadata.usage`
EST_STATIC_PREFIX_TOKENS = 4600
EST_DYNAMIC_BEFORE_TOKENS = 1900  # includes seconds-changing date_context + redundant get_stock_levels
EST_DYNAMIC_AFTER_TOKENS = 1550   # hourly bucket date_context + no get_stock_levels duplication

DEFAULT_DOC_PATH = ROOT_DIR / "docs" / "CHAT_COST_TOKEN_LATENCY_TRACKER.md"
QUALITY_LOG_START = "<!-- QUALITY_AUDIT_LOG_START -->"
QUALITY_LOG_END = "<!-- QUALITY_AUDIT_LOG_END -->"


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    idx = (len(sorted_vals) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def _latency_stats(values: List[int]) -> Dict[str, Any]:
    clean = sorted(float(v) for v in values if v is not None and v > 0)
    if not clean:
        return {"count": 0, "avg_ms": 0, "median_ms": 0, "p90_ms": 0, "p95_ms": 0, "max_ms": 0}
    return {
        "count": len(clean),
        "avg_ms": int(round(sum(clean) / len(clean))),
        "median_ms": int(round(statistics.median(clean))),
        "p90_ms": int(round(_percentile(clean, 0.90))),
        "p95_ms": int(round(_percentile(clean, 0.95))),
        "max_ms": int(round(clean[-1])),
    }


def _estimate_legacy_tokens_and_cost(row: Dict[str, Any], is_after: bool) -> Dict[str, float]:
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if bool(meta.get("cached")):
        return {
            "prompt_tokens": 0.0,
            "cache_hit_tokens": 0.0,
            "cache_miss_tokens": 0.0,
            "completion_tokens": 0.0,
            "cost_usd": 0.0,
        }
    content = str(row.get("content") or "")
    # Arabic + markdown averages ~2.6 chars per token on DeepSeek BPE
    comp_tokens = max(round(len(content) / 2.6), 40)
    # 2 LLM rounds typical (Round 1 tool selection + Round 2 synthesis)
    dyn_tokens = EST_DYNAMIC_AFTER_TOKENS if is_after else EST_DYNAMIC_BEFORE_TOKENS
    if is_after:
        # Hourly date_context + static prompt keeps Round 1 prefix warm across users too
        hit_tokens = EST_STATIC_PREFIX_TOKENS * 2.0 + 400.0
        miss_tokens = dyn_tokens
    else:
        # Per-second date_context forces cache miss on Round 1 dynamic tail, Round 2 hits Round 1 prefix
        hit_tokens = EST_STATIC_PREFIX_TOKENS * 2.0
        miss_tokens = dyn_tokens * 1.35

    prompt_tokens = hit_tokens + miss_tokens
    cost_usd = (
        (hit_tokens / 1_000_000) * PRICE_HIT_PER_1M
        + (miss_tokens / 1_000_000) * PRICE_MISS_PER_1M
        + (comp_tokens / 1_000_000) * PRICE_OUT_PER_1M
    )
    return {
        "prompt_tokens": prompt_tokens,
        "cache_hit_tokens": hit_tokens,
        "cache_miss_tokens": miss_tokens,
        "completion_tokens": float(comp_tokens),
        "cost_usd": cost_usd,
    }


def summarize_cohort(rows: List[Dict[str, Any]], is_after: bool) -> Dict[str, Any]:
    total = len(rows)
    cached_rows = []
    live_rows = []
    measured_usage_rows = []
    by_source: Dict[str, List[Dict[str, Any]]] = {}

    all_latencies: List[int] = []
    cached_latencies: List[int] = []
    live_latencies: List[int] = []
    char_lengths: List[int] = []

    est_total_cost = 0.0
    est_total_prompt = 0.0
    est_total_comp = 0.0

    meas_cost_sum = 0.0
    meas_max_cost = 0.0
    meas_prompt_sum = 0
    meas_comp_sum = 0
    meas_hit_sum = 0
    meas_miss_sum = 0

    guard_warning_rows = 0
    guard_warning_counts: Counter = Counter()

    for r in rows:
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        is_cached = bool(meta.get("cached"))
        lat = r.get("latency_ms") or meta.get("latency_ms") or 0
        try:
            lat_int = int(lat)
        except Exception:
            lat_int = 0

        gw_list = meta.get("guard_warnings") if isinstance(meta.get("guard_warnings"), list) else []
        if gw_list:
            guard_warning_rows += 1
            for w in gw_list:
                guard_warning_counts[str(w)] += 1

        content = str(r.get("content") or "")
        char_lengths.append(len(content))

        src = str(meta.get("chat_source") or "unknown")
        by_source.setdefault(src, []).append(r)

        if lat_int > 0:
            all_latencies.append(lat_int)

        if is_cached:
            cached_rows.append(r)
            if lat_int > 0:
                cached_latencies.append(lat_int)
        else:
            live_rows.append(r)
            if lat_int > 0:
                live_latencies.append(lat_int)

        usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else None
        if usage and (
            usage.get("total_tokens") is not None
            or usage.get("cost_usd") is not None
            or usage.get("vip_response_cached") is True
        ):
            row_cost = float(usage.get("cost_usd") or 0.0)
            if row_cost > meas_max_cost:
                meas_max_cost = row_cost
            measured_usage_rows.append(r)
            meas_cost_sum += row_cost
            meas_prompt_sum += int(usage.get("prompt_tokens") or 0)
            meas_comp_sum += int(usage.get("completion_tokens") or 0)
            meas_hit_sum += int(usage.get("prompt_cache_hit_tokens") or 0)
            meas_miss_sum += int(usage.get("prompt_cache_miss_tokens") or 0)

            est_total_cost += row_cost
            est_total_prompt += float(usage.get("prompt_tokens") or 0)
            est_total_comp += float(usage.get("completion_tokens") or 0)
        else:
            est = _estimate_legacy_tokens_and_cost(r, is_after=is_after)
            est_total_cost += est["cost_usd"]
            est_total_prompt += est["prompt_tokens"]
            est_total_comp += est["completion_tokens"]

    source_summary: Dict[str, Dict[str, Any]] = {}
    for src, s_rows in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
        s_lats = []
        s_cached = 0
        s_cost_sum = 0.0
        for sr in s_rows:
            sm = sr.get("metadata") if isinstance(sr.get("metadata"), dict) else {}
            if bool(sm.get("cached")):
                s_cached += 1
            su = sm.get("usage") if isinstance(sm.get("usage"), dict) else None
            if su and su.get("cost_usd") is not None:
                s_cost_sum += float(su.get("cost_usd") or 0.0)
            sl = sr.get("latency_ms") or sm.get("latency_ms") or 0
            if sl:
                try:
                    s_lats.append(int(sl))
                except Exception:
                    pass
        st = _latency_stats(s_lats)
        source_summary[src] = {
            **st,
            "count": len(s_rows),
            "cached": s_cached,
            "cache_rate_pct": round((s_cached / len(s_rows)) * 100.0, 1) if s_rows else 0.0,
            "measured_cost_sum_usd": round(s_cost_sum, 6),
        }

    avg_chars = int(round(sum(char_lengths) / len(char_lengths))) if char_lengths else 0
    est_avg_cost = (est_total_cost / total) if total else 0.0
    est_avg_prompt = int(round(est_total_prompt / total)) if total else 0
    est_avg_comp = int(round(est_total_comp / total)) if total else 0

    meas_n = len(measured_usage_rows)
    meas_live_rows = [
        r for r in measured_usage_rows
        if not bool((r.get("metadata") or {}).get("cached"))
    ]
    meas_hit_pct = round((meas_hit_sum / meas_prompt_sum) * 100.0, 1) if meas_prompt_sum > 0 else 0.0

    created_vals = [str(r.get("created_at") or "")[:19] for r in rows if r.get("created_at")]
    window_start = min(created_vals) if created_vals else "—"
    window_end = max(created_vals) if created_vals else "—"

    return {
        "total": total,
        "cached_count": len(cached_rows),
        "live_count": len(live_rows),
        "cache_hit_pct": round((len(cached_rows) / total) * 100.0, 1) if total else 0.0,
        "latency_all": _latency_stats(all_latencies),
        "latency_cached": _latency_stats(cached_latencies),
        "latency_live": _latency_stats(live_latencies),
        "avg_chars": avg_chars,
        "by_source": source_summary,
        "window_start_utc": window_start,
        "window_end_utc": window_end,
        # Mixed/estimated totals across all rows
        "avg_cost_usd": est_avg_cost,
        "cost_per_1k_usd": round(est_avg_cost * 1000.0, 4),
        "avg_prompt_tokens": est_avg_prompt,
        "avg_completion_tokens": est_avg_comp,
        # Strictly measured rows with `metadata.usage`
        "measured_count": meas_n,
        "measured_live_count": len(meas_live_rows),
        "measured_total_cost_usd": round(meas_cost_sum, 6) if meas_n else 0.0,
        "measured_max_cost_usd": round(meas_max_cost, 6) if meas_n else 0.0,
        "measured_avg_cost_usd": (meas_cost_sum / meas_n) if meas_n else None,
        "measured_avg_prompt_tokens": int(round(meas_prompt_sum / meas_n)) if meas_n else None,
        "measured_avg_comp_tokens": int(round(meas_comp_sum / meas_n)) if meas_n else None,
        "measured_prefix_cache_hit_pct": meas_hit_pct if meas_prompt_sum > 0 else None,
        # Deterministic output guardrail stats
        "guard_warning_rows": guard_warning_rows,
        "guard_warning_counts": dict(guard_warning_counts.most_common()),
    }


def _get_supabase_client():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def fetch_chat_rows(limit: int = 1000, since_utc: Optional[str] = None) -> List[Dict[str, Any]]:
    sb = _get_supabase_client()
    q = (
        sb.table("ai_chat_messages")
        .select("id,session_id,role,latency_ms,metadata,created_at,content")
        .eq("role", "assistant")
    )
    if since_utc:
        q = q.gte("created_at", since_utc)
    res = (
        q.order("created_at", desc=True)
        .limit(min(max(int(limit), 10), 1000))
        .execute()
    )
    return res.data or []


def fetch_before_baseline_rows(limit: int = 200) -> List[Dict[str, Any]]:
    """Fallback query for pre-cutoff baseline rows once post-update rows exceed fetch limit."""
    sb = _get_supabase_client()
    res = (
        sb.table("ai_chat_messages")
        .select("id,session_id,role,latency_ms,metadata,created_at,content")
        .eq("role", "assistant")
        .lt("created_at", UPDATE_CUTOFF_UTC)
        .order("created_at", desc=True)
        .limit(min(max(int(limit), 10), 1000))
        .execute()
    )
    return res.data or []


def _fmt_sec(ms: Optional[int]) -> str:
    if not ms:
        return "—"
    return f"{ms / 1000.0:.2f}s ({ms:,} ms)"


def _extract_existing_snapshots(doc_path: Path) -> List[str]:
    if not doc_path.exists():
        return []
    text = doc_path.read_text(encoding="utf-8")
    marker = "<!-- SNAPSHOT_HISTORY_START -->"
    end_marker = "<!-- SNAPSHOT_HISTORY_END -->"
    if marker not in text or end_marker not in text:
        return []
    block = text.split(marker, 1)[1].split(end_marker, 1)[0]
    rows = []
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("| 20"):
            rows.append(s)
    return rows


def _extract_existing_quality_log(doc_path: Path) -> str:
    if not doc_path.exists():
        return ""
    text = doc_path.read_text(encoding="utf-8")
    if QUALITY_LOG_START not in text or QUALITY_LOG_END not in text:
        return ""
    return text.split(QUALITY_LOG_START, 1)[1].split(QUALITY_LOG_END, 1)[0].strip()


def render_markdown(
    before: Dict[str, Any],
    after: Dict[str, Any],
    existing_snapshots: List[str],
    existing_quality_log: str = "",
) -> str:
    now_cairo = datetime.now(CAIRO_TZ)
    today_label = now_cairo.strftime("%Y-%m-%d %H:%M")

    # Build snapshot line for today (replace existing entry for same date if re-run same day)
    today_date = now_cairo.strftime("%Y-%m-%d")
    after_meas_cost = (
        f"${after['measured_avg_cost_usd']:.5f}"
        if after["measured_avg_cost_usd"] is not None
        else f"~${after['avg_cost_usd']:.5f} (تقديري)"
    )
    after_prefix_hit = (
        f"{after['measured_prefix_cache_hit_pct']}%"
        if after["measured_prefix_cache_hit_pct"] is not None
        else "قيد التجميع"
    )
    new_snap = (
        f"| {today_label} | {after['total']} | {after['cache_hit_pct']}% | "
        f"{_fmt_sec(after['latency_all']['avg_ms'])} | {_fmt_sec(after['latency_live']['avg_ms'])} | "
        f"{after['measured_count']} | {after_prefix_hit} | {after_meas_cost} | "
        f"${after['cost_per_1k_usd']:.3f} |"
    )
    filtered_snaps = [s for s in existing_snapshots if not s.startswith(f"| {today_date}")]
    all_snaps = filtered_snaps + [new_snap]

    def _source_rows_md(src_map: Dict[str, Dict[str, Any]]) -> str:
        if not src_map:
            return "| — | 0 | 0% | — | — |\n"
        lines = []
        for src, st in src_map.items():
            lines.append(
                f"| `{src}` | {st['count']} | {st['cache_rate_pct']}% | "
                f"{_fmt_sec(st['avg_ms'])} | {_fmt_sec(st['p90_ms'])} |"
            )
        return "\n".join(lines)

    guard_line = ""
    if after.get("guard_warning_rows", 0) > 0:
        gw_pairs = ", ".join(f"`{k}`×{v}" for k, v in (after.get("guard_warning_counts") or {}).items())
        guard_line = (
            f"\n- **تدخلات الحارس الحتمي (`output_guard`):** `{after['guard_warning_rows']}` رد "
            f"({gw_pairs})"
        )

    meas_section_after = (
        f"- **الصفوف المقاسة فعلياً (`metadata.usage`):** `{after['measured_count']}` رد "
        f"(`{after['measured_live_count']}` رد LLM مباشر)\n"
        f"- **متوسط التوكن المقاس/رد:** Prompt `{after['measured_avg_prompt_tokens']:,}` | "
        f"Output `{after['measured_avg_comp_tokens']:,}` | "
        f"**Prefix Cache Hit:** `{after_prefix_hit}`\n"
        f"- **متوسط التكلفة المقاسة/رد:** `${after['measured_avg_cost_usd']:.6f}` "
        f"(`~${after['measured_avg_cost_usd'] * 1000:.3f}` لكل 1,000 رد | "
        f"إجمالي العينة: `${after['measured_total_cost_usd']:.4f}` | أعلى رد: `${after['measured_max_cost_usd']:.5f}`)"
        f"{guard_line}"
        if after["measured_count"] > 0
        else "- **الصفوف المقاسة فعلياً (`metadata.usage`):** `0` حتى الآن — تم تفعيل التسجيل الدقيق في `pipeline.py` و`router.py` و`native_telegram_vip_chat.py`، وسيبدأ الامتلاء التلقائي فور نشر الكود واستقبال ردود جديدة."
    )

    quality_body = (
        existing_quality_log.strip()
        if existing_quality_log and existing_quality_log.strip()
        else "*لا توجد مراجعات نوعية مسجلة بعد — اتبع [chat-audit SKILL](../.agent/skills/chat-audit/SKILL.md) لإضافة مراجعة جديدة.*"
    )

    return f"""# 📊 متابعة تكلفة الشات واستهلاك التوكن وزمن الرد (قبل وبعد التحديث)

> **آخر تحديث تلقائي:** `{today_label} (توقيت القاهرة)`
> **نقطة الفصل المرجعية (Update Cutoff):** `2026-11-17 21:11 القاهرة` (`{UPDATE_CUTOFF_UTC} UTC` — كوميت `94105490` / HF `0fd31aad`)
> **أداة التحديث الدوري (كل يومين):**
> ```bash
> python scripts/audit_chat_cost_and_latency.py --limit 1000 --update-doc
> ```

---

## 1. جدول تسعير DeepSeek-V3 المعتمد في الحسابات
| البند | السعر لكل 1M توكن | ملاحظة |
|---|---|---|
| Input Cache Hit (`prompt_cache_hit_tokens`) | **\\$0.028** | خصم **90%** على البادئة الثابتة + التوقيت الساعي |
| Input Cache Miss (`prompt_cache_miss_tokens`) | **\\$0.280** | الجزء المتغير + مخرجات الأدوات + سؤال المستخدم |
| Output Tokens (`completion_tokens`) | **\\$0.420** | النص المولّد في الإجابة النهائية |

---

## 2. مقارنة الإنتاج الفعلية من قاعدة البيانات (`ai_chat_messages`) — قبل التحديث مقابل بعده

| المؤشر | قبل التحديث (`< 2026-11-17 21:11`) | بعد التحديث (`>= 2026-11-17 21:11`) | الفرق / الملاحظة |
|---|---:|---:|---|
| **النطاق الزمني (UTC)** | `{before['window_start_utc']}` → `{before['window_end_utc']}` | `{after['window_start_utc']}` → `{after['window_end_utc']}` | عينة: قبل {before['total']} / بعد {after['total']} رد |
| **إجمالي الردود** | {before['total']} | {after['total']} | — |
| **ردود VIP Cache (0 توكن)** | {before['cached_count']} ({before['cache_hit_pct']}%) | {after['cached_count']} ({after['cache_hit_pct']}%) | تزيد مع تكرار أسئلة اليوم |
| **ردود LLM المباشرة** | {before['live_count']} | {after['live_count']} | — |
| **متوسط زمن الرد (الكل)** | {_fmt_sec(before['latency_all']['avg_ms'])} | {_fmt_sec(after['latency_all']['avg_ms'])} | يشمل الكاش والمباشر |
| **الوسيط / P90 (الكل)** | {_fmt_sec(before['latency_all']['median_ms'])} / {_fmt_sec(before['latency_all']['p90_ms'])} | {_fmt_sec(after['latency_all']['median_ms'])} / {_fmt_sec(after['latency_all']['p90_ms'])} | — |
| **متوسط زمن الرد (LLM مباشر فقط)** | {_fmt_sec(before['latency_live']['avg_ms'])} | {_fmt_sec(after['latency_live']['avg_ms'])} | بدون احتساب الكاش |
| **الوسيط / P90 (LLM مباشر)** | {_fmt_sec(before['latency_live']['median_ms'])} / {_fmt_sec(before['latency_live']['p90_ms'])} | {_fmt_sec(after['latency_live']['median_ms'])} / {_fmt_sec(after['latency_live']['p90_ms'])} | — |
| **متوسط زمن الرد (VIP Cache)** | {_fmt_sec(before['latency_cached']['avg_ms'])} | {_fmt_sec(after['latency_cached']['avg_ms'])} | استجابة شبه فورية |
| **متوسط طول الإجابة (حرف)** | {before['avg_chars']:,} | {after['avg_chars']:,} | تعكس ثراء المحتوى |
| **متوسط توكن الإدخال/رد (مقدّر/مقاس)** | {before['avg_prompt_tokens']:,} | {after['avg_prompt_tokens']:,} | تشمل جولتي Round 0+1 |
| **متوسط توكن الإخراج/رد (مقدّر/مقاس)** | {before['avg_completion_tokens']:,} | {after['avg_completion_tokens']:,} | — |
| **متوسط التكلفة للرد** | \\${before['avg_cost_usd']:.5f} | \\${after['avg_cost_usd']:.5f} | *(تقديري للصفوف القديمة قبل `metadata.usage`)* |
| **التكلفة لكل 1,000 رد** | **\\${before['cost_per_1k_usd']:.3f}** | **\\${after['cost_per_1k_usd']:.3f}** | تتجه للانخفاض مع VIP + Prefix Cache |

### حالة القياس الفعلي الدقيق (`metadata.usage` من DeepSeek API)
{meas_section_after}

### توزيع القنوات — قبل التحديث
| القناة (`chat_source`) | العدد | نسبة VIP Cache | متوسط الزمن | P90 |
|---|---:|---:|---:|---:|
{_source_rows_md(before['by_source'])}

### توزيع القنوات — بعد التحديث
| القناة (`chat_source`) | العدد | نسبة VIP Cache | متوسط الزمن | P90 |
|---|---:|---:|---:|---:|
{_source_rows_md(after['by_source'])}

---

## 3. اختبار المقارنة المضبوط لسؤال تحليل السهم (`حلل سهم فوري FWRY`)
*(تم قياسه محلياً قبل التعديل وبعده على نفس الاستفسار بدون كاش VIP مسبق)*

| المقياس | قبل التحديث | بعد التحديث | التغيير |
|---|---:|---:|---|
| **الأدوات المستدعاة (Round 0 متوازي)** | 3 (`get_stock`, `get_stock_levels`, `get_news`) | 6 (`get_stock`, `get_fair_value`, `get_news`, `get_disclosures`, `get_price_traps`, `get_stock_levels`) — ثم أُزيل تكرار `get_stock_levels` | تغطية شاملة (فني + قيمة عادلة + إفصاحات + مصائد) |
| **زمن الرد الكلي** | `15.34s` | `18.64s` *(بوجود 6 أدوات)* | زمن مقارب مع ضعف المحتوى |
| **طول الرد** | `2,855` حرف | `3,518` حرف | أعمق (+VWAP، بولينجر، القيمة العادلة، Risk/Reward، دعم S2 مستقل) |
| **تثبيت Prefix Cache في `date_context`** | يتغير كل ثانية (`%H:%M:%S`) ❌ | ثابت بالساعة (`%H:00`) ✅ | رفع توقع إصابة كاش DeepSeek بين المستخدمين |
| **إزالة تكرار `get_stock_levels`** | يُستدعى مع `get_stock` و`get_comparison` ❌ | مدمج داخل `get_stock` ومحذوف من `get_comparison` ✅ | توفير ~250 توكن/طلب واستعلام DB مكرر |

---

## 4. سجل المتابعة الدوري (كل يومين)
*يتم تحديث هذا الجدول تلقائياً عند تشغيل `python scripts/audit_chat_cost_and_latency.py --limit 1000 --update-doc`.*

<!-- SNAPSHOT_HISTORY_START -->
| التاريخ (القاهرة) | ردود ما بعد التحديث | نسبة VIP Cache | متوسط الزمن (الكل) | متوسط الزمن (LLM مباشر) | صفوف `usage` المقاسة | نسبة Prefix Hit المقاسة | متوسط التكلفة/رد | التكلفة / 1,000 رد |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(all_snaps)}
<!-- SNAPSHOT_HISTORY_END -->

---

## 5. قائمة المراجعة الدورية (عند طلب «راجع الشات» أو كل يومين)
1. شغّل نافذة الفحص التراكمي/الحديث: `python scripts/audit_chat_cost_and_latency.py --limit 1000 --since <LAST_DEPLOY_UTC>` ثم حدّث الوثيقة: `python scripts/audit_chat_cost_and_latency.py --limit 1000 --update-doc`
2. اتبع البروتوكول الكامل في [chat-audit SKILL](../.agent/skills/chat-audit/SKILL.md) (فحص منطقية الردود، تدخلات `output_guard`، شكاوى المستخدمين، الكاش، التكلفة، الزمن، وأثر الكوميتات).
3. راجع عمود **نسبة Prefix Hit المقاسة**: يجب أن يكون أعلى من **65%–75%** في الردود المباشرة؛ لو انخفض، تأكد من عدم إدراج قيم متغيرة في `AGENTIC_SYSTEM_PROMPT` أو `date_context`.
4. راجع عمود **نسبة VIP Cache**: الأسئلة الشائعة اليومية («حلل سهم X»، «وضع السوق»، «التوصيات»، «الفرص البديلة») يجب أن ترفع النسبة تدريجياً فتُخدم بـ **0 توكن** وبزمن `< 0.5s`.
5. راقب **متوسط زمن الرد (LLM مباشر)** و**أعلى 10 ردود تكلفة** لكل قناة (`web_chat` مقابل `telegram_private` و`scheduled_automation`) لمنع تضخم التوكن في جلسات المحفظة الطويلة.

---

## 6. سجل المراجعة النوعية والمنطقية وأثر التعديلات
*يُحفظ هذا القسم تلقائياً عند تشغيل `--update-doc`. اتبع [chat-audit SKILL](../.agent/skills/chat-audit/SKILL.md) لإضافة مراجعة جديدة دون حذف السجلات السابقة.*

{QUALITY_LOG_START}
{quality_body}
{QUALITY_LOG_END}
"""


def print_window_report(window_rows: List[Dict[str, Any]], since_label: str) -> None:
    st = summarize_cohort(window_rows, is_after=True)
    l_all = st["latency_all"]
    l_cached = st["latency_cached"]
    l_live = st["latency_live"]
    print(
        f"\n[WINDOW since={since_label}] total={st['total']} "
        f"(UTC {st['window_start_utc']} -> {st['window_end_utc']})"
    )
    print(
        f"  VIP Cache: {st['cached_count']}/{st['total']} ({st['cache_hit_pct']}%) | "
        f"measured_usage={st['measured_count']} | "
        f"prefix_hit={st['measured_prefix_cache_hit_pct']}%"
    )
    print(
        f"  Cost (measured): total=${st['measured_total_cost_usd']:.5f} | "
        f"avg_all=${st['avg_cost_usd']:.5f} (${st['cost_per_1k_usd']:.3f}/1k) | "
        f"max=${st['measured_max_cost_usd']:.5f}"
    )
    print(
        f"  Latency ALL   : avg={l_all['avg_ms']}ms | p50={l_all['median_ms']}ms | "
        f"p90={l_all['p90_ms']}ms | p95={l_all['p95_ms']}ms | max={l_all['max_ms']}ms"
    )
    print(
        f"  Latency CACHED: n={l_cached['count']} avg={l_cached['avg_ms']}ms | "
        f"p50={l_cached['median_ms']}ms | max={l_cached['max_ms']}ms"
    )
    print(
        f"  Latency LIVE  : n={l_live['count']} avg={l_live['avg_ms']}ms | "
        f"p50={l_live['median_ms']}ms | p95={l_live['p95_ms']}ms | max={l_live['max_ms']}ms"
    )
    print(f"  Guard warnings: rows={st['guard_warning_rows']} | counts={st['guard_warning_counts']}")
    print("  By source:")
    for src, sdata in st["by_source"].items():
        print(
            f"    - {src}: n={sdata['count']} | cached={sdata['cached']} ({sdata['cache_rate_pct']}%) | "
            f"cost=${sdata['measured_cost_sum_usd']:.5f} | avg_lat={sdata['avg_ms']}ms"
        )

    def _row_cost(r: Dict[str, Any]) -> float:
        m = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        u = m.get("usage") if isinstance(m.get("usage"), dict) else {}
        return float(u.get("cost_usd") or 0.0)

    def _row_lat(r: Dict[str, Any]) -> int:
        m = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        try:
            return int(r.get("latency_ms") or m.get("latency_ms") or 0)
        except Exception:
            return 0

    print("  Top 5 most expensive:")
    for r in sorted(window_rows, key=_row_cost, reverse=True)[:5]:
        m = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        u = m.get("usage") if isinstance(m.get("usage"), dict) else {}
        print(
            f"    * {str(r.get('created_at') or '')[:19]} | ${ _row_cost(r):.5f} | "
            f"in={u.get('prompt_tokens')} out={u.get('completion_tokens')} | "
            f"lat={_row_lat(r)}ms | src={m.get('chat_source')} | "
            f"key={m.get('cache_key')} | gw={m.get('guard_warnings')}"
        )

    print("  Top 5 slowest:")
    for r in sorted(window_rows, key=_row_lat, reverse=True)[:5]:
        m = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        print(
            f"    * {str(r.get('created_at') or '')[:19]} | lat={_row_lat(r)}ms | "
            f"${_row_cost(r):.5f} | src={m.get('chat_source')} | cached={m.get('cached')} | "
            f"key={m.get('cache_key')} | gw={m.get('guard_warnings')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit chat cost, tokens, and latency before vs after update.")
    parser.add_argument("--limit", type=int, default=1000, help="Number of recent assistant rows to inspect (max 1000).")
    parser.add_argument("--since", type=str, default=None, help="Optional ISO UTC cutoff for window audit report (e.g. 2026-11-21T17:32:00Z).")
    parser.add_argument("--update-doc", action="store_true", help="Write/update docs/CHAT_COST_TOKEN_LATENCY_TRACKER.md")
    parser.add_argument("--doc-path", type=str, default=str(DEFAULT_DOC_PATH), help="Target markdown doc path")
    args = parser.parse_args()

    if args.since and not args.update_doc:
        window_rows = fetch_chat_rows(limit=args.limit, since_utc=args.since)
        print_window_report(window_rows, args.since)
        return

    rows = fetch_chat_rows(limit=args.limit)
    before_rows = [r for r in rows if str(r.get("created_at") or "") < UPDATE_CUTOFF_UTC]
    if not before_rows:
        before_rows = fetch_before_baseline_rows(limit=200)
    after_rows = [r for r in rows if str(r.get("created_at") or "") >= UPDATE_CUTOFF_UTC]

    before_stats = summarize_cohort(before_rows, is_after=False)
    after_stats = summarize_cohort(after_rows, is_after=True)

    print(f"Fetched {len(rows)} assistant messages (Before={before_stats['total']}, After={after_stats['total']})")
    print(
        f"[BEFORE] cache_hit={before_stats['cache_hit_pct']}% | "
        f"avg_lat={before_stats['latency_all']['avg_ms']}ms | "
        f"live_avg={before_stats['latency_live']['avg_ms']}ms | "
        f"est_cost/1k=${before_stats['cost_per_1k_usd']:.3f}"
    )
    print(
        f"[AFTER ] cache_hit={after_stats['cache_hit_pct']}% | "
        f"avg_lat={after_stats['latency_all']['avg_ms']}ms | "
        f"live_avg={after_stats['latency_live']['avg_ms']}ms | "
        f"measured_rows={after_stats['measured_count']} | "
        f"prefix_hit={after_stats['measured_prefix_cache_hit_pct']}% | "
        f"est_cost/1k=${after_stats['cost_per_1k_usd']:.3f}"
    )

    if args.since:
        window_rows = [r for r in rows if str(r.get("created_at") or "") >= args.since]
        print_window_report(window_rows, args.since)

    if args.update_doc:
        doc_p = Path(args.doc_path)
        doc_p.parent.mkdir(parents=True, exist_ok=True)
        existing_snaps = _extract_existing_snapshots(doc_p)
        existing_quality = _extract_existing_quality_log(doc_p)
        md = render_markdown(before_stats, after_stats, existing_snaps, existing_quality)
        doc_p.write_text(md, encoding="utf-8")
        print(f"Updated doc: {doc_p}")


if __name__ == "__main__":
    main()
