#!/usr/bin/env python3
"""
IndexNow Instant Search Engine Submission (Bing, Yandex, Copilot, ChatGPT Search)
Submits all high-priority EGX BOTS URLs and top-searched stock pages via IndexNow protocol.
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HOST = "egxbots.com"
KEY = "61bdf3b09990ce1cc89368a7ba379cba"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"

URLS = [
    f"https://{HOST}/",
    f"https://{HOST}/scanner/ai",
    f"https://{HOST}/scanner/technical",
    f"https://{HOST}/scanner/market",
    f"https://{HOST}/scanner/backtests",
    f"https://{HOST}/stocks",
    f"https://{HOST}/fair-value",
    f"https://{HOST}/sharia",
    f"https://{HOST}/blogs",
    f"https://{HOST}/blogs/best-egx-stock-analysis-software",
    f"https://{HOST}/blogs/ai-egyptian-stock-market-analysis",
    f"https://{HOST}/blogs/egx-telegram-stock-recommendations",
    f"https://{HOST}/blogs/how-to-invest-in-egyptian-stock-market-beginners",
    f"https://{HOST}/blogs/egx33-sharia-compliant-stocks-egypt-guide",
    f"https://{HOST}/blogs/undervalued-egx-stocks-fair-value-calculation",
    f"https://{HOST}/stocks/alum",
    f"https://{HOST}/stocks/copr",
    f"https://{HOST}/stocks/kora",
    f"https://{HOST}/stocks/ames",
    f"https://{HOST}/stocks/aalr",
    f"https://{HOST}/stocks/abuk",
    f"https://{HOST}/stocks/mbeg",
    f"https://{HOST}/stocks/gbco",
    f"https://{HOST}/stocks/auto",
    f"https://{HOST}/stocks/comi",
    f"https://{HOST}/stocks/tmgh",
    f"https://{HOST}/stocks/fwry",
    f"https://{HOST}/stocks/esrs",
    f"https://{HOST}/stocks/etel",
    f"https://{HOST}/stocks/swdy",
    f"https://{HOST}/stocks/hrho",
    f"https://{HOST}/stocks/btfh",
    f"https://{HOST}/stocks/mfpc",
    f"https://{HOST}/stocks/amoc",
]

def main():
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": URLS,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"✅ IndexNow submitted {len(URLS)} URLs | HTTP Status: {resp.status}")
    except Exception as e:
        print(f"IndexNow response: {e}")

if __name__ == "__main__":
    main()
