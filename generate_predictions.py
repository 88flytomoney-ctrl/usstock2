#!/usr/bin/env python3
"""
generate_predictions.py
US Stock AI Prediction Script using Alpha Vantage (confirmed close prices) + OpenRouter (owl-alpha).
- Alpha Vantage TIME_SERIES_DAILY: last 10 completed trading days, reliable canonical closes
- OpenRouter owl-alpha: 5-step vector extrapolation on [open,high,low,close,volumeM]
- Predictions stored in public/data/predictions.json with 15-row combined_data per stock
Usage:
    SKIP_AI=true python generate_predictions.py   # skip AI, prices only
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from openai import OpenAI

# ── OpenRouter Client ──────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

def get_openrouter_client():
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

# ── Alpha Vantage Config ──────────────────────────────────────────────────────
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_API_KEY  = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
LIMIT                  = 10   # top-10 stocks
OUTPUT_FILE            = Path("public/data/predictions.json")
STOCKS_FILE           = Path("public/data/stocks.json")
HISTORY_DIR            = Path("public/data/history")
AI_MODEL_ID           = "openrouter/owl-alpha"

# ── ETNet: fetch Top-10 US stocks by turnover ─────────────────────────────────
ETNET_URL = "https://www.etnet.com.hk/www/tc/us-stocks/top20.php?tab=turnover"

def fetch_etnet_top10():
    """Fetch top-10 US stocks by turnover from ETNet."""
    print("📡 Fetching ETNet US Top-20 by turnover...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(ETNET_URL, headers=headers, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"❌ ETNet fetch failed: {e}")
        return []

    # Parse the embedded turnover chartdata JSON
    import re
    pattern = r'"turnover":\s*\{[^}]*"chartdata":\s*(\[[\s\S]*?\])'
    match = re.search(pattern, html)
    if not match:
        print("⚠️  Could not parse ETNet turnover data")
        return []

    json_str = match.group(1)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try to find the last valid closing bracket
        last_valid = json_str.rfind("}]")
        if last_valid > 0:
            data = json.loads(json_str[:last_valid + 2])
        else:
            return []

    stocks = []
    for item in data:
        code = item.get("code", "").strip()
        name = item.get("name", "").strip()
        value = item.get("value", 0)
        if code:
            stocks.append({"code": code, "name": name, "turnover": value})

    stocks.sort(key=lambda x: x["turnover"], reverse=True)
    print(f"  → Found {len(stocks)} stocks from ETNet")
    return stocks[:LIMIT]


# ── Alpha Vantage: 10-day daily prices ─────────────────────────────────────────
def fetch_alpha_vantage_prices(symbol):
    """Fetch 10-day daily OHLCV for a symbol from Alpha Vantage.
    Returns list of {date, dateShort, open, high, low, close, volume, volumeM}, oldest first.
    Returns None on failure (caller will use fallback).
    Free tier: 5 calls/minute. We add a 13-s delay between calls.
    """
    if not ALPHA_VANTAGE_API_KEY:
        print(f"  ⚠️  ALPHA_VANTAGE_API_KEY not set, skipping {symbol}")
        return None

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": ALPHA_VANTAGE_API_KEY,
        "outputsize": "compact",   # last 100 trading days, we take last 10
    }
    try:
        resp = requests.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=30)
        data = resp.json()

        # Handle rate limiting
        if "Note" in data and "rate limit" in data["Note"].lower():
            print(f"  ⚠️  Alpha Vantage rate limit, backing off...")
            time.sleep(60)
            return None

        if "Time Series (Daily)" not in data:
            error_msg = data.get("Note", data.get("Error Message", "No data"))
            print(f"  ⚠️  {symbol}: {str(error_msg)[:60]}")
            return None

        time_series = data["Time Series (Daily)"]
        # Sort dates ascending (oldest first), take last 10
        sorted_dates = sorted(time_series.keys())
        if len(sorted_dates) < 5:
            print(f"  ⚠️  {symbol}: only {len(sorted_dates)} days returned")
            return None

        rows = []
        for date in sorted_dates[-10:]:
            daily = time_series[date]
            close  = float(daily["4. close"])
            open_p = float(daily["1. open"])
            high   = float(daily["2. high"])
            low    = float(daily["3. low"])
            vol    = int(daily["5. volume"])
            rows.append({
                "date":      date,
                "dateShort": datetime.strptime(date, "%Y-%m-%d").strftime("%m/%d"),
                "open":      open_p,
                "high":      high,
                "low":       low,
                "close":     close,
                "volume":    vol,
                "volumeM":   round(vol / 1e6, 2),
            })
        return rows

    except Exception as e:
        print(f"  ❌ {symbol} fetch error: {e}")
        return None


# ── OpenRouter AI: 5-step vector extrapolation ──────────────────────────────────
def call_openrouter_ai(symbol, combined_data):
    """Send 15-row [O,H,L,C,V_M] vector array to OpenRouter owl-alpha.
    Returns list of 5 predicted rows [{date,dateShort,open,high,low,close,volume,volumeM}].
    """
    if not OPENROUTER_API_KEY:
        return None

    prompt = _build_ai_prompt(symbol, combined_data)
    client = get_openrouter_client()
    try:
        response = client.chat.completions.create(
            model=AI_MODEL_ID,
            messages=[
                {
                    "role": "developer",
                    "content": (
                        "You are a precise quantitative finance AI. You output ONLY a JSON "
                        "array of 5 future daily OHLCV steps derived strictly from the "
                        "input price vector array. Each step must be a JSON object with "
                        "exact keys: date (YYYY-MM-DD), dateShort (MM/DD), open, high, "
                        "low, close, volume, volumeM. All values must be numbers. "
                        "Output only the JSON array, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences
        raw = raw.strip().strip("```json").strip("```").strip()
        predictions = json.loads(raw)
        if not isinstance(predictions, list) or len(predictions) != 5:
            print(f"  ⚠️  {symbol}: invalid AI response format")
            return None
        return predictions

    except Exception as e:
        print(f"  ❌ {symbol} AI error: {e}")
        return None


def _build_ai_prompt(symbol, combined_data):
    """Build anonymized 5D vector prompt: [open, high, low, close, volumeM]."""
    lines = [f"Symbol: {symbol}", "Historical 10-day OHLCV + VolumeM (oldest → latest):"]
    for row in combined_data:
        lines.append(
            f"[{row['open']:.2f}, {row['high']:.2f}, {row['low']:.2f}, "
            f"{row['close']:.2f}, {row['volumeM']:.2f}]"
        )
    lines.append(
        "Based on the above momentum and volume pattern, project the next 5 daily "
        "OHLCV steps. Respond with ONLY a JSON array of 5 objects with keys: "
        "date (YYYY-MM-DD), dateShort (MM/DD), open, high, low, close, volume, volumeM."
    )
    return "\n".join(lines)


# ── Analysis: rule-based signals ───────────────────────────────────────────────
def analyze_stock(prices):
    """Rule-based trend + signal analysis."""
    if not prices or len(prices) < 2:
        return {"signal": "neutral", "trend": "unknown", "pctChange": 0}

    first = prices[0]["close"]
    last  = prices[-1]["close"]
    pct   = round(((last - first) / first) * 100, 2)

    if len(prices) >= 5:
        ma5 = sum(p["close"] for p in prices[-5:]) / 5
    else:
        ma5 = sum(p["close"] for p in prices) / len(prices)

    trend_map = {"uptrend": "📈 Uptred", "downtrend": "📉 Downtr", "sideways": "➡️ Side"}
    if last > ma5 * 1.01:
        trend = "uptrend"
    elif last < ma5 * 0.99:
        trend = "downtrend"
    else:
        trend = "sideways"

    # Recent 2-day momentum
    if len(prices) >= 2:
        momentum = prices[-1]["close"] - prices[-2]["close"]
        if momentum > 0.5:
            signal = "strong_buy"
        elif momentum > 0:
            signal = "buy"
        elif momentum < -0.5:
            signal = "strong_sell"
        else:
            signal = "sell"
    else:
        signal = "neutral"

    return {"signal": signal, "trend": trend, "pctChange": pct}


# ── Main pipeline ──────────────────────────────────────────────────────────────
def main():
    skip_ai = os.environ.get("SKIP_AI", "").lower() == "true"
    hk_tz   = timezone(timedelta(hours=8))
    ts      = datetime.now(hk_tz).strftime("%Y-%m-%d %H:%M")
    print(f"🚀 US Stock pipeline started {ts}")

    # Step 1: Get top-10 symbols from ETNet
    etnet_stocks = fetch_etnet_top10()
    if not etnet_stocks:
        print("❌ No stocks from ETNet, exiting.")
        sys.exit(1)

    # Step 2: Fetch prices for each stock (Alpha Vantage, with rate-limit delay)
    stocks_results  = []
    predictions_out = {}
    today_str = datetime.now(hk_tz).strftime("%Y-%m-%d")

    for i, st in enumerate(etnet_stocks):
        sym  = st["code"]
        name = st["name"]
        print(f"[{i+1}/{len(etnet_stocks)}] {sym} ({name})...", end=" ", flush=True)

        prices = fetch_alpha_vantage_prices(sym)

        # Rate-limit padding: Alpha Vantage free tier = 5 calls/min
        time.sleep(13)

        if not prices:
            print("⚠️  no data, skipped")
            continue

        last_close = prices[-1]["close"]
        first_close = prices[0]["close"]
        pct = round(((last_close - first_close) / first_close) * 100, 2)
        trend_arrow = "▲" if pct >= 0 else "▼"
        print(f"✅ ${last_close:.2f} {trend_arrow} {pct:+.2f}% ({len(prices)} days)")

        analysis = analyze_stock(prices)
        combined_data = list(prices)   # 10 historical rows

        # Step 3: AI prediction (unless skipped)
        has_ai = False
        if not skip_ai and OPENROUTER_API_KEY:
            ai_rows = call_openrouter_ai(sym, combined_data)
            if ai_rows:
                combined_data = list(prices) + ai_rows
                has_ai = True

        # Step 4: Write history snapshot
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        snap_file = HISTORY_DIR / f"{today_str}.json"
        snap = {"date": today_str, "stocks": etnet_stocks, "prices": {sym: prices}}
        snap_file.write_text(json.dumps(snap, ensure_ascii=False, indent=2))

        # Update manifest
        manifest = HISTORY_DIR / "manifest.json"
        dates = json.loads(manifest.read_text()) if manifest.exists() else []
        if today_str not in dates:
            dates.append(today_str)
        manifest.write_text(json.dumps(dates))

        # Stock result
        stocks_results.append({
            "code":         sym,
            "name":         name,
            "prices":       prices,
            "lastClose":    last_close,
            "pctChange":    pct,
            "high10":       round(max(r["high"] for r in prices), 2),
            "low10":        round(min(r["low"]  for r in prices), 2),
            "volumeM":      round(prices[-1]["volumeM"], 2),
            "signal":       analysis["signal"],
            "trend":        analysis["trend"],
        })

        # Predictions entry
        predictions_out[sym] = {
            "code":         sym,
            "name":         name,
            "combined_data": combined_data,   # 10 hist + 5 AI
            "has_ai":       has_ai,
        }

    # Step 5: Write stocks.json
    STOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    stocks_payload = {
        "generatedAt": f"{ts} HKT",
        "stockCount":  len(stocks_results),
        "stocks":      stocks_results,
    }
    STOCKS_FILE.write_text(json.dumps(stocks_payload, ensure_ascii=False, indent=2))
    print(f"✅ stocks.json → {STOCKS_FILE}")

    # Step 6: Write predictions.json
    OUTPUT_FILE.write_text(json.dumps(predictions_out, ensure_ascii=False, indent=2))
    print(f"✅ predictions.json → {OUTPUT_FILE}")

    ai_count = sum(1 for v in predictions_out.values() if v["has_ai"])
    print(f"\n✅ Done! {len(stocks_results)} stocks, {ai_count} with AI predictions")
    if skip_ai:
        print("ℹ️   SKIP_AI=true, AI predictions skipped")


if __name__ == "__main__":
    main()
