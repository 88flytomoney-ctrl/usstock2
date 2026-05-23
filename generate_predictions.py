#!/usr/bin/env python3
"""
generate_predictions.py
US Stock AI Prediction Script using OpenRouter (openrouter/owl-alpha).
Anonymized vector-based prompts: [open, high, low, close, volumeM] per timestamp.
Combines 10-day Yahoo Finance historical data + 5-day AI extrapolation = 15-period view.
"""

import os
import sys
import json
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────────
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
LIMIT = 10  # number of US stocks to process

# Top US stocks by market cap / relevance (ETNet-like list)
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
    ("ASML",  "ASML Holding NV"),
    ("INTC",  "Intel Corporation"),
    ("QCOM",  "QUALCOMM Inc"),
    ("TXN",   "Texas Instruments Inc"),
    ("AMAT",  "Applied Materials Inc"),
]

STOCKS_FILE = Path("public/data/stocks.json")
PREDICTIONS_FILE = Path("public/data/predictions.json")
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

# ── Yahoo Finance: 10-day OHLCV ────────────────────────────────────────────────
def fetch_yahoo_prices(symbol):
    """Fetch 10-day daily OHLCV from Yahoo Finance. Returns list of dicts, oldest first."""
    url = YAHOO_BASE.format(symbol=symbol)
    params = {"interval": "1d", "range": "10d"}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ⚠️  Yahoo fetch error for {symbol}: {e}")
        return None

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quotes = result["indicators"]["quote"][0]
        volumes = result["indicators"]["quote"][0].get("volume", [])
        adj_close = result["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, IndexError):
        print(f"  ⚠️  Malformed Yahoo response for {symbol}")
        return None

    rows = []
    for i, ts in enumerate(timestamps):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        close  = quotes["close"][i]
        open_  = quotes["open"][i]
        high   = quotes["high"][i]
        low    = quotes["low"][i]
        vol    = volumes[i] if i < len(volumes) else None
        if close is None or close == 0:
            continue
        rows.append({
            "date":      dt.strftime("%Y-%m-%d"),
            "dateShort": dt.strftime("%m/%d"),
            "open":      round(float(open_),  2) if open_  else round(float(close), 2),
            "high":      round(float(high),   2) if high   else round(float(close), 2),
            "low":       round(float(low),    2) if low    else round(float(close), 2),
            "close":     round(float(close),  2),
            "volume":    int(vol) if vol else 0,
            "volumeM":   round(float(vol) / 1e6, 1) if vol else 0,
        })

    return rows if len(rows) >= 5 else None


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
        # Strip markdown code fences
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
            pred_label = f"PRED_{idx+1}"
            normalised.append({
                "date":      f"🔮 {pred_label}",
                "dateShort": f"🔮 {pred_label}",
                "open":      round(float(vals[0]), 2),
                "high":      round(float(vals[1]), 2),
                "low":       round(float(vals[2]), 2),
                "close":     round(float(vals[3]), 2),
                "volume":    int(float(vals[4]) * 1e6),
                "volumeM":   f"{vals[4]:.1f}M",
            })
        return normalised

    except Exception as e:
        print(f"  ❌ OpenRouter parse failed for {stock_code}: {e}")
        return None


# ── ETNet US Top 20 scraper ────────────────────────────────────────────────────
def fetch_etnet_us_top():
    """Scrape ETNet US stocks top 20 by turnover. Returns list of (symbol, name)."""
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


# ── Mock fallback prices ───────────────────────────────────────────────────────
def get_mock_prices(symbol):
    """Return deterministic mock 10-day OHLCV data."""
    random.seed(hash(symbol) % 1000)
    base_prices = {
        "AAPL": 190, "NVDA": 870, "TSLA": 245, "MSFT": 415,
        "AMZN": 190, "META": 505, "GOOGL": 175, "AMD": 165,
        "AVGO": 1250, "NFLX": 620,
    }
    base = base_prices.get(symbol, 100)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    rows = []
    for i in range(10):
        d = today - timedelta(days=9 - i)
        close = round(base * (1 + random.uniform(-0.025, 0.025)), 2)
        open_p = round(close * (1 + random.uniform(-0.01, 0.01)), 2)
        high = round(max(close, open_p) * (1 + random.uniform(0, 0.01)), 2)
        low = round(min(close, open_p) * (1 - random.uniform(0, 0.01)), 2)
        vol = int(random.uniform(8e6, 60e6))
        rows.append({
            "date":      d.strftime("%Y-%m-%d"),
            "dateShort": d.strftime("%m/%d"),
            "open":  open_p, "high": high, "low": low,
            "close": close,
            "volume": vol, "volumeM": round(vol / 1e6, 1),
        })
        base = close
    return rows


# ── Stock price change helpers ─────────────────────────────────────────────────
def calc_pct(prices):
    if len(prices) < 2:
        return 0.0
    return round((prices[-1]["close"] / prices[0]["close"] - 1) * 100, 2)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    now_hkt = datetime.now(timezone(timedelta(hours=8)))
    print(f"🚀 US Stock 2 pipeline started {now_hkt.strftime('%Y-%m-%d %H:%M:%S HKT')}")

    # ── Step 1: Fetch stock list from ETNet ───────────────────────────────────
    etnet_stocks = fetch_etnet_us_top()
    if etnet_stocks:
        symbols = [(s["code"], s["name"]) for s in etnet_stocks]
        print(f"📡 ETNet Top {len(symbols)} US stocks: {[c for c,_ in symbols]}")
    else:
        symbols = US_SYMBOLS[:LIMIT]
        print(f"📡 Using fallback symbol list: {[c for c,_ in symbols]}")

    # ── Step 2: Fetch Yahoo Finance prices ───────────────────────────────────
    print("📊 Fetching Yahoo Finance 10-day OHLCV...")
    predictions_db = {}   # code -> full prediction object
    stocks_list = []      # for stocks.json (simplified, OHLCV only)

    for i, (symbol, name) in enumerate(symbols):
        print(f"[{i+1}/{len(symbols)}] {symbol} ({name})...", end="", flush=True)

        prices = fetch_yahoo_prices(symbol)
        if not prices:
            print(" ⚠️ Yahoo failed, using mock")
            prices = get_mock_prices(symbol)

        pct = calc_pct(prices)
        print(f" ✅ {pct:+.2f}% ({len(prices)} days)")

        # ── Step 3: OpenRouter AI extrapolation ─────────────────────────────
        ai_rows = call_openrouter_ai(prices, symbol) if prices else None
        has_ai = ai_rows is not None and len(ai_rows) == 5
        combined = (prices[-10:] if len(prices) > 10 else prices) + (ai_rows or [])

        predictions_db[symbol] = {
            "name":        name,
            "symbol":      symbol,
            "has_ai":      has_ai,
            "combined_data": combined,
        }

        # ── stocks.json entry (OHLCV only) ────────────────────────────────
        hist_prices = prices[-10:] if len(prices) > 10 else prices
        stock_entry = {
            "code":    symbol,
            "symbol":  symbol,
            "name":    name,
            "prices":  hist_prices,
            "fiveDayPct": pct,
            "high10":  max(p["high"] for p in hist_prices) if hist_prices else 0,
            "low10":   min(p["low"]  for p in hist_prices) if hist_prices else 0,
        }
        stocks_list.append(stock_entry)

        if i < len(symbols) - 1:
            time.sleep(0.5)

    # ── Step 4: Write predictions.json ─────────────────────────────────────────
    PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(predictions_db, f, ensure_ascii=False, indent=2)
    print(f"✅ predictions.json → {PREDICTIONS_FILE} ({len(predictions_db)} stocks)")

    # ── Step 5: Write stocks.json ──────────────────────────────────────────────
    STOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    stocks_output = {
        "generatedAt": now_hkt.strftime("%Y-%m-%d %H:%M:%S") + " HKT",
        "stockCount":  len(stocks_list),
        "stocks":      stocks_list,
    }
    with open(STOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks_output, f, ensure_ascii=False, indent=2)
    print(f"✅ stocks.json → {STOCKS_FILE}")

    ai_count = sum(1 for v in predictions_db.values() if v["has_ai"])
    print(f"\n✅ Done! {len(predictions_db)} stocks, {ai_count} with AI predictions")
    if not OPENROUTER_API_KEY or SKIP_AI:
        print("⚠️  OPENROUTER_API_KEY not set — AI predictions skipped")


if __name__ == "__main__":
    main()
