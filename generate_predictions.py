#!/usr/bin/env python3
"""
generate_predictions.py
US Stock AI Prediction Script using yfinance (split-adjusted live prices) + OpenRouter (owl-alpha).
- yfinance: robust, retry-capable, split-adjusted OHLCV (10-day)
- OpenRouter: anonymized [O,H,L,C,V_M] vector prompts → 5-day extrapolation
- History snapshots: public/data/history/{date}.json (updated daily)
"""

import os
import sys
import json
import time
import random
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────────
LIMIT = 10

US_SYMBOLS = [
    ("AAPL",  "Apple Inc"),
    ("NVDA",  "NVIDIA Corporation"),
    ("TSLA",  "Tesla Inc"),
    ("MSFT",  "Microsoft Corporation"),
    ("AMZN",  "Amazon.com Inc"),
    ("META",  "Meta Platforms Inc"),
    ("GOOGL", "Alphabet Inc (Class A)"),
    ("AMD",   "Advanced Micro Devices Inc"),
    ("AVGO",  "Broadcom Inc"),
    ("NFLX",  "Netflix Inc"),
]

STOCKS_FILE       = Path("public/data/stocks.json")
PREDICTIONS_FILE = Path("public/data/predictions.json")
HISTORY_DIR       = Path("public/data/history")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SKIP_AI = os.environ.get("SKIP_AI", "false").lower() == "true"
AI_MODEL = "openrouter/owl-alpha"

# ── OpenRouter Client ───────────────────────────────────────────────────────────
def get_openrouter_client():
    from openai import OpenAI
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

