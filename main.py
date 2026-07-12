from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import re
import requests
import yfinance as yf
from dotenv import load_dotenv
from openai import OpenAI
import logging
from search_client import search_ticker_symbol, search_stock_news, search_missing_metric

# --- SETUP ---
load_dotenv("key.env")
GROK_API_KEY = os.getenv("GROK_API_KEY")
INDIAN_API_KEY = os.getenv("INDIAN_API_KEY")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.groq.com/openai/v1") if GROK_API_KEY else None
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- HELPERS ---
def get_live_price(symbol: str) -> dict:
    # 1. IndianAPI (Primary)
    if INDIAN_API_KEY:
        try:
            for sym in [symbol, symbol.replace(".NS",""), symbol + ".NS"]:
                url = "https://api.indianapi.in/v1/stock"
                resp = requests.get(url, headers={"Authorization": f"Bearer {INDIAN_API_KEY}"}, params={"symbol": sym}, timeout=2)
                if resp.status_code == 200:
                    d = resp.json().get('data', resp.json())
                    price = d.get('currentPrice') or d.get('lastPrice')
                    if price:
                        return {"price": price, "change": d.get('pChange', 0), "source": "IndianAPI"}
        except: pass

    # 2. Yahoo Finance (Backup)
    try:
        stock = yf.Ticker(symbol)
        price = stock.fast_info.last_price
        if price:
            prev = stock.fast_info.previous_close
            change = ((price - prev) / prev) * 100 if prev else 0
            return {"price": round(price, 2), "change": round(change, 2), "source": "YahooFinance"}
    except: pass
    return {}

def get_fundamentals(symbol: str, name: str) -> dict:
    data = {"market_cap": None, "pe_ratio": None, "roe": None}
    try:
        info = yf.Ticker(symbol).info
        data["market_cap"] = f"{round(info.get('marketCap', 0)/10000000, 2)} Cr" if info.get('marketCap') else None
        data["pe_ratio"] = round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else None
        data["roe"] = f"{round(info.get('returnOnEquity', 0)*100, 2)}%" if info.get('returnOnEquity') else None
    except: pass

    # Fill missing gaps with Search
    for k, v in data.items():
        if v is None:
            readable = k.replace("_", " ").title()
            data[k] = search_missing_metric(name, readable)
    return data

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
    if not client: return ChatResponse(answer="Error: GROK_API_KEY missing.")

    q = request.message.strip()
    clean_name = re.sub(r'(price|stock|share|news|analysis|of|for|target)\s+', '', q, flags=re.IGNORECASE).strip()

    # 1. RESOLVE TICKER
    ticker = search_ticker_symbol(clean_name)
    if not ticker: ticker = f"{clean_name}.NS" # Fallback

    # 2. FETCH DATA
    price_data = get_live_price(ticker)
    
    # Retry if price failed (maybe ticker had .NS double or missing)
    if not price_data.get('price'):
        ticker = ticker.replace(".NS", "")
        price_data = get_live_price(ticker)

    fund_data = get_fundamentals(ticker, clean_name)
    news_data = search_stock_news(clean_name, ticker)

    # 3. PROFESSIONAL DASHBOARD PROMPT
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

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": system_prompt}],
            temperature=0.1
        )
        return ChatResponse(answer=completion.choices[0].message.content)
    except Exception as e:
        return ChatResponse(answer=f"Error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)