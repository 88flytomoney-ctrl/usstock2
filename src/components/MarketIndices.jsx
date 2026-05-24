/**
 * MarketIndices – global market overview panel
 * Displays S&P 500, Nasdaq Composite, and Dow Jones from stocks.json marketIndices field.
 * Fixed: responsive typography, stacked layout, fluid grid to prevent overflow on mobile.
 */
function MarketIndices({ indices }) {
  if (!indices || indices.length === 0) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 mb-6">
      {indices.map((idx) => {
        const up    = idx.pctChange >= 0;
        const color = up ? "text-green-400" : "text-red-400";
        const bar   = up ? "bg-green-500"   : "bg-red-500";

        return (
          <div
            key={idx.ticker}
            className="bg-slate-800 rounded-xl px-4 py-3 sm:px-5 sm:py-4 border border-slate-700 flex flex-col justify-between min-w-0 overflow-hidden"
          >
            {/* Row 1: Ticker tag + % badge */}
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs text-slate-400 font-medium tracking-wide uppercase truncate">
                {idx.ticker}
              </span>
              <span className={`text-xs font-bold ${color} shrink-0`}>
                {idx.arrow} {Math.abs(idx.pctChange).toFixed(2)}%
              </span>
            </div>

            {/* Row 2: Large price value — responsive, stacks cleanly */}
            <div className="flex flex-col justify-end min-w-0">
              <span className="text-xl sm:text-2xl lg:text-3xl font-bold text-white leading-none tracking-tight truncate"
                title={idx.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}>
                {idx.price.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
              {/* Secondary label: hidden on very small screens, visible on sm+ */}
              <span className="hidden sm:block text-xs text-slate-500 mt-1 truncate">
                {idx.name}
              </span>
            </div>

            {/* Row 3: Mini change bar */}
            <div className="mt-2 h-1 w-full rounded-full bg-slate-700 overflow-hidden">
              <div
                className={`h-full rounded-full ${bar}`}
                style={{
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