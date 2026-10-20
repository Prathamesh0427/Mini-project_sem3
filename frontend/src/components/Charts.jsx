/** Small dependency-free SVG line chart. series: [{name, color, x:[], y:[]}] */
export default function LineChart({ series, xLabel, yLabel, height = 220, marks = [] }) {
  const W = 720, L = 46, R = 12, T = 10, B = 34;
  const xs = series.flatMap((s) => s.x), ys = series.flatMap((s) => s.y);
  if (!xs.length) return null;
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const sx = (v) => L + ((v - x0) / (x1 - x0 || 1)) * (W - L - R);
  const sy = (v) => T + (1 - (v - y0) / (y1 - y0)) * (height - T - B);
  const ticks = (a, b, n = 5) => Array.from({ length: n }, (_, i) => a + ((b - a) * i) / (n - 1));
  const fmt = (v) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(1) : v.toFixed(3));
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={`${yLabel} versus ${xLabel}`}>
        {ticks(y0, y1, 4).map((v) => (
          <g key={"y" + v}>
            <line x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} className="grid" />
            <text x={L - 6} y={sy(v) + 4} textAnchor="end" className="tick">{fmt(v)}</text>
          </g>
        ))}
        {ticks(x0, x1, 6).map((v) => (
          <text key={"x" + v} x={sx(v)} y={height - B + 16} textAnchor="middle" className="tick">{fmt(v)}</text>
        ))}
        {marks.map((m) => (
          <g key={m.label}>
            <line x1={sx(m.x)} x2={sx(m.x)} y1={T} y2={height - B} className="mark" />
            <text x={sx(m.x) + 4} y={T + 11} className="tick">{m.label}</text>
          </g>
        ))}
        {series.map((s) => (
          <polyline key={s.name} fill="none" stroke={s.color} strokeWidth="1.4" strokeLinejoin="round"
            points={s.x.map((v, i) => `${sx(v).toFixed(1)},${sy(s.y[i]).toFixed(1)}`).join(" ")} />
        ))}
        <text x={(L + W - R) / 2} y={height - 2} textAnchor="middle" className="axis">{xLabel}</text>
        <text transform={`translate(11 ${(T + height - B) / 2}) rotate(-90)`} textAnchor="middle" className="axis">{yLabel}</text>
      </svg>
      <figcaption>
        {series.map((s) => <span key={s.name} className="legend"><i style={{ background: s.color }} />{s.name}</span>)}
      </figcaption>
    </figure>
  );
}
