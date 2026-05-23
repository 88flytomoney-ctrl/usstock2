import MiniChart from './MiniChart.jsx';

const SIGNAL_COLORS = {
  'strong buy': { bg: 'bg-blue-900/40', text: 'text-blue-400', label: '💎 強烈買入' },
  'buy':        { bg: 'bg-blue-900/30', text: 'text-blue-300', label: '✅ 買入' },
  'hold':       { bg: 'bg-slate-800',   text: 'text-slate-300', label: '⏸ 持有' },
  'watch':      { bg: 'bg-yellow-900/30', text: 'text-yellow-400', label: '👁 觀望' },
  'sell':       { bg: 'bg-orange-900/30', text: 'text-orange-400', label: '⚠️ 賣出' },
  'strong sell':{ bg: 'bg-red-900/40',  text: 'text-red-400',    label: '🔴 強烈賣出' },
  'neutral':    { bg: 'bg-slate-800',   text: 'text-slate-400',  label: '➖ 中性' },
};

function getSignalStyle(signal) {
  return SIGNAL_COLORS[signal] || SIGNAL_COLORS['neutral'];
}

function fmt(v) { return typeof v === 'number' ? v.toFixed(2) : '—'; }

export default function StockCard({ stock, prediction }) {
  const { code, name, symbol, prices = [], pctChange = 0 } = stock;
  const fiveDayPct = pctChange;

  // combined_data: [0-9] = 10 historical, [10-14] = 5 AI predicted
  const hasAi    = prediction?.has_ai && Array.isArray(prediction.combined_data);
  const histRows = hasAi ? prediction.combined_data.slice(0, 10) : prices;
  const predRows = hasAi ? prediction.combined_data.slice(10, 15) : [];
  const chartRows = hasAi ? prediction.combined_data : prices;

  const isUp = fiveDayPct >= 0;
  const arrow = isUp ? '▲' : '▼';

  const latestPrice = histRows.length ? histRows[histRows.length - 1].close : null;
  const priceChange = latestPrice && histRows[0]
    ? (histRows[histRows.length - 1].close - histRows[0].close)
    : null;

  // 5-day / 10-day high & low (from historical rows)
  const hi5 = histRows.length ? Math.max(...histRows.map(p => p.high)) : 0;
  const lo5 = histRows.length ? Math.min(...histRows.map(p => p.low))  : 0;

  const sigStyle = getSignalStyle('neutral'); // analysis signal not present in usstock2

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden hover:border-slate-600 transition-colors">

      {/* ── Dashboard Header ── */}
      <div className="px-4 pt-4 pb-3">

        {/* Row 1: Ticker + Name + Badges */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Ticker badge */}
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold ${
              isUp ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
            }`}>
              {arrow} {Math.abs(fiveDayPct).toFixed(2)}%
            </span>
            <span className="font-mono text-sm text-slate-300 font-semibold">{symbol}</span>
            {hasAi && (
              <span className="text-xs bg-purple-900/50 text-purple-300 px-2 py-0.5 rounded">
                🔮 AI
              </span>
            )}
          </div>
          <div className={`badge ${sigStyle.bg} ${sigStyle.text} text-xs`}>
            {sigStyle.label}
          </div>
        </div>

        {/* Row 2: Name */}
        <h3 className="font-bold text-white text-base leading-tight mb-2">{name}</h3>

        {/* Row 3: Latest price + 5-day high/low */}
        {latestPrice && (
          <div className="flex items-baseline justify-between border-t border-slate-700 pt-2 mt-1">
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-bold text-white">${fmt(latestPrice)}</span>
              <span className="text-sm text-slate-400">USD</span>
            </div>
            <div className="text-right text-xs text-slate-400 space-y-0.5">
              <p>10日高 ${fmt(hi5)}</p>
              <p>10日低 ${fmt(lo5)}</p>
            </div>
          </div>
        )}

        {/* Row 4: Price change + trend */}
        {priceChange !== null && (
          <div className="flex items-center justify-between mt-2">
            <div className={`text-sm font-medium ${isUp ? 'text-green-400' : 'text-red-400'}`}>
              {isUp ? '▲' : '▼'} ${fmt(Math.abs(priceChange))} ({isUp ? '+' : ''}{fiveDayPct.toFixed(2)}%)
            </div>
          </div>
        )}
      </div>

      {/* ── Candlestick Chart (15 bars: 10 hist + 5 AI) ── */}
      {chartRows.length > 0 && (
        <MiniChart prices={chartRows} hasAi={hasAi} histCount={10} />
      )}

      {/* ── Historical Price Table (10 days) ── */}
      {histRows.length > 0 && (
        <div className="px-3 pb-2">
          <div className="bg-slate-700/40 px-3 py-1.5 flex items-center gap-2 border-b border-slate-600/40">
            <span className="text-slate-300 text-xs font-semibold">📅 歷史報價（10日）</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-700">
                  <th className="text-left py-1 px-1 font-medium">日期</th>
                  <th className="text-right py-1 px-1 font-medium">開</th>
                  <th className="text-right py-1 px-1 font-medium">高</th>
                  <th className="text-right py-1 px-1 font-medium">低</th>
                  <th className="text-right py-1 px-1 font-medium">收</th>
                  <th className="text-right py-1 px-1 font-medium">量(M)</th>
                </tr>
              </thead>
              <tbody>
                {[...histRows].reverse().map((row, idx) => {
                  const prevRow = idx > 0 ? histRows[histRows.length - 1 - idx + 1] : null;
                  const rowUp = prevRow ? row.close >= prevRow.close : true;
                  return (
                    <tr key={row.date} className={`border-b border-slate-700/30 last:border-0 ${idx === 0 ? 'bg-slate-700/20' : ''}`}>
                      <td className="py-1 px-1 text-slate-400">{row.dateShort || row.date}</td>
                      <td className="text-right px-1 text-slate-300">${fmt(row.open)}</td>
                      <td className="text-right px-1 text-red-400">${fmt(row.high)}</td>
                      <td className="text-right px-1 text-green-400">${fmt(row.low)}</td>
                      <td className={`text-right px-1 font-medium ${rowUp ? 'text-green-400' : 'text-red-400'}`}>
                        ${fmt(row.close)}
                      </td>
                      <td className="text-right px-1 text-slate-400">{row.volumeM || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── AI Prediction Table (future 5 days) ── */}
      {hasAi && predRows.length > 0 && (
        <div className="ai-prediction-matrix border border-dashed border-purple-500/30 p-3 rounded-lg mt-2 mx-3 mb-3">
          <div className="bg-purple-900/30 px-3 py-1.5 flex items-center gap-2 border-b border-purple-700/40 mb-2">
            <span className="text-purple-300 text-xs font-semibold">🔮 AI 預測（未來5日）</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-purple-400/70 border-b border-purple-700/30">
                  <th className="text-left py-1 px-1 font-medium">日期</th>
                  <th className="text-right py-1 px-1 font-medium">開</th>
                  <th className="text-right py-1 px-1 font-medium">高</th>
                  <th className="text-right py-1 px-1 font-medium">低</th>
                  <th className="text-right py-1 px-1 font-medium">收</th>
                  <th className="text-right py-1 px-1 font-medium">量(M)</th>
                </tr>
              </thead>
              <tbody>
                {predRows.map((row, idx) => (
                  <tr key={idx} className="border-b border-purple-700/20 last:border-0">
                    <td className="py-1 px-1 text-purple-300">{row.dateShort || row.date}</td>
                    <td className="text-right px-1 text-slate-300">${fmt(row.open)}</td>
                    <td className="text-right px-1 text-red-400">${fmt(row.high)}</td>
                    <td className="text-right px-1 text-green-400">${fmt(row.low)}</td>
                    <td className="text-right px-1 font-medium text-purple-200">${fmt(row.close)}</td>
                    <td className="text-right px-1 text-purple-300">{row.volumeM || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!hasAi && (
        <div className="text-center text-xs text-slate-600 py-2 px-3">
          🔮 AI 預測（請設定 OPENROUTER_API_KEY）
        </div>
      )}
    </div>
  );
}
