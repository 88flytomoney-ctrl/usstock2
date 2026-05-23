/**
 * MarketIndices – global market overview panel
 * Displays S&P 500, Nasdaq Composite, and Dow Jones from stocks.json marketIndices field.
 */
function MarketIndices({ indices }) {
  if (!indices || indices.length === 0) return null;

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      {indices.map((idx) => {
        const up = idx.pctChange >= 0;
        const color = up ? "text-green-400" : "text-red-400";
        const bar  = up ? "bg-green-500"   : "bg-red-500";

        return (
          <div
            key={idx.ticker}
            className="bg-slate-800 rounded-xl px-5 py-4 border border-slate-700 flex flex-col gap-1"
          >
            {/* Ticker + name */}
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-slate-400 font-medium tracking-wide uppercase">
                {idx.ticker}
              </span>
              <span className={`text-xs font-bold ${color}`}>
                {idx.arrow} {Math.abs(idx.pctChange).toFixed(2)}%
              </span>
            </div>

            {/* Price */}
            <div className="flex items-end justify-between">
              <span className="text-xl font-bold text-white leading-none">
                {idx.price.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
              <span className="text-xs text-slate-500 mb-0.5">
                {idx.name}
              </span>
            </div>

            {/* Mini change bar */}
            <div className="mt-1 h-1 w-full rounded-full bg-slate-700 overflow-hidden">
              <div
                className={`h-full rounded-full ${bar}`}
                style={{
                  // Scale bar to show magnitude (cap at 5%)
                  width: `${Math.min(Math.abs(idx.pctChange) / 5 * 100, 100)}%`,
                  marginLeft: up ? 0 : "auto",
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default MarketIndices;
