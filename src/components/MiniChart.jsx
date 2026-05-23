import { useEffect, useRef } from 'react';

/**
 * MiniChart — HTML5 Canvas candlestick chart (15 periods: 10 hist + 5 AI).
 * Props:
 *   prices   — array of { date, dateShort, open, high, low, close, volumeM }
 *   hasAi    — boolean, whether AI predictions are present
 *   histCount — number of historical (non-AI) candles (default 10)
 */
export default function MiniChart({ prices = [], hasAi = false, histCount = 10 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !prices || prices.length === 0) return;

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // ── Retina-scale the internal buffer ──────────────────────────────────────
    const rect = canvas.getBoundingClientRect();
    canvas.width  = rect.width  * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width  = rect.width;
    const height = rect.height;

    // ── Chart spacing variables ───────────────────────────────────────────────
    const paddingLeft   = 40;
    const paddingRight  = 20;
    const paddingTop    = 20;
    const paddingBottom = 20;

    const chartWidth  = width  - paddingLeft - paddingRight;
    const chartHeight = height - paddingTop   - paddingBottom;

    const totalPeriods = prices.length;   // 15 (10 hist + 5 AI)
    const stepX        = chartWidth / totalPeriods;

    // Candle width = 60% of slot; 40% clean margin gap
    const candleWidth   = Math.max(2, stepX * 0.6);
    const spacingOffset = (stepX - candleWidth) / 2;

    // ── Price scale ───────────────────────────────────────────────────────────
    const highs = prices.map(d => d.high);
    const lows  = prices.map(d => d.low);
    const maxPrice = Math.max(...highs);
    const minPrice = Math.min(...lows);
    const priceRange = maxPrice - minPrice || 1;

    const getPercentY = (price) =>
      paddingTop + chartHeight * (1 - (price - minPrice) / priceRange);

    // ── Clear canvas ──────────────────────────────────────────────────────────
    ctx.clearRect(0, 0, width, height);

    // ── Draw candles ──────────────────────────────────────────────────────────
    prices.forEach((point, i) => {
      // X – perfectly centered
      const xLeft  = paddingLeft + i * stepX + spacingOffset;
      const xCenter = Math.floor(xLeft + candleWidth / 2) + 0.5;

      const openY  = getPercentY(point.open);
      const closeY = getPercentY(point.close);
      const highY  = getPercentY(point.high);
      const lowY   = getPercentY(point.low);

      const isUp        = point.close >= point.open;
      const isPrediction = hasAi && i >= histCount;

      // Colour palette per spec
      const bodyColor   = isUp ? '#26a69a' : '#ef5350';
      const strokeColor = isPrediction ? '#a855f7' : bodyColor;
      const fillColor   = isPrediction
        ? (isUp ? 'rgba(38, 166, 154, 0.15)' : 'rgba(239, 83, 80, 0.15)')
        : bodyColor;

      ctx.save();
      ctx.strokeStyle = strokeColor;
      ctx.fillStyle   = fillColor;
      ctx.lineWidth   = 1.5;

      // Wick: high → low, perfectly centered
      ctx.beginPath();
      ctx.moveTo(xCenter, Math.floor(highY));
      ctx.lineTo(xCenter, Math.floor(lowY));
      ctx.stroke();

      // Body: centered rect
      const bodyY = Math.min(openY, closeY);
      const bodyH = Math.max(1, Math.abs(openY - closeY));
      const bodyW = Math.floor(candleWidth);

      ctx.beginPath();
      ctx.rect(
        Math.floor(xLeft) + 0.5,
        Math.floor(bodyY) + 0.5,
        bodyW,
        Math.floor(bodyH)
      );
      if (!isPrediction) ctx.fill();
      ctx.setLineDash(isPrediction ? [4, 2] : []);
      ctx.stroke();
      ctx.setLineDash([]);

      // X-axis label (alternate dates to prevent overlap)
      if (i % 2 === 0) {
        ctx.fillStyle   = '#64748b';
        ctx.font        = '10px sans-serif';
        ctx.textAlign   = 'center';
        ctx.fillText(point.dateShort || point.date || '', xCenter, height - 2);
      }

      ctx.restore();
    });

    // ── Dashed divider: day 10 ↔ day 11 ────────────────────────────────────
    if (totalPeriods > 10) {
      const dividerX = paddingLeft + 10 * stepX + 0.5;
      ctx.save();
      ctx.strokeStyle = 'rgba(168, 85, 247, 0.4)';
      ctx.setLineDash([6, 4]);
      ctx.lineWidth   = 1;
      ctx.beginPath();
      ctx.moveTo(dividerX, paddingTop);
      ctx.lineTo(dividerX, height - paddingBottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }
  }, [prices, hasAi, histCount]);

  return (
    <div className="w-full bg-slate-900/50 px-3 py-1">
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '140px', display: 'block' }}
      />
    </div>
  );
}
