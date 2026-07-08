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
AI_MODEL_ID = "poolside/laguna-xs-2.1:free"

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
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            name = info.get("longName", ticker_symbol)
            
            # Fetch 15 days to ensure we get 10 clean trading days after dropna
            hist = ticker.history(period="15d")
            if hist.empty: continue
            
            # Drop NaN rows (weekends/holidays) BEFORE tail
            hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
            hist = hist.tail(10) # Grab the final 10 days of real history
            rows = []
            for timestamp, row in hist.iterrows():
                close_val = round(float(row["Close"]), 2)
                open_val  = round(float(row["Open"]), 2)
                high_val  = round(float(row["High"]), 2)
                low_val   = round(float(row["Low"]), 2)
                
                # Extra safety: skip any remaining NaN
                if any(pd.isna(v) for v in [close_val, open_val, high_val, low_val]):
                    continue
                
                vol = int(row["Volume"]) if pd.notna(row["Volume"]) else 0
                rows.append({
                    "date":      timestamp.strftime("%Y-%m-%d"),
                    "dateShort": timestamp.strftime("%m/%d"),
                    "close":     close_val,
                    "open":      open_val,
                    "high":      high_val,
                    "low":       low_val,
                    "volume":    vol,
                    "volumeM":   f"{round(vol / 1e6, 2)}M",
                    "is_predicted": False # Real transactions are tagged False
                })
            results.append({
                "code": ticker_symbol,
                "name": name,
                "symbol": ticker_symbol,
                "prices": rows
            })
        except Exception as e:
            print(f"❌ Yahoo Finance fetch failed for {ticker_symbol}: {e}")
    return results

def call_openrouter_vector_engine(history_rows, ticker_symbol):
    if not OPENROUTER_API_KEY:
        print("⚠️ OPENROUTER_API_KEY is not defined.")
        return None, "持有"

    # Convert prices to raw multidimensional coordinate vectors
    segments = []
    for i, row in enumerate(history_rows[-10:]):
        idx = i + 1
        vol_clean = str(row['volumeM']).replace('M', '')
        segments.append(f"t{idx}: [{row['open']:.2f}, {row['high']:.2f}, {row['low']:.2f}, {row['close']:.2f}, {vol_clean}]")
    historical_context = " | ".join(segments)

    sample_input = "t1: [75.30, 76.10, 71.50, 71.50, 98.4] | t2: [73.90, 76.65, 70.75, 71.15, 156.8]"
    sample_output = (
        '{\n'
        '  "extrapolated_steps": [\n'
        '    {"step": "t3_ext", "values": [74.50, 76.00, 72.10, 75.30, 180.5]},\n'
        '    {"step": "t4_ext", "values": [75.30, 77.20, 74.80, 76.80, 195.2]}\n'
        '  ],\n'
        '  "trend_direction_index": 1\n'
        '}'
    )

    node_token = f"node_us_alpha_{ticker_symbol.lower()}"

    prompt = (
        f"You are a mathematical sequence extrapolation compiler specializing in multi-dimensional coordinate vector progression.\n"
        f"Generate exactly 5 continuous vector steps (t11_ext to t15_ext) following the mathematical progression pattern for the sequence node: {node_token}.\n"
        f"Also determine the overall extrapolated trend vector index 'trend_direction_index' as an integer: 1 for upward continuation, 0 for range-bound, or -1 for downward continuation.\n"
        f"Do not return conversational explanations or markdown blocks. Return ONLY a valid JSON object matching the sample structure shown above.\n\n"
        f"[SAMPLE]\nInput Matrix:\n{sample_input}\nOutput JSON:\n{sample_output}\n\n"
        f"[REAL-TIME TASK]\nInput Matrix:\n{historical_context}\n\n"
        f"Output JSON:"
    )

    try:
        client = get_openrouter_client()
        response = client.chat.completions.create(
            model=AI_MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=4000,
            timeout=30,
            extra_body={"reasoning": {"enabled": False}},
        )
        msg = response.choices[0].message
        raw = msg.content
        if not raw:
            # Reasoning models may put output in reasoning_content / reasoning
            raw = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if not raw:
            print(f"⚠️ Model returned empty content for {stock_code}")
            return None, "持有"
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("\n", 1)[0]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        
        parsed_response = json.loads(raw)
        predicted_rows = parsed_response.get("extrapolated_steps", [])
        trend_idx = int(parsed_response.get("trend_direction_index", 0))
        indicator_map = {1: "買入", 0: "持有", -1: "賣出"}
        recommendation = indicator_map.get(trend_idx, "持有")

        last_history_date_str = history_rows[-1]["date"]
        last_date = datetime.strptime(last_history_date_str, "%Y-%m-%d")
        
        next_trading_days = []
        curr_date = last_date
        while len(next_trading_days) < 5:
            curr_date += timedelta(days=1)
            if curr_date.weekday() < 5:
                next_trading_days.append(curr_date)

        normalised = []
        for idx, item in enumerate(predicted_rows[:5]):
            vals = item.get("values", [])
            if len(vals) < 5: continue
            target_date = next_trading_days[idx]
            raw_vol_m = float(vals[4])
            normalised.append({
                "date":      target_date.strftime("%Y-%m-%d"),
                "dateShort": f"🔮 {target_date.strftime('%m/%d')}",
                "open":      float(vals[0]),
                "high":      float(vals[1]),
                "low":       float(vals[2]),
                "close":     float(vals[3]),
                "volume":    int(raw_vol_m * 1e6),
                "volumeM":   f"{raw_vol_m:.1f}M",
                "is_predicted": True # 🛠️ FIXED: Explicitly flag as predicted for US stocks
            })
        return normalised, recommendation
    except Exception as e:
        print(f"❌ OpenRouter failed for {ticker_symbol}: {e}")
        return None, "持有"

