#!/usr/bin/env python3
"""
build_us_report.py — Fetch US Stock 2 data, generate a static report.html
with market indices, 22 tracked stocks, today's highlights, and 10-day standouts.
Supports historical archives with a date selector dropdown.

Data source: https://88flytomoney-ctrl.github.io/usstock2/data/predictions.json
Output:      public/report.html      (latest report)
             public/archive/*.html    (historical snapshots)
             public/archive/index.json (archive manifest)

Usage:
  python3 build_us_report.py --dry-run   # generate locally, don't push
  python3 build_us_report.py             # generate + archive + git commit + push
"""
import json
import os
import sys
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_URL = "https://88flytomoney-ctrl.github.io/usstock2/data/predictions.json"
LOCAL_DATA = "public/data/predictions.json"
PUBLIC_DIR = Path("public")
OUTPUT_FILE = PUBLIC_DIR / "report.html"
ARCHIVE_DIR = PUBLIC_DIR / "archive"
ARCHIVE_INDEX = ARCHIVE_DIR / "index.json"
HK_TZ = timezone(timedelta(hours=8))


def fetch_data():
    """Read predictions JSON from local file (pipeline just wrote it),
    or fall back to the live URL if the local file doesn't exist."""
    import os
    if os.path.exists(LOCAL_DATA):
        with open(LOCAL_DATA, "r", encoding="utf-8") as f:
            return json.loads(f.read())
    # Fallback: fetch from live site
    req = urllib.request.Request(DATA_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def compute_stock_stats(stocks):
    """Return a list of dicts with today % and 10-day % for each stock."""
    rows = []
    for code, stock in stocks.items():
        name = stock.get("name", "?")
        rec = stock.get("recommendation", "—")
        combined = stock.get("combined_data", [])
        actual = [d for d in combined if not d.get("is_predicted")]
        if len(actual) < 2:
            continue
        last = actual[-1]
        prev = actual[-2]
        first = actual[0]
        today_chg = ((last["close"] - prev["close"]) / prev["close"]) * 100
        ten_chg = ((last["close"] - first["close"]) / first["close"]) * 100
        rows.append({
            "code": code,
            "name": name,
            "close": last["close"],
            "today_chg": today_chg,
            "ten_chg": ten_chg,
            "rec": rec,
        })
    order = {"買入": 0, "持有": 1, "賣出": 2}
    rows.sort(key=lambda r: order.get(r["rec"], 9))
    return rows


def build_html(data, rows, archive_dates=None, current_date=None):
    """Build the full HTML report. If current_date is set, it's an archive page."""
    indices = data.get("indices", {})
    is_archive = current_date is not None
    now_str = current_date if current_date else datetime.now(HK_TZ).strftime("%Y/%m/%d %H:%M HKT")

    # Build archive dropdown
    archive_options = '<option value="">最新數據</option>\n'
    if archive_dates:
        for d in archive_dates:
            selected = ' selected' if d == current_date else ''
            label = d.replace("-", "/")
            archive_options += f'<option value="{d}"{selected}>{label}</option>\n'

    # Dropdown redirect script
    dropdown_html = ""
    if archive_dates is not None:
        if is_archive:
            onchange = ("document.location.href="
                         "this.value? '../archive/'+this.value+'.html'"
                         ": '../report.html'")
        else:
            onchange = ("document.location.href="
                         "this.value? 'archive/'+this.value+'.html'"
                         ": 'report.html'")
        dropdown_html = f"""
  <div class="mb-4">
    <label class="text-sm text-gray-400 mr-2">📜 歷史記錄:</label>
    <select onchange="{onchange}" class="bg-gray-800 text-gray-100 border border-gray-600 rounded px-3 py-1.5 text-sm">
      {archive_options}
    </select>
  </div>"""

    # Indices rows
    idx_rows = ""
    for key in ["spx", "ixic", "dji"]:
        idx = indices.get(key, {})
        arrow = "▲" if idx.get("isPositive") else "▼"
        color = "#22c55e" if idx.get("isPositive") else "#ef4444"
        name = idx.get("name", key.upper())
        val = f"{idx.get('value', 0):,.2f}"
        chg = f"{arrow} {idx.get('change', 0):+,.2f} ({idx.get('pct', 0):+.2f}%)"
        idx_rows += f'<tr><td class="px-4 py-2 font-semibold">{name}</td><td class="px-4 py-2 text-right">{val}</td><td class="px-4 py-2 text-right" style="color:{color}">{chg}</td></tr>\n'

    # Stock rows
    s_rows = ""
    gainers = []
    losers = []
    for r in rows:
        t_arrow = "▲" if r["today_chg"] > 0 else "▼" if r["today_chg"] < 0 else "→"
        t_color = "#22c55e" if r["today_chg"] > 0 else "#ef4444" if r["today_chg"] < 0 else "#888"
        d_arrow = "▲" if r["ten_chg"] > 0 else "▼" if r["ten_chg"] < 0 else "→"
        d_color = "#22c55e" if r["ten_chg"] > 0 else "#ef4444" if r["ten_chg"] < 0 else "#888"
        rec_color = {"買入": "#22c55e", "賣出": "#ef4444", "持有": "#f59e0b"}.get(r["rec"], "#888")
        s_rows += (
            f'<tr>'
            f'<td class="px-3 py-2 font-mono">{r["code"]}</td>'
            f'<td class="px-3 py-2">{r["name"]}</td>'
            f'<td class="px-3 py-2 text-right">{r["close"]:,.2f}</td>'
            f'<td class="px-3 py-2 text-right" style="color:{t_color}">{t_arrow} {r["today_chg"]:+.2f}%</td>'
            f'<td class="px-3 py-2 text-right" style="color:{d_color}">{d_arrow} {r["ten_chg"]:+.2f}%</td>'
            f'<td class="px-3 py-2 text-center font-semibold" style="color:{rec_color}">{r["rec"]}</td>'
            f'</tr>\n'
        )
        if r["today_chg"] > 0:
            gainers.append(r)
        else:
            losers.append(r)

    # Today highlights
    gainers.sort(key=lambda x: x["today_chg"], reverse=True)
    losers.sort(key=lambda x: x["today_chg"])
    top_gainers = ", ".join(f'{r["name"]} ({r["code"]}) {r["today_chg"]:+.2f}%' for r in gainers[:3])
    top_losers = ", ".join(f'{r["name"]} ({r["code"]}) {r["today_chg"]:+.2f}%' for r in losers[:3])
    adv_dec = f'{len(gainers)} 升 {len(losers)} 跌'

    buy_count = sum(1 for r in rows if r["rec"] == "買入")
    sell_count = sum(1 for r in rows if r["rec"] == "賣出")
    hold_count = sum(1 for r in rows if r["rec"] == "持有")

    # 10-day highlights
    sorted_10d = sorted(rows, key=lambda x: x["ten_chg"], reverse=True)
    biggest_gainer = sorted_10d[0]
    runner_up = sorted_10d[1]
    biggest_loser = sorted_10d[-1]
    buy_list = ", ".join(f'{r["name"]} ({r["code"]})' for r in rows if r["rec"] == "買入")
    sell_list = ", ".join(f'{r["name"]} ({r["code"]})' for r in rows if r["rec"] == "賣出")

    title = f"US Stock 2 AI — {current_date}" if is_archive else "US Stock 2 AI — Summary Report"

    html = f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>body{{font-family:system-ui,-apple-system,sans-serif;}}table{{border-collapse:collapse;}}</style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
<div class="max-w-5xl mx-auto px-4 py-8">

  <!-- Header -->
  <h1 class="text-3xl font-bold mb-1">US Stock 2 🤖 AI — Summary Report</h1>
  <p class="text-gray-400 mb-2">最後更新: {now_str}</p>
  {dropdown_html}

  <!-- Market Indices -->
  <h2 class="text-xl font-semibold mb-3">🇺🇸 US Market Indices</h2>
  <table class="w-full mb-6 text-sm border border-gray-700 rounded-lg overflow-hidden">
    <thead class="bg-gray-800">
      <tr><th class="px-4 py-2 text-left">指數</th><th class="px-4 py-2 text-right">Value</th><th class="px-4 py-2 text-right">Change</th></tr>
    </thead>
    <tbody>
      {idx_rows}
    </tbody>
  </table>

  <!-- Tracked Stocks -->
  <h2 class="text-xl font-semibold mb-3">📈 Tracked Stocks ({len(rows)} tickers)</h2>
  <table class="w-full mb-6 text-sm border border-gray-700 rounded-lg overflow-hidden">
    <thead class="bg-gray-800">
      <tr>
        <th class="px-3 py-2 text-left">Ticker</th>
        <th class="px-3 py-2 text-left">Company</th>
        <th class="px-3 py-2 text-right">Price (USD)</th>
        <th class="px-3 py-2 text-right">Today Chg %</th>
        <th class="px-3 py-2 text-right">10-Day Chg %</th>
        <th class="px-3 py-2 text-center">AI 建議</th>
      </tr>
    </thead>
    <tbody class="divide-y divide-gray-800">
      {s_rows}
    </tbody>
  </table>

  <!-- Today Highlights -->
  <h2 class="text-xl font-semibold mb-3">🔑 Key Highlights</h2>
  <div class="bg-gray-900 rounded-lg p-5 mb-4 border border-gray-700">
    <h3 class="text-lg font-semibold mb-3">📅 Today</h3>
    <ul class="space-y-1 text-sm">
      <li><b>大市:</b> S&P 500 {indices.get('spx',{}).get('change',0):+,.2f} ({indices.get('spx',{}).get('pct',0):+.2f}%), Nasdaq {indices.get('ixic',{}).get('change',0):+,.2f} ({indices.get('ixic',{}).get('pct',0):+.2f}%), Dow {indices.get('dji',{}).get('change',0):+,.2f} ({indices.get('dji',{}).get('pct',0):+.2f}%)</li>
      <li><b class="text-green-400">今日最強:</b> {top_gainers}</li>
      <li><b class="text-red-400">今日最弱:</b> {top_losers}</li>
      <li><b>升跌比:</b> {adv_dec}</li>
      <li><b>AI 分佈:</b> 買入 {buy_count} 檔 · 賣出 {sell_count} 檔 · 持有 {hold_count} 檔</li>
    </ul>
  </div>

  <!-- 10-Day Highlights -->
  <div class="bg-gray-900 rounded-lg p-5 mb-4 border border-gray-700">
    <h3 class="text-lg font-semibold mb-3">📊 10-Day Standouts</h3>
    <ul class="space-y-1 text-sm">
      <li><b class="text-green-400">Biggest gainer:</b> {biggest_gainer['name']} ({biggest_gainer['code']}) ▲ {biggest_gainer['ten_chg']:+.2f}% → ${biggest_gainer['close']:,.2f}</li>
      <li><b class="text-green-400">Runner-up:</b> {runner_up['name']} ({runner_up['code']}) ▲ {runner_up['ten_chg']:+.2f}% → ${runner_up['close']:,.2f}</li>
      <li><b class="text-red-400">Biggest loser:</b> {biggest_loser['name']} ({biggest_loser['code']}) ▼ {biggest_loser['ten_chg']:+.2f}% → ${biggest_loser['close']:,.2f}</li>
    </ul>
  </div>

  <!-- AI Signals -->
  <div class="bg-gray-900 rounded-lg p-5 mb-4 border border-gray-700">
    <h3 class="text-lg font-semibold mb-3">🤖 AI Signals</h3>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
      <div><b class="text-green-400">Buy ({buy_count}):</b> {buy_list}</div>
      <div><b class="text-red-400">Sell ({sell_count}):</b> {sell_list}</div>
    </div>
  </div>

  <!-- Footer -->
  <p class="text-xs text-gray-500 mt-8 text-center">
    數據來源：Yahoo Finance · AI 預測：OpenRouter · 僅供參考，不構成投資建議
  </p>

</div>
</body>
</html>"""
    return html


def load_archive_index():
    """Load existing archive/index.json, or return empty list."""
    if ARCHIVE_INDEX.exists():
        with open(ARCHIVE_INDEX) as f:
            return json.load(f)
    return []


def save_archive_index(dates):
    """Save archive dates to index.json (newest first)."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_INDEX, "w", encoding="utf-8") as f:
        json.dump(dates, f, ensure_ascii=False, indent=2)


def archive_today(data, rows, archive_dates):
    """Save today's report as an archive snapshot and update index."""
    today = datetime.now(HK_TZ).strftime("%Y-%m-%d")

    # Build archive HTML with the dropdown showing all dates
    archive_html = build_html(data, rows, archive_dates=archive_dates, current_date=today)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_file = ARCHIVE_DIR / f"{today}.html"
    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(archive_html)
    print(f"✅ Archive saved: {archive_file}")

    # Update index (newest first, no duplicates)
    if today not in archive_dates:
        archive_dates.insert(0, today)
    save_archive_index(archive_dates)
    print(f"✅ Archive index updated: {len(archive_dates)} dates")

    return archive_dates


def git_push():
    """Commit and push report.html + archive/ to main branch."""
    subprocess.run(["git", "add", str(OUTPUT_FILE), "public/archive/"], capture_output=True, text=True)

    r = subprocess.run(
        ["git", "commit", "-m", f"🤖 Auto-update US report + archive {datetime.now(HK_TZ).strftime('%Y-%m-%d %H:%M')}"],
        capture_output=True, text=True
    )
    if r.returncode != 0 and "nothing to commit" not in r.stdout:
        print(f"  git commit: {r.stdout.strip()} {r.stderr.strip()}")

    subprocess.run(["git", "pull", "--rebase"], capture_output=True, text=True)
    r = subprocess.run(["git", "push"], capture_output=True, text=True)
    if r.returncode == 0:
        print("✅ Pushed to GitHub")
    else:
        print(f"⚠ Push failed: {r.stderr.strip()}")


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"🚀 Building US report at {datetime.now(HK_TZ).strftime('%Y-%m-%d %H:%M')} HKT{' (dry-run)' if dry_run else ''}")

    data = fetch_data()
    rows = compute_stock_stats(data["stocks"])

    # Load existing archive dates
    archive_dates = load_archive_index()
    print(f"  → Existing archives: {len(archive_dates)}")

    # 1. Save today's archive snapshot
    archive_dates = archive_today(data, rows, archive_dates)

    # 2. Generate the latest report.html (with dropdown showing all archive dates)
    html = build_html(data, rows, archive_dates=archive_dates, current_date=None)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Written {OUTPUT_FILE} ({len(html)} bytes, {len(rows)} stocks)")

    if not dry_run:
        git_push()


if __name__ == "__main__":
    main()
