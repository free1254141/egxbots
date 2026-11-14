"""
api/agentic_chat/vision.py
Complete Image & Portfolio Vision Analyzer for the Egyptian Stock Market (EGX).
Ported 1:1 from the legacy Vercel vision system (web/src/lib/ai/vision.ts and agentic-recovery.ts).
Powered by deepseek-flash with exact JSON extraction, Arab broker column mapping,
OCR decimal correction, market quote reconciliation, and deterministic fallbacks.
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

logger = logging.getLogger("agentic_chat.vision")

VISION_SYSTEM_PROMPT = """You are a financial image analyzer. Examine all attached image(s), combine the distinct visible evidence, and return ONLY a valid JSON object with no markdown fences, no comments, and no extra text.

Return one JSON object with these keys: image_type, symbols, technical_observations, market_depth, user_relevant_summary, uncertainties, confidence.
Do not copy this instruction, do not return a schema, and do not use placeholder values.

Rules:
- image_type: write exactly one word — portfolio (if it shows broker holdings/positions), chart (candlestick/line), table (price table), market_depth (bid/ask ladder), or unknown.
- symbols: for each visible ticker, add an entry: {"symbol":"TICKER","name":"Company name or empty","asset_type":"stock|fund|unknown","visible_values":{"price":null,"average_price":null,"change_pct":null,"return_pct":null,"quantity":null,"market_value":null,"cost_basis":null,"profit_loss":null,"cash_dividends":null}}. Preserve section membership: entries under a visible "Funds/الصناديق" heading are funds, not direct stocks; use unknown if grouping is unclear. Fill only fields whose labels are visible; use null otherwise. Write numbers without commas (50000 not 50,000). Preserve decimal points exactly (181.50 must be 181.5, never 18150).
- Arabic column mapping (very important):
  * "الوحدات" or "الكمية" = number of shares → quantity.
  * "متوسط سعر الوحدات" or "متوسط الشراء" = average purchase price → average_price, never current price.
  * "السعر" / "سعر الإغلاق" = visible current/closing price → price.
  * "القيمة السوقية" = market_value; "القيمة الشرائية" = cost_basis; "المكسب/الخسارة" = profit_loss. These are distinct from price and quantity.
  * "توزيعات نقدية" / "Cash Dividends" = cash_dividends; preserve this only when explicitly shown for that position.
  * "العائد %" (return %) = return_pct, never daily change_pct or quantity. Preserve its sign and decimal exactly.
- A number beside a ticker is not a share quantity unless a quantity/units heading is visibly attached to that column. In a portfolio holdings list, a cash gain and its percentage may share one cell: put the amount in profit_loss and the percentage in return_pct, not change_pct, quantity, or price.
- Preserve the sign and decimal of every percentage exactly as shown. Do not drop a visible minus sign or relabel "العائد %" as daily change.
- If the screen lists holdings with only market value and return % (no share count and no average price), preserve those in market_value and return_pct; leave price, average_price, and quantity null. Never infer missing fields.
- If the screen is a single-stock position detail, use units as quantity and average unit price as average_price.
- Return each ticker at most once.
- Never invent a ticker, price, or quantity. If the image text is unreadable, return unknown image_type and empty symbols array.
- confidence: a number from 0 to 1 reflecting how clearly you could read the image.
"""

VISION_TIMEOUT_SECONDS = 30.0
MAX_VISION_TOTAL_TIME_SECONDS = 50.0
VISION_MAX_OUTPUT_TOKENS = 3000


def coerce_number_or_null(value: Any) -> Optional[float]:
    """Extract a valid float from numeric or string input, removing Arabic/English currency symbols."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if not lowered or lowered in ("null", "undefined", "n/a", "na", "-", "—"):
            return None
        cleaned = re.sub(r"[,%]|\s|جنيه|ج\.م|egp|ريال|درهم|دولار|\$", "", lowered)
        try:
            val = float(cleaned)
            return val if math.isfinite(val) else None
        except Exception:
            return None
    return None


def normalize_visible_price(raw: Any, image_type: str) -> Optional[float]:
    """Correct OCR decimal drops (e.g. 18150 -> 181.50) for ungrouped Egyptian stock prices."""
    val = coerce_number_or_null(raw)
    if val is None:
        return None
    grouped = isinstance(raw, str) and "," in raw
    if not grouped and image_type in ("portfolio", "table") and 1000 <= val < 100000:
        return round(val / 100.0, 2)
    return val


