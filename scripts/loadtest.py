# scripts/loadtest.py
import asyncio
import httpx
import time
import json
import sys

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/api/ai_chat/stream"
HEADERS = {
    "Authorization": "Bearer TEST_TOKEN",
    "x-benchmark-test": "true",
    "Content-Type": "application/json",
}
QUESTIONS = [
    "سعر فوري كام دلوقتي؟",
    "حلل سهم COMI",
    "إيه أفضل أسهم السوق النهارده؟",
    "قارن بين ETEL و COMI",
]

# Run custom levels from CLI if provided, e.g. python scripts/loadtest.py http://... 5,10,20
if len(sys.argv) > 2:
    LEVELS = [int(x.strip()) for x in sys.argv[2].split(",") if x.strip()]
else:
    LEVELS = [5, 10, 20, 40]


async def one_user(client, i):
    t0 = time.perf_counter()
    ttfb, ok, err = None, False, None
    try:
        body = {"message": QUESTIONS[i % len(QUESTIONS)], "history": []}
        async with client.stream("POST", URL, json=body, headers=HEADERS) as r:
            if r.status_code != 200:
                err_text = await r.aread()
                return dict(
                    ok=False,
                    err=f"HTTP {r.status_code}: {err_text.decode('utf-8', errors='ignore')[:100]}",
                    ttfb=None,
                    total=time.perf_counter() - t0,
                )
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    ev = json.loads(payload)
                except Exception:
                    continue
                if ev.get("type") == "token" and ttfb is None:
                    ttfb = time.perf_counter() - t0
                elif ev.get("type") == "error":
                    err = ev.get("detail", "error")
                elif ev.get("type") == "done":
                    ok = True
    except Exception as e:
        err = repr(e)
    return dict(ok=ok and not err, err=err, ttfb=ttfb, total=time.perf_counter() - t0)


def pct(vals, p):
    vals = sorted(v for v in vals if v is not None)
    return round(vals[min(len(vals) - 1, int(len(vals) * p))], 2) if vals else None


async def main():
    print(f"Target URL: {URL}")
    print(f"Levels: {LEVELS}")
    for n in LEVELS:
        limits = httpx.Limits(max_connections=n + 10)
        async with httpx.AsyncClient(timeout=120, limits=limits) as c:
            res = await asyncio.gather(*[one_user(c, i) for i in range(n)])
        fails = [r["err"] for r in res if not r["ok"]]
        succ = [r for r in res if r["ok"]]
        print(f"\n=== {n} متزامن ===")
        print("أول كلمة  p50/p95:", pct([r['ttfb'] for r in succ], .5), "/", pct([r['ttfb'] for r in succ], .95), "ث")
        print("الزمن الكلي p50/p95:", pct([r['total'] for r in succ], .5), "/", pct([r['total'] for r in succ], .95), "ث")
        print(f"نجاح: {len(succ)}/{n} | أخطاء: {len(fails)}/{n}", set(fails) if fails else "")
        if n != LEVELS[-1]:
            print("انتظار 5 ثوانٍ بين المراحل...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
