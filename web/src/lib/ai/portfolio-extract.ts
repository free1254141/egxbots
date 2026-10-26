import { getDeepSeekApiKey, getNvidiaApiKeys } from "@/lib/ai/server-secrets";

export interface ExtractedStock {
    symbol: string;
    name?: string;
    quantity?: number | null;
    price?: number | null;
}

const LLM_SYSTEM_PROMPT = `You are an expert Egyptian Stock Exchange (EGX) portfolio assistant.
Your task is to analyze the provided chat message/analysis and extract ALL Egyptian stock holdings mentioned, discussed, or recommended for a portfolio.

For each stock found, extract:
- symbol: The official EGX English ticker symbol in UPPERCASE (e.g., COMI, TMGH, ABUK, ATQA, SKPC, FWRY, SWDY, HRHO, ESRS, CCAP, AMOC, EKHO, HELI, PHDC, ISPH, JUFO, BTFH, ETEL, etc.). Always map Arabic stock names to their exact official EGX ticker symbol (e.g. التجاري الدولي -> COMI, طلعت مصطفى -> TMGH, عتاقة -> ATQA, سيدي كرير -> SKPC, أبو قير -> ABUK, حديد عز -> ESRS, بلتون -> BTFH).
- name: The Arabic company name if recognized.
- quantity: The number of shares mentioned (e.g., 200, 500, 1000). If no quantity is mentioned, set to 100.
- price: The buy/entry/cost price per share mentioned in the text (as a number, e.g. 85.5). If no entry price was mentioned, set to null.

CRITICAL INSTRUCTIONS:
- You must return ONLY a valid JSON object matching this schema:
{
  "stocks": [
    { "symbol": "COMI", "name": "البنك التجاري الدولي", "quantity": 100, "price": 85.5 }
  ]
}
- If NO EGX stocks are present in the text, return: {"stocks": []}
- Extract every single stock mentioned (whether 1, 2, 4, 10, or more).
- Do NOT wrap in markdown backticks. Return raw valid JSON.`;

export async function callExtractionLLM(text: string): Promise<ExtractedStock[]> {
    const deepseekKey = getDeepSeekApiKey();
    const nvidiaKeys = getNvidiaApiKeys();

    const userPrompt = `حلل هذا النص واستخرج كل أسهم البورصة المصرية منه بصيغة JSON كما طُلب:\n\n${text.slice(0, 4000)}`;

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
                if (Array.isArray(parsed?.stocks)) {
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
                if (Array.isArray(parsed?.stocks)) {
                    return parsed.stocks;
                }
            }
        } catch (err) {
            console.warn("[portfolio-extract] Nvidia fallback failed:", err);
        }
    }

    return [];
}
