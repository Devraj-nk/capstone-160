// Small dependency-free charts: plain SVG and tables.

/** Tiny line of a numeric series, e.g. a situation's priority history. */
export function Sparkline({ values, width = 80, height = 20 }) {
  const points = (values ?? []).filter((v) => typeof v === "number");
  if (points.length < 2) return <span>—</span>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label={`from ${points[0]} to ${points[points.length - 1]}`}>
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/** Bar per hour: [{label, posts}], oldest first. */
export function HourlyBars({ data, height = 80 }) {
  const max = Math.max(1, ...data.map((d) => d.posts));
  const barWidth = 18;
  return (
    <svg width={data.length * barWidth} height={height + 18} role="img" aria-label="posts per hour, last 24 hours">
      {data.map((d, i) => {
        const h = (d.posts / max) * height;
        return (
          <g key={d.end}>
            <title>{`${d.label}: ${d.posts} posts`}</title>
            <rect x={i * barWidth + 2} y={height - h} width={barWidth - 4} height={h} fill="steelblue" />
            {i % 3 === 0 && (
              <text x={i * barWidth} y={height + 14} fontSize="9">
                {d.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** Table heatmap: cell colour scales with value; empty cells stay white. */
export function HeatmapGrid({ rows, cols, cells, colLabel = (c) => c, format = (v) => v, caption }) {
  const max = Math.max(1e-9, ...cells.flat().filter((v) => typeof v === "number"));
  return (
    <table style={{ borderCollapse: "collapse", fontSize: "12px" }}>
      {caption && <caption style={{ textAlign: "left" }}>{caption}</caption>}
      <thead>
        <tr>
          <th />
          {cols.map((c) => (
            <th key={c} style={{ padding: "2px 4px", fontWeight: "normal" }}>
              {colLabel(c)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={row}>
            <th style={{ textAlign: "left", padding: "2px 6px", fontWeight: "normal" }}>{row}</th>
            {cols.map((c, ci) => {
              const v = cells[r][ci];
              const alpha = v ? 0.1 + 0.9 * (v / max) : 0;
              return (
                <td
                  key={c}
                  title={`${row} / ${colLabel(c)}: ${format(v)}`}
                  style={{
                    background: `rgba(200, 60, 30, ${alpha})`,
                    color: alpha > 0.6 ? "white" : "inherit",
                    textAlign: "center",
                    minWidth: "22px",
                    padding: "2px",
                    border: "1px solid #eee",
                  }}
                >
                  {v ? format(v) : ""}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
