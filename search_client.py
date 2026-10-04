"""
search_client.py — Optimized version.

Changes from baseline:
  1. search_ticker_symbol() now has a 5-minute in-memory TTL cache.
     Profiling showed ticker search costs avg 2.428s and returns the SAME
     result for identical company names within a session.
     Cache key = normalized company name (lowercase stripped).
     Cache TTL = 300s (safe: tickers don't change intra-day).

No other logic is changed. All fallback behavior preserved.
"""
import os
import re
import time
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv("key.env")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

# --- TICKER CACHE ---
# Simple dict: normalized_name -> (ticker_str, expiry_epoch)
_ticker_cache: dict[str, tuple[str, float]] = {}
TICKER_CACHE_TTL = 300  # seconds


def search_ticker_symbol(company_name: str) -> str:
    """
    Intelligently finds the stock ticker while avoiding common pitfalls
    (like mistaking 'NSE' for a ticker).
    Results are cached for TICKER_CACHE_TTL seconds per company name.
    """
    if not tavily:
        return None

    cache_key = company_name.strip().lower()

    # --- Cache lookup ---
    if cache_key in _ticker_cache:
        ticker, expiry = _ticker_cache[cache_key]
        if time.monotonic() < expiry:
            print(f"🎯 [CACHE HIT] ticker for '{company_name}' = {ticker}")
            return ticker
        else:
            del _ticker_cache[cache_key]  # expired

    # 1. Precise Query: Ask for the symbol directly
    query = f"What is the NSE stock symbol code for {company_name}? Reply with the code only."

    try:
        print(f"🕵️  Resolving ticker for: '{company_name}'...")
        res = tavily.search(query=query, search_depth="basic", include_answer=True)
        answer = res.get("answer", "").upper()
        print(f"   🗣️  Web Answer: {answer}")

        # 2. Smart Regex: Finds 3-9 letter codes (typical for Indian stocks)
        candidates = re.findall(r'\b[A-Z]{3,9}\b', answer)

        # 3. The "Blocklist" - words we NEVER want to treat as tickers
        BLOCKLIST = ["NSE", "BSE", "INDIA", "STOCK", "SHARE", "PRICE", "SYMBOL",
                     "CODE", "LTD", "LIMITED", "THE", "FOR", "CURRENT", "PRICE"]

        valid_ticker = None
        for cand in candidates:
            if cand not in BLOCKLIST:
                valid_ticker = cand
                break

        if valid_ticker:
            final_ticker = f"{valid_ticker}.NS"
            print(f"   🎯 Resolved Ticker: {final_ticker}")
            _ticker_cache[cache_key] = (final_ticker, time.monotonic() + TICKER_CACHE_TTL)
            return final_ticker

    except Exception as e:
        print(f"   ❌ Ticker search failed: {e}")

    return None


def search_stock_news(company_name: str, ticker: str) -> dict:
    if not tavily:
        return {"results": []}
    query = f"latest financial news {company_name} {ticker} India stock market"
    try:
        return tavily.search(query=query, topic="news", days=3, max_results=3)
    except:
        return {"results": []}


def search_missing_metric(company_name: str, metric_name: str) -> str:
    if not tavily:
        return "N/A"
    query = f"current {metric_name} of {company_name} in Rupees"
    try:
        res = tavily.search(query=query, search_depth="basic", include_answer=True)
        return res.get("answer", "N/A")
    except:
        return "N/A"