import { useEffect, useRef } from 'react';

/**
 * MiniChart — HTML5 Canvas candlestick chart.
 * Props:
 *   prices  — array of { date, open, high, low, close, volumeM }
 *   hasAi   — boolean, whether AI predictions are present
 *   histCount — number of historical (non-AI) candles (default 10)
 */
export default function MiniChart({ prices = [], hasAi = false, histCount = 10 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || prices.length === 0) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.offsetWidth;
    const H = 120;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, W, H);

    const n = prices.length;
    const pad  = { left: 4, right: 4, top: 8, bottom: 20 };
    const chartW  = W - pad.left - pad.right;
    const chartH  = H - pad.top  - pad.bottom;
    const barW    = Math.max(2, (chartW / n) - 1);

    // Compute OHLC range
    let minP = Infinity, maxP = -Infinity;
    for (const p of prices) {
      if (p.low  < minP) minP = p.low;
      if (p.high > maxP) maxP = p.high;
    }
    const range   = maxP - minP || 1;
    const scale   = chartH / range;
    const midY    = (y) => pad.top + (maxP - y) * scale;
    const barH    = (p) => Math.max(1, (p.high - p.low) * scale);
    const bodyY   = (p) => midY(Math.max(p.open, p.close));
    const bodyH   = (p) => Math.max(1, Math.abs(p.close - p.open) * scale);

    // Grid lines
    ctx.strokeStyle = 'rgba(148,163,184,0.08)';
    ctx.lineWidth   = 1;
    for (let i = 0; i <= 3; i++) {
      const y = pad.top + (chartH / 3) * i;
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    }

    // Draw candles
    prices.forEach((p, i) => {
      const x      = pad.left + i * (barW + 1) + barW / 2;
      const isPred = hasAi && i >= histCount;
      const isUp   = p.close >= p.open;

      // Colour scheme
      if (isPred) {
        ctx.strokeStyle = '#c084fc';   // purple-400 for AI candles
        ctx.fillStyle   = 'rgba(192,132,252,0.25)';
      } else {
        ctx.strokeStyle = isUp ? '#4ade80' : '#f87171';
        ctx.fillStyle   = isUp ? 'rgba(74,222,128,0.25)' : 'rgba(248,113,113,0.25)';
      }

      // Wick
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, midY(p.high));
      ctx.lineTo(x, midY(p.low));
      ctx.stroke();

      // Body
      const by = bodyY(p);
      const bh = bodyH(p);
      if (isPred) {
        // Dashed outline for AI predicted candles
        ctx.setLineDash([2, 2]);
        ctx.strokeRect(x - barW / 2, by, barW, bh || 2);
        ctx.fillRect(x - barW / 2, by, barW, bh || 2);
        ctx.setLineDash([]);
      } else {
        ctx.fillRect(x - barW / 2, by, barW, bh || 2);
      }
    });

    // X-axis date labels
    ctx.fillStyle      = 'rgba(148,163,184,0.5)';
    ctx.font           = '9px monospace';
    ctx.textAlign      = 'center';
    const step         = n > 15 ? Math.ceil(n / 6) : 1;
    for (let i = 0; i < n; i += step) {
      const x = pad.left + i * (barW + 1) + barW / 2;
      ctx.fillText(prices[i].dateShort || prices[i].date || '', x, H - 4);
    }

    // HKT watermark
    ctx.fillStyle   = 'rgba(148,163,184,0.2)';
    ctx.font        = '8px monospace';
    ctx.textAlign   = 'right';
    ctx.fillText('HKT', W - 4, H - 4);
  }, [prices, hasAi, histCount]);

  return (
    <div className="w-full bg-slate-900/50 px-3 py-1">
      <canvas
        ref={canvasRef}
        className="w-full"
        style={{ height: '120px', display: 'block' }}
      />
    </div>
  );
}
