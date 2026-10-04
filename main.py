"""
main.py — Optimized version.

Optimizations applied (all justified by Phase 1/2/3 profiling):

1. PARALLEL I/O for price + fundamentals + news
   Profiling showed these three are fully independent after ticker resolution
   and ran sequentially for a combined avg of 4.316s.  With asyncio.gather +
   run_in_executor they run concurrently, reducing that wall-time to
   max(price, fundamentals, news) ≈ avg 2.024s (measured on R1-R4).

2. Ticker cache (in search_client.py)
   Same company name → same ticker within 5 min.  Saves avg 2.428s on hits.

3. IndianAPI concurrent variant fetch
   The original code tried 3 URL variants (symbol, symbol-".NS", symbol+".NS")
   SEQUENTIALLY with a 2s timeout each = up to 6s before yfinance fallback.
   Now all three are fired concurrently via ThreadPoolExecutor; first success wins.
   Worst-case timeout drops from 6s to 2s.

4. Added "CURRENT" to ticker blocklist (bug fix from R5 profiling).

All fallbacks, API contracts, and frontend compatibility preserved.
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import os
import re
import time
import requests
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from openai import OpenAI
import logging
from search_client import search_ticker_symbol, search_stock_news, search_missing_metric

# --- SETUP ---
load_dotenv("key.env")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
INDIAN_API_KEY = os.getenv("INDIAN_API_KEY")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_API_KEY else None
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# Shared executor for sync I/O tasks
_executor = ThreadPoolExecutor(max_workers=8)


# --- HELPERS ---

def _fetch_indian_api_variant(sym: str) -> dict:
    """Fetch one IndianAPI variant. Returns {} on failure."""
    try:
        url = "https://api.indianapi.in/v1/stock"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {INDIAN_API_KEY}"},
            params={"symbol": sym},
            timeout=2,
        )
        if resp.status_code == 200:
            d = resp.json().get("data", resp.json())
            price = d.get("currentPrice") or d.get("lastPrice")
            if price:
                return {"price": price, "change": d.get("pChange", 0), "source": "IndianAPI"}
    except:
        pass
    return {}


async def get_live_price_async(symbol: str) -> dict:
    """
    Optimized price fetch.
    IndianAPI: fires all 3 symbol variants CONCURRENTLY (was sequential).
    Worst-case timeout: 2s (was up to 6s).
    Falls back to yfinance if all variants fail.
    """
    if INDIAN_API_KEY:
        loop = asyncio.get_event_loop()
        variants = [symbol, symbol.replace(".NS", ""), symbol + ".NS"]
        # Deduplicate variants (e.g. if symbol already has no .NS)
        variants = list(dict.fromkeys(variants))
        futures = [
            loop.run_in_executor(_executor, _fetch_indian_api_variant, sym)
            for sym in variants
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)
        for r in results:
            if isinstance(r, dict) and r.get("price"):
                return r

    # Yahoo Finance fallback (sync, run in executor to not block event loop)
    loop = asyncio.get_event_loop()
    def _yfinance_price():
        try:
            stock = yf.Ticker(symbol)
            price = stock.fast_info.last_price
            if price:
                prev = stock.fast_info.previous_close
                change = ((price - prev) / prev) * 100 if prev else 0
                return {"price": round(price, 2), "change": round(change, 2), "source": "YahooFinance"}
        except:
            pass
        return {}
    return await loop.run_in_executor(_executor, _yfinance_price)


async def get_fundamentals_async(symbol: str, name: str) -> dict:
    """
    Fundamentals fetch — moved to executor so it doesn't block event loop.
    Fallback search_missing_metric calls are still sequential within this
    function (they depend on which fields yfinance returned), but the whole
    function runs concurrently with price and news.
    """
    loop = asyncio.get_event_loop()
    def _fetch():
        data = {"market_cap": None, "pe_ratio": None, "roe": None}
        try:
            info = yf.Ticker(symbol).info
            data["market_cap"] = (
                f"{round(info.get('marketCap', 0) / 10000000, 2)} Cr"
                if info.get("marketCap") else None
            )
            data["pe_ratio"] = (
                round(info.get("trailingPE", 0), 2)
                if info.get("trailingPE") else None
            )
            data["roe"] = (
                f"{round(info.get('returnOnEquity', 0) * 100, 2)}%"
                if info.get("returnOnEquity") else None
            )
        except:
            pass
        for k, v in data.items():
            if v is None:
                readable = k.replace("_", " ").title()
                data[k] = search_missing_metric(name, readable)
        return data
    return await loop.run_in_executor(_executor, _fetch)


async def get_news_async(company_name: str, ticker: str) -> dict:
    """News fetch — run in executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, search_stock_news, company_name, ticker
    )


