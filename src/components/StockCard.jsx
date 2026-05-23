import MiniChart from './MiniChart.jsx';

function fmt(v)  { return typeof v === 'number' ? v.toFixed(2) : '—'; }
function vol(v)  { return typeof v === 'number' ? `${v.toFixed(1)}M` : '—'; }
function pct(v)  { return typeof v === 'number' ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—'; }

export default function StockCard({ stock, prediction }) {
  const { code, name, prices = [], fiveDayPct = 0 } = stock;

  // combined_data: [0-9] = 10 historical days, [10-14] = 5 AI future days
  const hasAi     = prediction?.has_ai && Array.isArray(prediction.combined_data);
  const histRows  = hasAi ? prediction.combined_data.slice(0, 10) : prices;
  const predRows  = hasAi ? prediction.combined_data.slice(10, 15) : [];
  const chartRows = hasAi ? prediction.combined_data : prices;

  const lastClose  = histRows.length ? histRows[histRows.length - 1].close : null;
  const openClose   = histRows.length ? histRows[0].close : null;
  const priceChange = lastClose && openClose ? lastClose - openClose : null;
  const isUp = priceChange >= 0;

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden hover:border-slate-600 transition-colors">

      {/* ── Card Header ── */}
      <div className="px-4 py-3 flex items-center justify-between border-b border-slate-700">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white">{code}</span>
            <span className="text-xs text-slate-400">{name}</span>
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-lg font-bold text-white">{lastClose ? fmt(lastClose) : '—'}</span>
            {priceChange !== null && (
              <span className={`text-sm font-medium ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                {isUp ? '▲' : '▼'} {fmt(Math.abs(priceChange))}
              </span>
            )}
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${isUp ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
              {fiveDayPct >= 0 ? '+' : ''}{fiveDayPct.toFixed(2)}%
            </span>
          </div>
        </div>
        {hasAi && (
          <span className="text-xs bg-purple-900/50 text-purple-300 px-2 py-1 rounded">
            🔮 AI 預測
          </span>
        )}
      </div>

      {/* ── Candlestick Chart (15 bars: 10 hist + 5 AI) ── */}
      {chartRows.length > 0 && (
        <MiniChart prices={chartRows} hasAi={hasAi} histCount={10} />
      )}

      {/* ── Historical Table (first 10 days) ── */}
      {histRows.length > 0 && (
        <div className="px-3 py-2">
          <div className="bg-slate-700/40 px-3 py-1.5 flex items-center gap-2 border-b border-slate-600/40">
            <span className="text-slate-300 text-xs font-semibold">📅 歷史報價（10日）</span>
          </div>
          <table className="w-full text-xs mt-1">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-1 px-1 font-medium">日期</th>
                <th className="text-right py-1 px-1 font-medium">開</th>
                <th className="text-right py-1 px-1 font-medium">高</th>
                <th className="text-right py-1 px-1 font-medium">低</th>
                <th className="text-right py-1 px-1 font-medium">收</th>
                <th className="text-right py-1 px-1 font-medium">成交量</th>
              </tr>
            </thead>
            <tbody>
              {[...histRows].reverse().map((row, idx) => {
                const rowUp = idx > 0 ? row.close >= histRows[histRows.length - 1 - idx + 1].close : true;
                return (
                  <tr key={row.date} className="text-slate-300 border-b border-slate-700/30 last:border-0">
                    <td className="py-1 px-1">{row.dateShort || row.date}</td>
                    <td className="text-right px-1">{fmt(row.open)}</td>
                    <td className="text-right px-1 text-red-300">{fmt(row.high)}</td>
                    <td className="text-right px-1 text-green-300">{fmt(row.low)}</td>
                    <td className={`text-right px-1 font-medium ${rowUp ? 'text-green-300' : 'text-red-300'}`}>
                      {fmt(row.close)}
                    </td>
                    <td className="text-right px-1 text-slate-400">{vol(row.volumeM)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── AI Prediction Table (future 5 days) ── */}
      {hasAi && predRows.length > 0 && (
        <div className="ai-prediction-matrix border border-dashed border-purple-500/30 p-3 rounded-lg mt-3 bg-purple-950/10 mx-3 mb-3">
          <div className="bg-purple-900/30 px-3 py-1.5 flex items-center gap-2 border-b border-purple-700/40">
            <span className="text-purple-300 text-xs font-semibold">🔮 AI 預測（未來5日）</span>
          </div>
          <table className="w-full text-xs mt-1">
            <thead>
              <tr className="text-purple-400/70 border-b border-purple-700/30">
                <th className="text-left py-1 px-1 font-medium">日期</th>
                <th className="text-right py-1 px-1 font-medium">開</th>
                <th className="text-right py-1 px-1 font-medium">高</th>
                <th className="text-right py-1 px-1 font-medium">低</th>
                <th className="text-right py-1 px-1 font-medium">收</th>
                <th className="text-right py-1 px-1 font-medium">成交量</th>
              </tr>
            </thead>
            <tbody>
              {predRows.map((row, idx) => (
                <tr key={idx} className="text-purple-200 border-b border-purple-700/20 last:border-0">
                  <td className="py-1 px-1">{row.dateShort || row.date}</td>
                  <td className="text-right px-1">{fmt(row.open)}</td>
                  <td className="text-right px-1 text-red-300">{fmt(row.high)}</td>
                  <td className="text-right px-1 text-green-300">{fmt(row.low)}</td>
                  <td className="text-right px-1 font-medium text-purple-100">{fmt(row.close)}</td>
                  <td className="text-right px-1 text-slate-400">{vol(row.volumeM)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!hasAi && (
        <div className="text-center text-xs text-slate-600 py-2">
          🔮 AI 預測（請設定 OPENROUTER_API_KEY）
        </div>
      )}
    </div>
  );
}