def extract_json_from_response(raw: str) -> Optional[Dict[str, Any]]:
    """Robust extraction and repair of JSON output from vision model."""
    if not raw or not isinstance(raw, str):
        return None
    trimmed = raw.strip()
    trimmed = re.sub(r"^```(?:json)?\s*", "", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"\s*```$", "", trimmed, flags=re.IGNORECASE)
    normalized_raw = re.sub(
        r'("symbols"\s*:\s*\[[\s\S]*?)(\}\s*,\s*)("technical_observations"\s*:)',
        r"\1\2] , \3",
        trimmed,
    )

    candidates: List[str] = []
    start = -1
    depth = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(normalized_raw):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{" and depth == 0:
            start = i
        if ch == "{" and start >= 0:
            depth += 1
        if ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(normalized_raw[start : i + 1])
                start = -1

    candidates.sort(key=lambda s: len(s), reverse=True)

    for json_text in candidates:
        try:
            return json.loads(json_text)
        except Exception:
            pass

        # Repair comma thousands patterns: e.g. 50,000 -> 50000
        try:
            repaired = re.sub(r"(\d),(?=\d{3}(?:\D|$))", r"\1", json_text)
            return json.loads(repaired)
        except Exception:
            pass

        # Repair smart quotes and trailing commas
        try:
            repaired = (
                json_text.replace("“", '"')
                .replace("”", '"')
                .replace("‘", "'")
                .replace("’", "'")
            )
            repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
            repaired = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', repaired)
            return json.loads(repaired)
        except Exception:
            pass

        # Repair unclosed array before technical_observations
        try:
            repaired_array = re.sub(
                r'(\}\s*,\s*)("technical_observations"\s*:)', r"\1] , \2", json_text
            )
            return json.loads(repaired_array)
        except Exception:
            pass

    # Salvage visible uppercase symbols if full JSON failed
    stopwords = {"JSON", "NULL", "TABLE", "CHART", "PRICE", "SUMMARY", "STOCK", "IMAGE", "UNKNOWN", "USD", "EGP"}
    symbols = list(set([
        m.upper() for m in re.findall(r"\b[A-Z]{2,6}\b", trimmed) if m.upper() not in stopwords
    ]))
    if symbols:
        portfolio = bool(re.search(r"portfolio|holding|position|محفظ|سهم|shares", trimmed, re.IGNORECASE))
        return {
            "image_type": "portfolio" if portfolio else "table",
            "symbols": [
                {
                    "symbol": s,
                    "name": "",
                    "asset_type": "unknown",
                    "visible_values": {
                        "price": None,
                        "average_price": None,
                        "change_pct": None,
                        "return_pct": None,
                        "quantity": None,
                        "market_value": None,
                        "cost_basis": None,
                        "profit_loss": None,
                        "cash_dividends": None,
                    },
                }
                for s in symbols
            ],
            "technical_observations": [],
            "market_depth": {"total_bid": None, "total_ask": None, "spread": None},
            "user_relevant_summary": "تم استخراج الرموز الواضحة فقط؛ القيم الرقمية تحتاج تأكيد المستخدم.",
            "uncertainties": ["استُخدم استخراج آمن للرموز من رد Vision غير المنظم؛ لم يتم اعتماد أي سعر أو كمية."],
            "confidence": 0.35,
        }

    return None


def validate_vision_output(data: Any) -> Optional[Dict[str, Any]]:
    """Clean, normalize, and validate the vision JSON object according to the EGX contract."""
    if not data or not isinstance(data, dict):
        return None

    try:
        from api.stock_aliases import ARABIC_STOCK_MAPPINGS, resolve_stock_symbol
    except Exception:
        ARABIC_STOCK_MAPPINGS = {}
        resolve_stock_symbol = lambda s: s

    uncertainties: List[str] = [str(u) for u in data.get("uncertainties", []) if isinstance(u, (str, int, float))]

    raw_tech = data.get("technical_observations") or []
    if isinstance(raw_tech, str):
        raw_tech = [{"symbol": "", "indicator": "Observation", "value": None, "meaning": raw_tech}]
    elif not isinstance(raw_tech, list):
        raw_tech = []

    technical_observations = []
    for t in raw_tech:
        if isinstance(t, str):
            technical_observations.append({
                "symbol": "",
                "indicator": "ملاحظة فنية",
                "value": None,
                "meaning": t,
            })
        elif isinstance(t, dict):
            val = coerce_number_or_null(t.get("value"))
            technical_observations.append({
                "symbol": str(t.get("symbol") or "").upper(),
                "indicator": str(t.get("indicator") or "مؤشر"),
                "value": val,
                "meaning": str(t.get("meaning") or ""),
            })

    raw_symbols = data.get("symbols") or data.get("visible_stock_symbols") or []
    if not isinstance(raw_symbols, list):
        raw_symbols = []

    seen_symbols = set()
    unique_symbols = []
    img_type = str(data.get("image_type") or "unknown").lower()
    if img_type not in ("portfolio", "chart", "table", "market_depth", "unknown"):
        img_type = "unknown"

    for s in raw_symbols:
        entry = s if isinstance(s, dict) else {"symbol": str(s)}
        raw_sym = str(entry.get("symbol") or "").strip().upper()
        raw_sym = re.sub(r"[^A-Za-z0-9]", "", raw_sym)
        if len(raw_sym) < 2:
            continue

        resolved = resolve_stock_symbol(raw_sym) or raw_sym

        raw_change_pct = coerce_number_or_null(
            entry.get("visible_values", {}).get("change_pct") if isinstance(entry.get("visible_values"), dict) else entry.get("change_pct")
        )
        # EGX circuit breaker: daily moves beyond ±100% indicate column mix-up
        change_pct = raw_change_pct if (raw_change_pct is not None and abs(raw_change_pct) <= 100) else None
        columns_untrustworthy = raw_change_pct is not None and change_pct is None
        if columns_untrustworthy and resolved not in seen_symbols:
            uncertainties.append(f"تم تجاهل القيم المقروءة لـ {resolved} ({raw_change_pct}%) لأن ترتيب الأعمدة غير منطقي.")

        vis = entry.get("visible_values") if isinstance(entry.get("visible_values"), dict) else entry
        raw_qty = coerce_number_or_null(vis.get("quantity"))
        quantity = raw_qty if (not columns_untrustworthy and raw_qty is not None and raw_qty > 0) else None
        price = normalize_visible_price(vis.get("price"), img_type)
        average_price = normalize_visible_price(vis.get("average_price"), img_type)
        return_pct = coerce_number_or_null(vis.get("return_pct"))
        market_value = coerce_number_or_null(vis.get("market_value"))
        cost_basis = coerce_number_or_null(vis.get("cost_basis"))
        profit_loss = coerce_number_or_null(vis.get("profit_loss"))
        cash_dividends = coerce_number_or_null(vis.get("cash_dividends"))

        if img_type == "portfolio" and return_pct is None and change_pct is not None and profit_loss is not None:
            return_pct = change_pct
            change_pct = None

        asset_type = str(entry.get("asset_type") or "unknown").lower()
        if asset_type not in ("stock", "fund", "unknown"):
            asset_type = "unknown"

        existing = next((item for item in unique_symbols if item["symbol"] == resolved), None)
        if existing:
            # Merge fields from duplicate symbol rows
            v = existing["visible_values"]
            if v["quantity"] is None and quantity is not None:
                v["quantity"] = quantity
            if v["price"] is None and price is not None:
                v["price"] = price
            if v["change_pct"] is None and change_pct is not None:
                v["change_pct"] = change_pct
            if v["average_price"] is None and average_price is not None:
                v["average_price"] = average_price
            if v["return_pct"] is None and return_pct is not None:
                v["return_pct"] = return_pct
            if v["market_value"] is None and market_value is not None:
                v["market_value"] = market_value
            if v["cost_basis"] is None and cost_basis is not None:
                v["cost_basis"] = cost_basis
            if v["profit_loss"] is None and profit_loss is not None:
                v["profit_loss"] = profit_loss
            if v["cash_dividends"] is None and cash_dividends is not None:
                v["cash_dividends"] = cash_dividends
            if existing["asset_type"] == "unknown" and asset_type != "unknown":
                existing["asset_type"] = asset_type
            continue

        seen_symbols.add(resolved)
        unique_symbols.append({
            "symbol": resolved,
            "name": str(entry.get("name") or ""),
            "asset_type": asset_type,
            "source_image_index": entry.get("source_image_index"),
            "visible_values": {
                "price": price,
                "average_price": average_price,
                "change_pct": change_pct,
                "return_pct": return_pct,
                "quantity": quantity,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "profit_loss": profit_loss,
                "cash_dividends": cash_dividends,
            },
        })

    market_depth = data.get("market_depth") or {}
    if not isinstance(market_depth, dict):
        market_depth = {}

    confidence = coerce_number_or_null(data.get("confidence"))
    if confidence is None or not (0.0 <= confidence <= 1.0):
        confidence = 0.8 if unique_symbols else 0.5

    return {
        "image_type": img_type,
        "symbols": unique_symbols,
        "technical_observations": technical_observations,
        "market_depth": {
            "total_bid": coerce_number_or_null(market_depth.get("total_bid")),
            "total_ask": coerce_number_or_null(market_depth.get("total_ask")),
            "spread": coerce_number_or_null(market_depth.get("spread")),
        },
        "user_relevant_summary": str(data.get("user_relevant_summary") or data.get("summary") or ""),
        "uncertainties": list(dict.fromkeys(uncertainties)),
        "confidence": round(confidence, 2),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "message_id": str(data.get("message_id") or ""),
    }


def reconcile_vision_with_market(vision: Dict[str, Any], sb_client: Any) -> Dict[str, Any]:
    """
    Cross-checks extracted screenshot prices against latest Egyptian market closes.
    Flags massive discrepancies (>3x or <0.33x) in uncertainties to prevent hallucinations.
    """
    if not vision or not vision.get("symbols") or not sb_client:
        return vision

    symbols = [s["symbol"] for s in vision["symbols"] if s.get("symbol")]
    if not symbols:
        return vision

    try:
        res = (
            sb_client.from_("stock_technical_indicators")
            .select("symbol, close, date")
            .in_("symbol", symbols)
            .eq("exchange", "EGX")
            .order("date", desc=True)
            .limit(100)
            .execute()
        )
        data = res.data or []
        close_by_symbol = {}
        for row in data:
            sym = str(row.get("symbol") or "").upper()
            close_val = coerce_number_or_null(row.get("close"))
            if sym and close_val and close_val > 0 and sym not in close_by_symbol:
                close_by_symbol[sym] = close_val

        for entry in vision["symbols"]:
            sym = entry.get("symbol")
            close = close_by_symbol.get(sym)
            price = entry.get("visible_values", {}).get("price")
            if close and price and price > 0:
                ratio = price / close
                if ratio > 3.0 or ratio < 0.33:
                    msg = (
                        f"السعر الظاهر بالصورة لـ {sym} هو {price:.2f} ج.م، ويختلف كثيراً عن آخر إغلاق مسجل "
                        f"({close:.2f} ج.م)؛ احتفظت بقراءة الصورة كما هي ولا أتعامل معها كسعر سوق حالي."
                    )
                    vision.setdefault("uncertainties", []).append(msg)
    except Exception as e:
        logger.warning(f"[reconcile_vision_with_market] Reconciliation error: {e}")

    return vision


async def analyze_image(
    image_url: Union[str, List[str]],
    user_message: str,
    api_key: str,
    message_id: str = "",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Analyze financial screenshots using DeepSeek-Flash via official API.
    Handles multiple attachments, JSON repair, normalization, and validation.
    """
    if not api_key:
        return None, "deepseek_api_key_missing"

    urls = [u for u in (image_url if isinstance(image_url, list) else [image_url]) if u and isinstance(u, str) and u.strip()]
    if not urls:
        return None, "no_images_provided"

    # Multi-image handling: analyze each independently to prevent context truncation
    if len(urls) > 1:
        tasks = [
            analyze_image(
                url,
                f"{user_message}\n\nهذه الصورة رقم {idx + 1} من {len(urls)}. اقرأ هذه الصورة وحدها، ولا تفترض محتوى الصور الأخرى.",
                api_key,
                f"{message_id}:image:{idx + 1}",
            )
            for idx, url in enumerate(urls)
        ]
        results = await asyncio.gather(*tasks)
        readable = []
        for idx, (res_vision, res_err) in enumerate(results):
            if res_vision:
                for sym in res_vision.get("symbols", []):
                    sym["source_image_index"] = idx + 1
                readable.append(res_vision)

        if not readable:
            err = next((err for _, err in results if err), "vision_unavailable")
            return None, err

        first = readable[0]
        combined = {
            "image_type": first["image_type"] if all(r["image_type"] == first["image_type"] for r in readable) else "unknown",
            "symbols": [s for r in readable for s in r.get("symbols", [])],
            "technical_observations": [t for r in readable for t in r.get("technical_observations", [])],
            "market_depth": first.get("market_depth") or {"total_bid": None, "total_ask": None, "spread": None},
            "uncertainties": list(dict.fromkeys(
                [u for r in readable for u in r.get("uncertainties", [])] +
                [f"تعذر تحليل الصورة رقم {idx + 1}؛ واحتفظت بنتيجة كل صورة أخرى بشكل مستقل." for idx, (r, _) in enumerate(results) if not r]
            )),
            "confidence": round(sum(r.get("confidence", 0.5) for r in readable) / len(readable), 2),
            "user_relevant_summary": "\n".join([
                f"الصورة {idx + 1}: {r.get('user_relevant_summary', 'تعذر استخراج بيانات مؤكدة.')}" if r else f"الصورة {idx + 1}: تعذر استخراج بيانات مؤكدة."
                for idx, (r, _) in enumerate(results)
            ]),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "message_id": message_id,
        }
        return combined, None

    # Single image execution
    target_url = urls[0]
    user_content = [
        {"type": "text", "text": "Analyze this attached image and return a JSON result containing all clearly visible, task-relevant data."},
        {"type": "image_url", "image_url": {"url": target_url, "detail": "high"}},
    ]

    req_payload = {
        "model": "deepseek-flash",
        "messages": [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": VISION_MAX_OUTPUT_TOKENS,
        "temperature": 0.05,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(VISION_TIMEOUT_SECONDS, connect=10.0)) as client:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=req_payload,
            )

            if resp.status_code != 200:
                logger.warning(f"[VISION] deepseek-flash returned HTTP {resp.status_code}: {resp.text[:200]}")
                return None, f"vision_http_{resp.status_code}"

            data = resp.json()
            choice = data.get("choices", [{}])[0]
            finish_reason = choice.get("finish_reason")
            raw_content = choice.get("message", {}).get("content", "").strip()

            if finish_reason == "length":
                logger.warning(f"[VISION] output truncated (length)")
                return None, "vision_output_truncated"

            parsed = extract_json_from_response(raw_content)
            validated = validate_vision_output(parsed) if parsed else None

            if not validated:
                logger.warning(f"[VISION] deepseek-flash returned no usable JSON (len={len(raw_content)})")
                return None, "vision_invalid_json"

            validated["message_id"] = message_id
            return validated, None

    except httpx.TimeoutException:
        logger.warning("[VISION] deepseek-flash timed out")
        return None, "vision_timeout"
    except Exception as e:
        logger.warning(f"[VISION] deepseek-flash error: {e}")
        return None, "vision_request_failed"


def _fmt(val: Any, suffix: str = "") -> str:
    if val is None:
        return "غير ظاهر"
    if isinstance(val, (int, float)):
        return f"{val:,.2f}{suffix}"
    return str(val)


def safe_portfolio_image_reply(vision: Dict[str, Any], request: str = "") -> str:
    """Format extracted broker portfolio screenshot into standard readable Arabic table."""
    if not vision or vision.get("image_type") != "portfolio" or not vision.get("symbols"):
        return ""

    symbols = vision["symbols"]
    stocks_count = sum(1 for s in symbols if s.get("asset_type") == "stock")
    funds_count = sum(1 for s in symbols if s.get("asset_type") == "fund")
    unknown_count = sum(1 for s in symbols if s.get("asset_type") == "unknown")

    has_multi = any(s.get("source_image_index") for s in symbols)
    intro = f"قرأت {'الصور المرفقة' if has_multi else 'الصورة'}. هذه قراءة مباشرة للقيم التي أمكن استخراجها، من دون استنتاج أسعار أو أوزان غير ظاهرة:"
    summary_parts = [f"الرموز المقروءة: {len(symbols)}"]
    if stocks_count:
        summary_parts.append(f"أسهم: {stocks_count}")
    if funds_count:
        summary_parts.append(f"صناديق: {funds_count}")
    if unknown_count:
        summary_parts.append(f"تصنيف غير مؤكد: {unknown_count}")

    table_header = (
        "| المصدر | الرمز | النوع | الكمية | متوسط الشراء | السعر الظاهر | قيمة المركز | التكلفة | ربح/خسارة | توزيعات نقدية | العائد |\n"
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    )

    rows = []
    for s in symbols:
        src = f"صورة {s['source_image_index']}" if s.get("source_image_index") else "—"
        sym = s["symbol"]
        atype = "صندوق" if s.get("asset_type") == "fund" else "سهم" if s.get("asset_type") == "stock" else "غير محدد"
        v = s.get("visible_values") or {}
        ret_val = v.get("return_pct") if v.get("return_pct") is not None else v.get("change_pct")
        ret_str = f"{ret_val:+.2f}%" if ret_val is not None else "غير ظاهر"

        row = (
            f"| {src} | **{sym}** | {atype} | {_fmt(v.get('quantity'))} | {_fmt(v.get('average_price'), ' ج.م')} | "
            f"{_fmt(v.get('price'), ' ج.م')} | {_fmt(v.get('market_value'), ' ج.م')} | {_fmt(v.get('cost_basis'), ' ج.م')} | "
            f"{_fmt(v.get('profit_loss'), ' ج.م')} | {_fmt(v.get('cash_dividends'), ' ج.م')} | {ret_str} |"
        )
        rows.append(row)

    lines = [intro, "، ".join(summary_parts) + ".", table_header] + rows

    missing = [s["symbol"] for s in symbols if s.get("visible_values", {}).get("quantity") is None or s.get("visible_values", {}).get("average_price") is None]
    if missing:
        lines.append(f"\n⚠️ الكمية أو متوسط الشراء غير ظاهرين لبعض المراكز ({'، '.join(missing)})؛ لذلك لم أستنتج أوزانها أو أسجلها كمراكز مؤكدة.")

    if vision.get("uncertainties"):
        lines.append("\n**ملاحظات الرؤية:**\n• " + "\n• ".join(vision["uncertainties"]))

    return "\n".join(lines)


def safe_image_evidence_reply(vision: Dict[str, Any], request: str = "") -> str:
    """Format general chart, table, or market depth image analysis into Arabic response."""
    if not vision:
        return ""
    if vision.get("image_type") == "portfolio":
        return safe_portfolio_image_reply(vision, request)

    symbols = vision.get("symbols") or []
    has_multi = any(s.get("source_image_index") for s in symbols)
    lines = [f"قرأت الصورة{'/الصور المرفقة' if has_multi else ''}. هذه البيانات التي استخرجتها الرؤية، مع إبقاء كل قيمة مرتبطة بمصدرها:"]

    if symbols:
        lines.append("\n| المصدر | الرمز | السعر الظاهر | التغير % | الكمية |\n|---|---|---:|---:|---:|")
        for s in symbols:
            src = f"صورة {s['source_image_index']}" if s.get("source_image_index") else "—"
            v = s.get("visible_values") or {}
            chg = f"{v.get('change_pct'):+.2f}%" if v.get("change_pct") is not None else "غير ظاهر"
            lines.append(f"| {src} | **{s['symbol']}** | {_fmt(v.get('price'), ' ج.م')} | {chg} | {_fmt(v.get('quantity'))} |")

    obs = [o for o in vision.get("technical_observations", []) if o.get("meaning") or o.get("value") is not None]
    if obs:
        lines.append("\n**المؤشرات والملاحظات الفنية الظاهرة:**")
        for o in obs:
            sym_prefix = f"• **{o['symbol']}**: " if o.get("symbol") else "• "
            val_str = f" = {_fmt(o.get('value'))}" if o.get("value") is not None else ""
            meaning = f" ({o['meaning']})" if o.get("meaning") else ""
            lines.append(f"{sym_prefix}{o.get('indicator', 'ملاحظة')}{val_str}{meaning}")

    depth = vision.get("market_depth") or {}
    if depth.get("total_bid") is not None or depth.get("total_ask") is not None or depth.get("spread") is not None:
        lines.append(f"\n**عمق السوق الظاهر:** طلب {_fmt(depth.get('total_bid'))}، عرض {_fmt(depth.get('total_ask'))}، فرق السعر {_fmt(depth.get('spread'))}.")

    if vision.get("user_relevant_summary"):
        lines.append(f"\n**ملخص الصورة:** {vision['user_relevant_summary']}")

    if vision.get("uncertainties"):
        lines.append("\n**تنبيهات التدقيق:**\n• " + "\n• ".join(vision["uncertainties"]))

    if len(lines) == 1:
        lines.append("لم تُستخرج أرقام مؤكدة من الصورة؛ وضّح الجزء المطلوب أو أرسل نسخة أوضح.")

    return "\n".join(lines)


def format_vision_context_for_prompt(vision: Dict[str, Any]) -> str:
    """Renders the extracted vision evidence as a structured prompt instruction for DeepSeek V3 synthesis."""
    if not vision:
        return ""

    img_type = vision.get("image_type", "unknown")
    symbols = vision.get("symbols", [])
    summary = vision.get("user_relevant_summary", "")
    uncertainties = vision.get("uncertainties", [])

    lines = [
        "📸 **نتيجة قراءة الصورة المرفقة عبر محرك Vision المعتمد (Ground Truth Facts):**",
        f"- نوع الصورة المكتشف: {img_type}",
        f"- ملخص القراءة: {summary if summary else 'تم استخراج البيانات الظاهرة'}",
    ]

    if symbols:
        lines.append("- الأسهم والبيانات المالية المستخرجة من الصورة:")
        for s in symbols:
            v = s.get("visible_values") or {}
            details = []
            if v.get("quantity") is not None:
                details.append(f"الكمية: {v['quantity']:,.0f}")
            if v.get("average_price") is not None:
                details.append(f"متوسط الشراء: {v['average_price']:.2f} ج.م")
            if v.get("price") is not None:
                details.append(f"السعر الظاهر: {v['price']:.2f} ج.م")
            if v.get("cost_basis") is not None:
                details.append(f"التكلفة: {v['cost_basis']:,.2f} ج.م")
            if v.get("market_value") is not None:
                details.append(f"القيمة السوقية: {v['market_value']:,.2f} ج.م")
            if v.get("profit_loss") is not None:
                details.append(f"الربح/الخسارة: {v['profit_loss']:+,.2f} ج.م")
            if v.get("return_pct") is not None:
                details.append(f"العائد: {v['return_pct']:+.2f}%")
            desc = "، ".join(details) if details else "لم تظهر أرقام تفصيلية"
            lines.append(f"  * **{s['symbol']}** ({s.get('asset_type', 'stock')}): {desc}")

    obs = vision.get("technical_observations", [])
    if obs:
        lines.append("- الملاحظات الفنية والمؤشرات المقروءة:")
        for o in obs:
            val_txt = f"={o['value']}" if o.get("value") is not None else ""
            lines.append(f"  * {o.get('symbol', '')} {o.get('indicator', '')}{val_txt}: {o.get('meaning', '')}")

    if uncertainties:
        lines.append("- حدود الثقة وملاحظات التحقق:")
        for u in uncertainties:
            lines.append(f"  * {u}")

    if img_type == "unknown" and not symbols and not obs:
        lines.append(
            "\nتوجيه للإجابة:\n"
            "1. الصورة المرفقة هي صورة عادية أو غير مالية ولا تحتوي على محفظة أسهم أو شارت فني أو جدول أسعار أسهم.\n"
            "2. لا تحللها كمحفظة أسهم ولا تخترع أي رموز أو أرقام مالية.\n"
            "3. رد على المستخدم بشكل طبيعي ومختصر بناءً على ملخص الصورة أو رسالته، ووضّح له أنه يمكنه إرسال لقطة شاشة لمحفظته أو شارت أي سهم لتحليله."
        )
    else:
        lines.append(
            "\nتوجيه صارم للإجابة:\n"
            "1. اعتمد الأرقام والأسهم المستخرجة أعلاه كحقائق مؤكدة من الصورة.\n"
            "2. قارن أسعار الشراء المستخرجة من الصورة بأسعار السوق اللحظية الحالية في البورصة المصرية ومستويات الدعم والمقاومة المستدعاة من الأدوات.\n"
            "3. قدم تحليلاً مالياً وفنياً دقيقاً ووافياً للمحفظة أو الشارت باللغة العربية بأسلوب استثماري احترافي."
        )

    return "\n".join(lines)