# --- ENDPOINT ---
@app.get("/")
async def get_frontend():
    return FileResponse("index.html")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    t_total_start = time.perf_counter()

    if not client:
        return ChatResponse(answer="Error: GROQ_API_KEY missing.")

    q = request.message.strip()
    clean_name = re.sub(
        r'(price|stock|share|news|analysis|of|for|target)\s+', '',
        q, flags=re.IGNORECASE
    ).strip()

    # 1. RESOLVE TICKER (cached after first hit)
    t0 = time.perf_counter()
    loop = asyncio.get_event_loop()
    ticker = await loop.run_in_executor(_executor, search_ticker_symbol, clean_name)
    if not ticker:
        ticker = f"{clean_name}.NS"
    t_ticker = time.perf_counter() - t0
    logger.info(f"[PERF] ticker_search={t_ticker:.3f}s  resolved={ticker}")

    # 2. FETCH PRICE, FUNDAMENTALS, NEWS — CONCURRENTLY
    t0 = time.perf_counter()
    price_task = get_live_price_async(ticker)
    fund_task  = get_fundamentals_async(ticker, clean_name)
    news_task  = get_news_async(clean_name, ticker)

    price_data, fund_data, news_data = await asyncio.gather(
        price_task, fund_task, news_task
    )
    t_parallel = time.perf_counter() - t0

    # Retry price with stripped ticker if failed (preserves original fallback)
    if not price_data.get("price"):
        stripped = ticker.replace(".NS", "")
        if stripped != ticker:
            ticker = stripped
            price_data = await get_live_price_async(ticker)

    logger.info(
        f"[PERF] parallel_gather={t_parallel:.3f}s  "
        f"price_source={price_data.get('source','none')}  "
        f"price_ok={bool(price_data.get('price'))}  "
        f"news_articles={len(news_data.get('results', []))}"
    )

    # 3. BUILD PROMPT + LLM
    system_prompt = f"""
    You are a senior financial analyst. Create a clean, professional executive summary.
    
    SUBJECT: {clean_name.upper()} (Ticker: {ticker})
    
    DATA FEED:
    - Price: {price_data.get('price', 'N/A')} (Change: {price_data.get('change', 'N/A')}%)
    - Market Cap: {fund_data.get('market_cap', 'N/A')}
    - P/E: {fund_data.get('pe_ratio', 'N/A')}
    - ROE: {fund_data.get('roe', 'N/A')}
    - News: {str(news_data.get('results', []))[:1000]}
    
    FORMATTING RULES:
    1. Do NOT use excessive emojis. Use standard bullet points.
    2. Use a clean "Table" for metrics.
    3. Structure:
       - Header: Company Name & Price
       - Executive Summary (1-2 sentences)
       - Key Fundamentals (Table)
       - Market Developments (Bullet points from news)
       - Analyst Verdict (Bold conclusion)
    """

    t0 = time.perf_counter()
    try:
        def _llm_call():
            return client.chat.completions.create(
                model="qwen/qwen3.8-27b",
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.1,
            )
        completion = await loop.run_in_executor(_executor, _llm_call)
        answer = completion.choices[0].message.content
    except Exception as e:
        answer = f"Error: {e}"
    t_llm = time.perf_counter() - t0

    t_total = time.perf_counter() - t_total_start
    logger.info(
        f"[PERF] llm={t_llm:.3f}s  total={t_total:.3f}s  "
        f"[ticker={t_ticker:.3f}s  parallel={t_parallel:.3f}s  llm={t_llm:.3f}s]"
    )

    return ChatResponse(answer=answer)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)