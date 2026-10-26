import { getDeepSeekApiKey, getNvidiaApiKeys } from "@/lib/ai/server-secrets";

export interface ExtractedStock {
    symbol: string;
    name?: string;
    quantity?: number | null;
    price?: number | null;
}

export interface ExtractionInput {
    text: string;
    userQuery?: string;
    suggestedButtons?: string[];
}

const LLM_SYSTEM_PROMPT = `You are an expert Egyptian Stock Exchange (EGX) portfolio assistant.
Your task is to analyze the user's query, the AI assistant's response/analysis, and any suggested follow-up buttons to extract ALL Egyptian stock symbols (EGX tickers) being analyzed, discussed, recommended, or tracked.

Extraction Rules:
1. Identify the subject stock(s) of the analysis (e.g. from user question, buttons, or analysis body).
2. Even if the analysis rating is negative (🔴 سلبي) or neutral or says "لا توجد توصية شراء" / "للمراقبة", ALWAYS extract the stock(s) because the user clicked "Save to Portfolio" to track this stock in their portfolio!
3. For each stock found:
   - symbol: The official EGX English ticker symbol in UPPERCASE (e.g., MOED, COMI, TMGH, ABUK, ATQA, SKPC, FWRY, SWDY, HRHO, ESRS, CCAP, AMOC, EKHO, HELI, PHDC, ISPH, JUFO, BTFH, ETEL, etc.). Always convert Arabic names or lowercase input to uppercase EGX tickers (e.g., المنصورة للدواجن -> MOED, moed -> MOED, التجاري الدولي -> COMI, طلعت مصطفى -> TMGH).
   - name: The Arabic company name if recognized (e.g., "المنصورة للدواجن").
   - quantity: Number of shares if mentioned in user text or response, default to 100.
   - price: The current market price or entry price mentioned in the text (e.g. "السعر: 0.404" or "السعر الحالي | 0.404" -> 0.404). If no price is mentioned, set to null.
4. DO NOT extract stocks that are explicitly mentioned only as already in the user's existing portfolio (e.g. under "غير مسجل ضمن مراكز محفظتك المحفوظة (ACGC, ACAP...)" -> do NOT add ACGC or ACAP). Only extract the target stock being analyzed or recommended.
5. Extract EVERY single stock analyzed (whether 1, 2, 4, 10 or more).
6. Return ONLY a valid JSON object matching this schema:
{
  "stocks": [
    { "symbol": "MOED", "name": "المنصورة للدواجن", "quantity": 100, "price": 0.404 }
  ]
}
- If NO EGX stocks are present in the text or request, return: {"stocks": []}
- Do NOT wrap in markdown backticks. Return raw valid JSON.`;

export function extractFallbackStocks(text: string, userQuery?: string, suggestedButtons?: string[]): ExtractedStock[] {
    const stocks: ExtractedStock[] = [];
    const foundSymbols = new Set<string>();
    const ignored = new Set(["RSI", "MACD", "EMA", "SMA", "EGX", "USD", "EGP", "COPY", "BUY", "SELL", "HOLD", "VIP", "EXCEL"]);

    // Try to find price from text (e.g., "السعر: 0.404" or "السعر الحالي | 0.404")
    let detectedPrice: number | null = null;
    const priceMatch = text.match(/(?:السعر الحالي|السعر)\s*[:|]?\s*([\d.]+)/i);
    if (priceMatch) {
        const val = parseFloat(priceMatch[1]);
        if (!isNaN(val) && val > 0) detectedPrice = val;
    }

    // 1. Check userQuery (e.g. "moed" or "COMI")
    if (userQuery) {
        const cleanQ = userQuery.trim().toUpperCase();
        if (/^[A-Z]{2,6}$/.test(cleanQ) && !ignored.has(cleanQ)) {
            foundSymbols.add(cleanQ);
        }
    }

    // 2. Check suggestedButtons (e.g. "اختبر الاتجاه وMACD على MOED")
    if (Array.isArray(suggestedButtons)) {
        for (const btn of suggestedButtons) {
            const match = btn.match(/(?:على|في|بـ|سهم)\s+([A-Z]{2,6})\b/i) || btn.match(/\b([A-Z]{2,6})\b/);
            if (match) {
                const sym = match[1].toUpperCase();
                if (!ignored.has(sym)) {
                    foundSymbols.add(sym);
                }
            }
        }
    }

    // 3. Check text for standalone tickers if still empty
    if (foundSymbols.size === 0) {
        const words = text.match(/\b[A-Z]{2,6}\b/g) || [];
        for (const w of words) {
            const sym = w.toUpperCase();
            if (!ignored.has(sym) && !text.includes(`مراكز محفظتك المحفوظة (${sym}`) && !text.includes(`المحفوظة (${sym}`)) {
                foundSymbols.add(sym);
                break;
            }
        }
    }

    for (const sym of foundSymbols) {
        stocks.push({
            symbol: sym,
            quantity: 100,
            price: detectedPrice,
        });
    }

    return stocks;
}