# ── yfinance: split-adjusted 10-day OHLCV ─────────────────────────────────────
def fetch_yfinance_prices(symbol):
    """Fetch 10-day daily OHLCV via yfinance. Returns list of dicts, oldest first.
    Uses split-adjusted (correct) prices. Returns None on failure."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="10d", auto_adjust=True)
        if hist.empty or len(hist) < 5:
            print(f"  ⚠️  yfinance returned < 5 rows for {symbol}")
            return None

        rows = []
        for ts, row in hist.iterrows():
            dt_utc = ts.tz_localize("UTC") if ts.tzinfo is None else ts
            rows.append({
                "date":      dt_utc.strftime("%Y-%m-%d"),
                "dateShort": dt_utc.strftime("%m/%d"),
                "open":      round(float(row["Open"]),  2),
                "high":      round(float(row["High"]),  2),
                "low":       round(float(row["Low"]),   2),
                "close":     round(float(row["Close"]), 2),
                "volume":    int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                "volumeM":   round(float(row["Volume"]) / 1e6, 1) if not pd.isna(row["Volume"]) else 0,
            })
        # yfinance returns newest-first; reverse to oldest-first
        rows.reverse()
        return rows

    except Exception as e:
        print(f"  ⚠️  yfinance error for {symbol}: {e}")
        return None


# ── OpenRouter: 5-day vector extrapolation ────────────────────────────────────
def call_openrouter_ai(history_rows, stock_code):
    """Send anonymized [O,H,L,C,V_M] vectors → get 5 future steps."""
    if SKIP_AI or not OPENROUTER_API_KEY:
        return None

    segments = []
    for i, row in enumerate(history_rows[-10:]):
        segments.append(
            f"t{i+1}: [{row['open']:.2f}, {row['high']:.2f}, {row['low']:.2f}, "
            f"{row['close']:.2f}, {row['volumeM']:.1f}]"
        )
    historical_context = " | ".join(segments)

    sample_input = (
        "t1: [175.30, 176.10, 171.50, 171.50, 48.4] | "
        "t2: [173.90, 176.65, 170.75, 171.15, 56.8] | "
        "t3: [170.55, 172.65, 167.60, 168.70, 38.0]"
    )
    sample_output = (
        '[\n'
        '  {"step": "t4_ext", "values": [169.50, 171.00, 167.10, 170.30, 45.5]},\n'
        '  {"step": "t5_ext", "values": [170.30, 172.20, 169.80, 171.80, 49.2]}\n'
        ']'
    )

    node_token = f"node_us_alpha_{stock_code}"

    prompt = (
        f"You are a mathematical sequence extrapolation compiler specializing in "
        f"multi-dimensional coordinate vector progression.\n"
        f"Generate exactly 5 continuous vector steps (t11_ext to t15_ext) following "
        f"the mathematical progression pattern for the sequence node: {node_token}.\n"
        f"Do not return conversational explanations, comments, or markdown blocks. "
        f"Return ONLY a valid JSON array matching the structure shown above.\n\n"
        f"[SAMPLE]\nInput Matrix:\n{sample_input}\nOutput Matrix:\n{sample_output}\n\n"
        f"[REAL-TIME TASK]\nInput Matrix:\n{historical_context}\nOutput JSON:"
    )

    try:
        client = get_openrouter_client()
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500,
            timeout=25,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw.rsplit("\n", 1)[0]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        predicted_rows_json = json.loads(raw)
        normalised = []
        for idx, item in enumerate(predicted_rows_json):
            vals = item.get("values", [])
            if len(vals) < 5:
                continue
            raw_vol_m = float(vals[4])
            pred_label = f"PRED_{idx+1}"
            normalised.append({
                "date":      f"🔮 {pred_label}",
                "dateShort": f"🔮 {pred_label}",
                "open":      round(float(vals[0]), 2),
                "high":      round(float(vals[1]), 2),
                "low":       round(float(vals[2]), 2),
                "close":     round(float(vals[3]), 2),
                "volume":    int(raw_vol_m * 1e6),
                "volumeM":   f"{raw_vol_m:.1f}M",
            })
        return normalised

    except Exception as e:
        print(f"  ❌ OpenRouter parse failed for {stock_code}: {e}")
        return None


# ── ETNet US Top 20 scraper ────────────────────────────────────────────────────
def fetch_etnet_us_top():
    ETNET_URL = "https://www.etnet.com.hk/www/tc/us-stocks/top20.php?tab=turnover"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(ETNET_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"  ⚠️  ETNet fetch failed: {e}")
        return None

    import re
    pattern = r'"turnover":\s*\{[^}]*"chartdata":\s*(\[[\s\S]*?\])\}'
    match = re.search(pattern, html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    stocks = []
    for item in data:
        code = item.get("code", "").strip()
        name = item.get("name", "").strip()
        value = item.get("value", 0)
        if code:
            stocks.append({"code": code, "name": name, "turnover": value})
    stocks.sort(key=lambda x: x["turnover"], reverse=True)
    return stocks[:LIMIT]


# ── Helpers ─────────────────────────────────────────────────────────────────────
def calc_pct(prices):
    if len(prices) < 2:
        return 0.0
    return round((prices[-1]["close"] / prices[0]["close"] - 1) * 100, 2)


def write_history_snapshot(stocks_output, date_str):
    """Write a dated history snapshot for the date selector."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    snap_file = HISTORY_DIR / f"{date_str}.json"
    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump(stocks_output, f, ensure_ascii=False, indent=2)

    # Update manifest
    manifest_file = HISTORY_DIR / "manifest.json"
    existing = []
    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            existing = json.load(f)
    if date_str not in existing:
        existing.append(date_str)
        existing.sort(reverse=True)
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False)
    print(f"  📁 History snapshot: {snap_file}")


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    date_str = now_hkt.strftime("%Y-%m-%d")
    print(f"🚀 US Stock 2 pipeline started {now_hkt.strftime('%Y-%m-%d %H:%M:%S HKT')}")

    # ── Step 1: Stock list from ETNet ─────────────────────────────────────────
    etnet_stocks = fetch_etnet_us_top()
    if etnet_stocks:
        symbols = [(s["code"], s["name"]) for s in etnet_stocks]
        print(f"📡 ETNet Top {len(symbols)}: {[c for c,_ in symbols]}")
    else:
        symbols = US_SYMBOLS[:LIMIT]
        print(f"📡 Fallback list: {[c for c,_ in symbols]}")

    # ── Step 2: Fetch yfinance prices ──────────────────────────────────────────
    print("📊 Fetching yfinance 10-day OHLCV (split-adjusted)...")
    predictions_db = {}
    stocks_list = []

    for i, (symbol, name) in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] {symbol} ({name})...", end="", flush=True)

        prices = fetch_yfinance_prices(symbol)
        if not prices:
            # No mock fallback — fail hard so we never ship stale data
            print(f"  ❌ yfinance failed for {symbol}, aborting pipeline")
            sys.exit(1)

        pct = calc_pct(prices)
        print(f" ✅ ${prices[-1]['close']:.2f} {pct:+.2f}% ({len(prices)} days)")

        # ── Step 3: OpenRouter AI extrapolation ─────────────────────────────
        ai_rows = call_openrouter_ai(prices, symbol)
        has_ai = ai_rows is not None and len(ai_rows) == 5
        hist_10 = prices[-10:] if len(prices) > 10 else prices
        combined = hist_10 + (ai_rows or [])

        predictions_db[symbol] = {
            "name":         name,
            "symbol":       symbol,
            "has_ai":       has_ai,
            "combined_data": combined,
        }

        stock_entry = {
            "code":       symbol,
            "symbol":     symbol,
            "name":       name,
            "prices":     hist_10,
            "fiveDayPct": pct,
            "high10":     max(p["high"] for p in hist_10) if hist_10 else 0,
            "low10":      min(p["low"]  for p in hist_10) if hist_10 else 0,
        }
        stocks_list.append(stock_entry)

        if i < len(symbols) - 1:
            time.sleep(0.3)

    # ── Step 4: Build + write stocks.json ─────────────────────────────────────
    STOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    stocks_output = {
        "generatedAt": now_hkt.strftime("%Y-%m-%d %H:%M:%S") + " HKT",
        "stockCount": len(stocks_list),
        "stocks":     stocks_list,
    }
    with open(STOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks_output, f, ensure_ascii=False, indent=2)
    print(f"✅ stocks.json → {STOCKS_FILE}")

    # ── Step 5: Write predictions.json ─────────────────────────────────────────
    PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(predictions_db, f, ensure_ascii=False, indent=2)
    print(f"✅ predictions.json → {PREDICTIONS_FILE}")

    # ── Step 6: Write history snapshot ─────────────────────────────────────────
    write_history_snapshot(stocks_output, date_str)

    ai_count = sum(1 for v in predictions_db.values() if v["has_ai"])
    print(f"\n✅ Done! {len(predictions_db)} stocks, {ai_count} with AI predictions")
    if not OPENROUTER_API_KEY or SKIP_AI:
        print("⚠️  OPENROUTER_API_KEY not set — AI predictions skipped")


if __name__ == "__main__":
    main()
