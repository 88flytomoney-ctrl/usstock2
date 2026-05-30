import { useState, useEffect } from 'react';
import StockCard from './components/StockCard.jsx';
import MarketIndices from './components/MarketIndices.jsx';

const PREDICTIONS_URL  = '/usstock2/data/predictions.json';
const MANIFEST_URL     = '/usstock2/data/history/manifest.json';

function App() {
  const [stocks,       setStocks]       = useState([]);
  const [marketIndices, setMarketIndices] = useState([]);
  const [predictions,  setPredictions]  = useState({});
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState(null);
  const [lastUpdated,  setLastUpdated]  = useState('');
  const [historyDates, setHistoryDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Transform predictions.json → { stocks[], marketIndices[], predictions{} }
  function transformPredictions(predData) {
    const stocksList = [];
    const predMap = {};
    const stocks = predData.stocks || {};
    for (const code of Object.keys(stocks)) {
      const s = stocks[code];
      const combined = s.combined_data || [];
      // Build stock list item matching the old stocks.json format
      stocksList.push({
        code,
        name: s.name,
        symbol: s.symbol,
        prices: combined.filter(r => !r.is_predicted),
        pctChange: 0, // will compute below
      });
      predMap[code] = s;
    }
    // Compute pctChange for each stock
    for (const st of stocksList) {
      const p = st.prices;
      if (p.length >= 2) {
        st.pctChange = ((p[p.length - 1].close - p[0].close) / p[0].close) * 100;
      }
    }
    // Market indices — map from predictions.json indices format
    const indices = predData.indices || {};
    const idxArr = Object.entries(indices).map(([key, v]) => ({
      ticker: key.toUpperCase(),
      name: v.name,
      price: v.value,
      pctChange: v.pct,
      arrow: v.isPositive ? '▲' : '▼',
    }));

    return { stocksList, marketIndices: idxArr, predictions: predMap };
  }

  // Load initial (latest) data
  useEffect(() => {
    fetch(PREDICTIONS_URL)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        const { stocksList, marketIndices, predictions } = transformPredictions(d);
        setStocks(stocksList);
        setMarketIndices(marketIndices);
        setPredictions(predictions);
        setLastUpdated(new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Hong_Kong' }));
        setLoading(false);
      })
      .catch(e => { setError(e.message); setLoading(false); });

    fetch(MANIFEST_URL)
      .then(r => r.ok ? r.json() : [])
      .then(dates => setHistoryDates(dates))
      .catch(() => setHistoryDates([]));
  }, []);

  // Switch to a historical date snapshot
  useEffect(() => {
    if (!selectedDate) {
      // Reload latest
      fetch(PREDICTIONS_URL)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(d => {
          const { stocksList, marketIndices, predictions } = transformPredictions(d);
          setStocks(stocksList);
          setMarketIndices(marketIndices);
          setPredictions(predictions);
          setLastUpdated(new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Hong_Kong' }));
          setError(null);
          setLoadingHistory(false);
        })
        .catch(e => { setError(e.message); setLoadingHistory(false); });
      return;
    }

    setLoadingHistory(true);
    const url = `/usstock2/data/history/${selectedDate}.json`;
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => {
        const { stocksList, marketIndices, predictions } = transformPredictions(d);
        setStocks(stocksList);
        setMarketIndices(marketIndices);
        setPredictions(predictions);
        setLastUpdated(d.generatedAt || '');
        setError(null);
        setLoadingHistory(false);
      })
      .catch(e => { setError(e.message); setLoadingHistory(false); });
  }, [selectedDate]);

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="text-center">
        <div className="text-4xl mb-4 animate-spin">📊</div>
        <p className="text-slate-400">載入中...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900">
      <div className="text-center card max-w-md">
        <div className="text-4xl mb-4">⚠️</div>
        <h2 className="text-lg font-bold text-red-400 mb-2">載入失敗</h2>
        <p className="text-slate-400 text-sm mb-4">{error}</p>
        <button className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm" onClick={() => window.location.reload()}>
          重試
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-900">

      {/* ── Header ── */}
      <header className="bg-slate-800 border-b border-slate-700 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between gap-4">

          {/* Left: Brand */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <svg className="w-8 h-8" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="6" fill="#1d4ed8"/>
              <path d="M6 20 L12 14 L17 18 L22 10 L28 14" stroke="#fbbf24" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="28" cy="14" r="2" fill="#fbbf24"/>
            </svg>
            <div>
              <h1 className="text-xl font-bold text-white leading-tight">
                US Stock 2 <span className="text-xs text-purple-400 ml-1">🤖 AI</span>
              </h1>
              <p className="text-xs text-slate-400">Alpha Vantage 10日 · OpenRouter 5日預測</p>
            </div>
          </div>

          {/* Center: Loading indicator */}
          <div className="flex-1 flex justify-center">
            {loadingHistory && (
              <div className="flex items-center gap-2 text-blue-400 text-xs">
                <span className="animate-pulse">⏳ 載入歷史數據...</span>
              </div>
            )}
          </div>

          {/* Right: Last updated + History selector */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="text-right">
              <p className="text-xs text-slate-400">最後更新 (HKT)</p>
              <p className="text-sm font-medium text-slate-200 leading-tight">{lastUpdated}</p>
            </div>

            {/* History Date Selector */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">📅</span>
              <select
                value={selectedDate}
                onChange={e => setSelectedDate(e.target.value)}
                className="px-2 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-slate-200 cursor-pointer hover:border-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
              >
                <option value="">最新數據</option>
                {historyDates.length === 0 && (
                  <option value="" disabled>— 尚無歷史記錄 —</option>
                )}
                {historyDates.map(d => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
          </div>

        </div>
      </header>

      {/* ── Main ── */}
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">

        {/* Market Indices Dashboard */}
        {marketIndices.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">
              🌐 Global Indices
            </h2>
            <MarketIndices indices={marketIndices} />
          </section>
        )}

        {/* Section header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-200">
            📈 美股行情（{stocks.length} 檔）
          </h2>
          {selectedDate && (
            <span className="text-xs text-slate-500 bg-slate-800 px-2 py-1 rounded border border-slate-700">
              📅 歷史數據：{selectedDate}
            </span>
          )}
        </div>

        {/* Stock grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {stocks.map(stock => (
            <StockCard
              key={stock.code}
              stock={stock}
              prediction={predictions[stock.code]}
            />
          ))}
        </div>

        <footer className="text-center text-xs text-slate-500 py-8">
          數據來源：ETNet + Alpha Vantage · 全球指數：Yahoo Finance · AI 預測：OpenRouter owl-alpha · 僅供參考，不構成投資建議
        </footer>
      </main>
    </div>
  );
}

export default App;
