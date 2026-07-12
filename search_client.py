import os
import re
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv("key.env")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None

def search_ticker_symbol(company_name: str) -> str:
    """
    Intelligently finds the stock ticker while avoiding common pitfalls 
    (like mistaking 'NSE' for a ticker).
    """
    if not tavily: return None

    # 1. Precise Query: Ask for the symbol directly
    query = f"What is the NSE stock symbol code for {company_name}? Reply with the code only."

    try:
        print(f"🕵️  Resolving ticker for: '{company_name}'...")
        res = tavily.search(query=query, search_depth="basic", include_answer=True)
        answer = res.get("answer", "").upper() # Convert to Uppercase
        print(f"   🗣️  Web Answer: {answer}")

        # 2. Smart Regex: Finds 3-6 letter codes (typical for Indian stocks like LICI, TATASTEEL)
        # We explicitly exclude common false positives.
        candidates = re.findall(r'\b[A-Z]{3,9}\b', answer)
        
        # 3. The "Blocklist" - The words we NEVER want to treat as tickers
        BLOCKLIST = ["NSE", "BSE", "INDIA", "STOCK", "SHARE", "PRICE", "SYMBOL", "CODE", "LTD", "LIMITED", "THE", "FOR"]
        
        valid_ticker = None
        for cand in candidates:
            if cand not in BLOCKLIST:
                valid_ticker = cand
                break # Stop at the first valid-looking ticker
        
        if valid_ticker:
            # Append .NS for Yahoo Finance
            final_ticker = f"{valid_ticker}.NS"
            print(f"   🎯 Resolved Ticker: {final_ticker}")
            return final_ticker
            
    except Exception as e:
        print(f"   ❌ Ticker search failed: {e}")

    return None

def search_stock_news(company_name: str, ticker: str) -> dict:
    if not tavily: return {"results": []}
    query = f"latest financial news {company_name} {ticker} India stock market"
    try:
        return tavily.search(query=query, topic="news", days=3, max_results=3)
    except: return {"results": []}

def search_missing_metric(company_name: str, metric_name: str) -> str:
    if not tavily: return "N/A"
    query = f"current {metric_name} of {company_name} in Rupees"
    try:
        res = tavily.search(query=query, search_depth="basic", include_answer=True)
        return res.get("answer", "N/A")
    except: return "N/A"