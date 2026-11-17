import "server-only";

export function resolveHfBackendUrl(): string {
  let backendUrl =
    process.env.PYTHON_BACKEND_URL ||
    process.env.TRADING_SIGNALS_API_URL ||
    (process.env.NODE_ENV === "production"
      ? "https://weeasdwee-ai-bot.hf.space"
      : "http://127.0.0.1:8000");
  if (/localhost:3000|:3000\b/.test(backendUrl)) {
    backendUrl = "http://127.0.0.1:8000";
  }
  if (process.env.NODE_ENV === "production" && /localhost|127\.0\.0\.1/.test(backendUrl)) {
    backendUrl = "https://weeasdwee-ai-bot.hf.space";
  }
  return backendUrl.replace(/\/$/, "");
}

/**
 * Fetch a precomputed public payload from the Hugging Face FastAPI backend so
 * Vercel ISR pages never burn Active CPU aggregating Supabase tables directly.
 * Returns null inside Jest tests, when OFFLOAD_TO_HF=false, or on network error
 * so callers can cleanly fall back to their existing Supabase paths.
 */
export async function fetchHfPublicJson<T>(
  pathAndQuery: string,
  revalidateSeconds = 86400,
  timeoutMs = 5000,
  tags?: string[]
): Promise<T | null> {
  if (process.env.JEST_WORKER_ID || process.env.OFFLOAD_TO_HF === "false") {
    return null;
  }
  const url = `${resolveHfBackendUrl()}${pathAndQuery.startsWith("/") ? pathAndQuery : `/${pathAndQuery}`}`;
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      next: tags?.length
        ? { revalidate: revalidateSeconds, tags }
        : { revalidate: revalidateSeconds },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