export async function callExtractionLLM(input: string | ExtractionInput): Promise<ExtractedStock[]> {
    const text = typeof input === "string" ? input : input.text || "";
    const userQuery = typeof input === "string" ? "" : input.userQuery || "";
    const suggestedButtons = typeof input === "string" ? [] : input.suggestedButtons || [];

    const deepseekKey = getDeepSeekApiKey();
    const nvidiaKeys = getNvidiaApiKeys();

    const compositeParts: string[] = [];
    if (userQuery) {
        compositeParts.push(`سؤال المستخدم أو طلبه: ${userQuery}`);
    }
    if (suggestedButtons.length > 0) {
        compositeParts.push(`أزرار ومقترحات المتابعة: ${suggestedButtons.join(" | ")}`);
    }
    if (text) {
        compositeParts.push(`تحليل ورد المساعد:\n${text.slice(0, 4000)}`);
    }
    const userPrompt = `استخرج أسهم البورصة المصرية المطلوب حفظها من هذا السياق بصيغة JSON كما طُلب:\n\n${compositeParts.join("\n\n")}`;

    // 1. Try DeepSeek first (fast, accurate for Arabic & EGX tickers)
    if (deepseekKey) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 12000);

            const res = await fetch("https://api.deepseek.com/chat/completions", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${deepseekKey}`,
                },
                body: JSON.stringify({
                    model: "deepseek-chat",
                    messages: [
                        { role: "system", content: LLM_SYSTEM_PROMPT },
                        { role: "user", content: userPrompt },
                    ],
                    response_format: { type: "json_object" },
                    temperature: 0.1,
                    max_tokens: 1000,
                }),
                signal: controller.signal,
            });

            clearTimeout(timeoutId);

            if (res.ok) {
                const json = await res.json();
                const content = json.choices?.[0]?.message?.content?.trim() || "";
                const parsed = JSON.parse(content);
                if (Array.isArray(parsed?.stocks) && parsed.stocks.length > 0) {
                    return parsed.stocks;
                }
            }
        } catch (err) {
            console.warn("[portfolio-extract] DeepSeek extraction failed, trying fallback:", err);
        }
    }

    // 2. Fallback to Nvidia
    for (const nKey of nvidiaKeys) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 12000);

            const res = await fetch("https://integrate.api.nvidia.com/v1/chat/completions", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${nKey}`,
                },
                body: JSON.stringify({
                    model: "meta/llama-3.1-70b-instruct",
                    messages: [
                        { role: "system", content: LLM_SYSTEM_PROMPT },
                        { role: "user", content: userPrompt },
                    ],
                    temperature: 0.1,
                    max_tokens: 1000,
                }),
                signal: controller.signal,
            });

            clearTimeout(timeoutId);

            if (res.ok) {
                const json = await res.json();
                const rawContent = json.choices?.[0]?.message?.content?.trim() || "";
                let parsed: any = null;
                try {
                    parsed = JSON.parse(rawContent);
                } catch {
                    const match = rawContent.match(/\{[\s\S]*\}/);
                    if (match) parsed = JSON.parse(match[0]);
                }
                if (Array.isArray(parsed?.stocks) && parsed.stocks.length > 0) {
                    return parsed.stocks;
                }
            }
        } catch (err) {
            console.warn("[portfolio-extract] Nvidia fallback failed:", err);
        }
    }

    // 3. Fallback to deterministic regex & context extraction if LLMs returned 0 items
    const fallback = extractFallbackStocks(text, userQuery, suggestedButtons);
    if (fallback.length > 0) {
        return fallback;
    }

    return [];
}