def main():
    existing_stocks = load_existing_database()
    stocks_data = fetch_us_prices(US_TICKERS)
    indices = fetch_global_indices()

    if not stocks_data:
        print("❌ Scraper failed to fetch US pricing rows.")
        sys.exit(1)

    final_predictions_db = {}
    for stock in stocks_data:
        code    = stock["code"]
        name    = stock["name"]
        history = stock["prices"]

        # Explicitly tag the newly fetched history as ACTUAL data
        for row in history:
            row["is_predicted"] = False

        # Get fresh 5-day future predictions
        ai_rows, recommendation = call_openrouter_vector_engine(history, code)

        # ── PERSISTENCE ENGINE: Merge with old predictions ────────────────────
        past_predicted_saved = []
        if code in existing_stocks:
            old_combined = existing_stocks[code].get("combined_data", [])
            # Get the earliest actual data date
            actual_date_set = set(r['date'] for r in history)
            first_actual_date = history[0]['date'] if history else None
            for old_row in old_combined:
                # Retain older historical predictions to enable side-by-side display
                if old_row.get("is_predicted", False):
                    # Discard stale predicted rows that fall before or overlap with
                    # actual data — those dates already have real prices
                    if first_actual_date and old_row['date'] < first_actual_date:
                        continue
                    if old_row['date'] in actual_date_set:
                        continue
                    past_predicted_saved.append(old_row)

        # Merge Actual History + Old Predictions + New Predictions
        combined = history + past_predicted_saved + (ai_rows if ai_rows else [])
        
        # Collect actual dates to filter out stale predictions
        actual_dates = set(r['date'] for r in combined if not r.get('is_predicted', False))
        
        # Deduplicate: skip stale predictions that overlap with actual data dates
        unique_combined = []
        seen_keys = set()
        for row in combined:
            # Skip AI-predicted rows whose date now has real actual data
            if row.get('is_predicted', False) and row['date'] in actual_dates:
                continue
            key = f"{row['date']}_{row.get('is_predicted', False)}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_combined.append(row)

        # Sort the array chronologically by date
        unique_combined.sort(key=lambda x: (x["date"], x.get("is_predicted", False)))

        final_predictions_db[code] = {
            "name":          name,
            "symbol":        stock["symbol"],
            "combined_data": unique_combined,
            "has_ai":        ai_rows is not None,
            "recommendation": recommendation,
        }
        time.sleep(0.2)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"stocks": final_predictions_db, "indices": indices}
    
    # Safety check: ensure no NaN/Infinity before writing (invalid JSON)
    raw_json = json.dumps(payload, ensure_ascii=False, indent=2)
    if "NaN" in raw_json or "Infinity" in raw_json:
        print("❌ CRITICAL: NaN/Infinity detected in JSON output! Attempting to clean...")
        raw_json = raw_json.replace(': NaN', ': null').replace(': Infinity', ': null')
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(raw_json)
    print(f"✅ Telemetry database merged cleanly with past projections → {OUTPUT_FILE}")

    # ── Save to history ─────────────────────────────────────────────────────────
    HISTORY_DIR = Path("public/data/history")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H')
    history_file = HISTORY_DIR / f'{date_str}.json'
    
    # History file format: { generatedAt, stocks: [{ code, symbol, name, prices }] }
    history_data = {
        "generatedAt": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "generatedDate": date_str,
        "generatedTime": f"{time_str}:00",
        "stockCount": len(final_predictions_db),
        "stocks": [
            {
                "code": code,
                "symbol": details["symbol"],
                "name": details["name"],
                "prices": [row for row in details.get("combined_data", []) if not row.get("is_predicted", False)]
            }
            for code, details in final_predictions_db.items()
        ]
    }
    
    with open(history_file, "w", encoding="utf-8") as f:
        hist_json = json.dumps(history_data, ensure_ascii=False, indent=2)
        if "NaN" in hist_json or "Infinity" in hist_json:
            print("⚠️ NaN in history JSON, cleaning...")
            hist_json = hist_json.replace(': NaN', ': null').replace(': Infinity', ': null')
        f.write(hist_json)
    print(f"   ✅ History snapshot: {history_file}")

    # Update manifest
    manifest_file = HISTORY_DIR / 'manifest.json'
    existing_manifest = []
    if manifest_file.exists():
        with open(manifest_file, 'r', encoding='utf-8') as f:
            try:
                raw_data = json.load(f)
                if raw_data and isinstance(raw_data[0], str):
                    # Old format: ["2026-05-23", ...]
                    existing_manifest = []
                    for d in raw_data:
                        existing_manifest.append({
                            "date": d,
                            "time": "00:00",
                            "file": f"{d}.json",
                            "display": d
                        })
                else:
                    existing_manifest = raw_data
            except:
                existing_manifest = []
    
    # Add new entry (avoid duplicates) only if history file exists
    if history_file.exists():
        new_entry = {
            "date": date_str,
            "time": f"{time_str}:00",
            "file": f"{date_str}.json",
            "display": date_str
        }
        existing_manifest = [e for e in existing_manifest if not (e['date'] == date_str)]
        existing_manifest.append(new_entry)
        existing_manifest.sort(key=lambda x: x['date'], reverse=True)
    else:
        print(f"   ⚠️ History file not found, skipping manifest update")
        # Filter out non-existent entries from manifest
        existing_manifest = [e for e in existing_manifest if (HISTORY_DIR / e['file']).exists()]
    
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump(existing_manifest, f, ensure_ascii=False)
    print(f"   ✅ Manifest updated")


if __name__ == "__main__":
    main()
