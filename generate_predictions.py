#!/usr/bin/env python3
"""
generate_predictions.py (US Stock 2 Version)
Appends 5-day future sequence coordinates to 10-day historical US stock datasets.
Saves up to two records per stock day: [Actual] and [AI Predicted].
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, date
from pathlib import Path
import yfinance as yf
from openai import OpenAI

# ── OpenRouter Configuration ──────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OUTPUT_FILE = Path("public/data/predictions.json")
AI_MODEL_ID = "@preset/free"

# Top 20 High-Turnover US Stocks to track — fetched dynamically from etnet
# PINNED_TICKERS are always tracked (always at top, live data via existing pipeline)
PINNED_TICKERS = ["QQQ", "VOO"]
US_TICKERS = []

def fetch_us_tickers_from_etnet():
    """Fetch top 20 US stocks by turnover from etnet."""
    import urllib.request
    import re
    
    url = "https://www.etnet.com.hk/www/tc/us-stocks/top20.php?tab=turnover"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode("utf-8")
    
    # Extract unique stock symbols from quote links
    pattern = r'/www/tc/us-stocks/quote/([A-Z]+)'
    tickers = sorted(set(re.findall(pattern, html)))[:20]
    
    print(f"[Etnet] Fetched {len(tickers)} tickers: {tickers}")
    return tickers

def build_ticker_list():
    """Combine PINNED_TICKERS (always first) + ETNet dynamic list (deduped)."""
    try:
        etnet_tickers = fetch_us_tickers_from_etnet()
    except Exception as e:
        print(f"[Etnet] Failed to fetch tickers: {e}")
        # Fallback to common US tickers
        etnet_tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "TSLA", "GOOGL", "META", "NFLX",
                         "AMD", "SPY", "IWM", "AVGO", "COIN", "PLTR", "SOXX", "XLF",
                         "XLK", "VGT", "MU", "INTC"]
    
    # Pinned tickers always first; drop any duplicates from ETNet list
    pinned_set = set(PINNED_TICKERS)
    deduped_etnet = [t for t in etnet_tickers if t not in pinned_set]
    combined = PINNED_TICKERS + deduped_etnet
    print(f"[Tickers] Pinned: {PINNED_TICKERS} | Total: {len(combined)} → {combined}")
    return combined

# Fetch tickers on module load
if not US_TICKERS:
    US_TICKERS = build_ticker_list()

def get_openrouter_client():
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

def load_existing_database():
    """Loads existing predictions.json to preserve historical predictions."""
    if not OUTPUT_FILE.exists():
        return {}
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("stocks", {})
    except Exception as e:
        print(f"⚠️ Failed to load existing database: {e}")
        return {}

def fetch_global_indices():
    """Fetches real-time index data using yfinance (Accurate & Rate-Limit Free)"""
    import pandas as pd
    
    indices = {
        "^GSPC": {"name": "S&P 500", "key": "spx"},
        "^IXIC": {"name": "Nasdaq", "key": "ixic"},
        "^DJI": {"name": "Dow Jones", "key": "dji"}
    }
    results = {}
    for ticker, info in indices.items():
        try:
            time.sleep(0.5)  # avoid rate limiting
            obj = yf.Ticker(ticker)
            hist = obj.history(period="5d")  # fetch more days to find 2 valid rows
            if hist.empty:
                print(f"⚠️ No history for index {ticker}")
                continue
            
            # Drop NaN rows first (weekends/holidays)
            hist = hist.dropna(subset=["Close"])
            if len(hist) < 2:
                print(f"⚠️ Less than 2 valid days for index {ticker}")
                continue
            
            close_today = round(float(hist["Close"].iloc[-1]), 2)
            close_yesterday = round(float(hist["Close"].iloc[-2]), 2)
            
            if pd.isna(close_today) or pd.isna(close_yesterday):
                print(f"⚠️ NaN in index {ticker} close values, skipping")
                continue
            
            change = round(close_today - close_yesterday, 2)
            pct = round((change / close_yesterday) * 100, 2)
            results[info["key"]] = {
                "name": info["name"],
                "value": close_today,
                "change": change,
                "pct": pct,
                "isPositive": change >= 0
            }
            print(f"📈 {info['name']}: {close_today} ({change:+.2f} / {pct:+.2f}%)")
        except Exception as e:
            print(f"⚠️ Failed to fetch index {ticker}: {e}")
    
    if not results:
        print("⚠️ No indices fetched — all failed, using empty defaults")
    return results

def fetch_us_prices(tickers):
    import pandas as pd
    
    results = []
    for ticker_symbol in tickers:
        try:
            print(f"📊 Fetching Yahoo Finance data for {ticker_symbol}...")
