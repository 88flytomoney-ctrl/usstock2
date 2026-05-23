import { useState, useEffect } from 'react';
import StockCard from './components/StockCard.jsx';

const STOCKS_URL = '/usstock2/data/stocks.json';
const PREDICTIONS_URL = '/usstock2/data/predictions.json';

function App() {
  const [stocks, setStocks]     = useState([]);
  const [predictions, setPredictions] = useState({});
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [lastUpdated, setLastUpdated] = useState('');

  useEffect(() => {
    Promise.all([
      fetch(STOCKS_URL).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
      fetch(PREDICTIONS_URL).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
    ])
      .then(([stocksData, predData]) => {
        setStocks(stocksData.stocks || []);
        setPredictions(predData || {});
        setLastUpdated(stocksData.generatedAt || '');
        setLoading(false);
      })
      .catch(e => {
        console.error('Load failed:', e);
        setError(e.message);
        setLoading(false);
      });
  }, []);

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
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <svg className="w-8 h-8" viewBox="0 0 32 32" fill="none">
              <rect width="32" height="32" rx="6" fill="#1d4ed8"/>
              <path d="M6 20 L12 14 L17 18 L22 10 L28 14" stroke="#fbbf24" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="28" cy="14" r="2" fill="#fbbf24"/>
            </svg>
            <div>
              <h1 className="text-xl font-bold text-white">US Stock 2 <span className="text-xs text-purple-400 ml-1">🤖 AI</span></h1>
              <p className="text-xs text-slate-400">Yahoo 10日 · OpenRouter 5日預測</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400">最後更新 (HKT)</p>
            <p className="text-sm font-medium text-slate-200">{lastUpdated}</p>
          </div>
        </div>
      </header>

      {/* ── Main ── */}
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <section>
          <h2 className="text-lg font-semibold mb-4 text-slate-200">
            📈 美股行情（{stocks.length} 檔）
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {stocks.map(stock => (
              <StockCard
                key={stock.code}
                stock={stock}
                prediction={predictions[stock.code]}
              />
            ))}
          </div>
        </section>

        <footer className="text-center text-xs text-slate-500 py-8">
          數據來源：ETNet + Yahoo Finance · AI 預測：OpenRouter owl-alpha · 僅供參考，不構成投資建議
        </footer>
      </main>
    </div>
  );
}

export default App;
