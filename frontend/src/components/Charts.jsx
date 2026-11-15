// Small dependency-free charts: plain SVG and tables, styled by theme.css.

/** Tiny line of a numeric series, e.g. a situation's priority history. */
export function Sparkline({ values, width = 90, height = 22 }) {
  const points = (values ?? []).filter((v) => typeof v === "number");
  if (points.length < 2) return <span className="muted">—</span>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const y = (v) => (height - 3 - ((v - min) / span) * (height - 6)).toFixed(1);
  const path = points.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${y(v)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <svg className="spark" width={width} height={height} role="img" aria-label={`priority from ${points[0]} to ${last}`}>
      <title>{`priority ${points.map((v) => v.toFixed(2)).join(" → ")}`}</title>
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={y(last)} r="2.5" fill="currentColor" />
    </svg>
  );
}

/** Bar per hour: [{label, posts, end}], oldest first. Stretches to its container width. */
export function HourlyBars({ data }) {
  const max = Math.max(1, ...data.map((d) => d.posts));
  const total = data.reduce((n, d) => n + d.posts, 0);
  return (
    <div className="hbars" role="img" aria-label={`posts per hour over the last 24 hours, ${total} in total, peak ${max}`}>
      <div className="hbars-max mono">{max}</div>
      <div className="hbars-plot">
        {data.map((d) => (
          <div className="hbars-col" key={d.end} title={`${d.label} — ${d.posts} post${d.posts === 1 ? "" : "s"}`}>
            {d.posts > 0 && <div className="hbars-bar" style={{ height: `${Math.max(2, (d.posts / max) * 100)}%` }} />}
          </div>
        ))}
      </div>
      <div className="hbars-axis mono">
        {data.map((d, i) => (
          <span key={d.end}>{i % 3 === 0 ? d.label : ""}</span>
        ))}
      </div>
    </div>
  );
}

// Sequential ramp: one hue, light -> dark.
const RAMP_LOW = [233, 241, 249];
const RAMP_HIGH = [31, 95, 150];

function rampColor(t) {
  const c = RAMP_LOW.map((lo, i) => Math.round(lo + (RAMP_HIGH[i] - lo) * t));
  return `rgb(${c.join(",")})`;
}

/** Table heatmap: darker = higher; empty cells stay blank. */
export function HeatmapGrid({
  rows,
  cols,
  cells,
  colLabel = (c) => c,
  format = (v) => v,
  caption,
  showValues = true,
  compact = false,
}) {
  const max = Math.max(1e-9, ...cells.flat().filter((v) => typeof v === "number"));
  return (
    <div className="table-wrap">
      <table className={`heatmap ${compact ? "heatmap-compact" : ""}`}>
        {caption && <caption className="card-sub" style={{ textAlign: "left", marginBottom: 6 }}>{caption}</caption>}
        <thead>
          <tr>
            <th />
            {cols.map((c, ci) => (
              <th key={c}>{!compact || ci % 3 === 0 ? colLabel(c) : ""}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={row}>
              <th className="row-head" scope="row">
                {row}
              </th>
              {cols.map((c, ci) => {
                const v = cells[r][ci];
                const t = v ? 0.12 + 0.88 * (v / max) : 0;
                return (
                  <td
                    key={c}
                    title={`${row} · ${colLabel(c)}: ${v ? format(v) : "none"}`}
                    style={{
                      background: v ? rampColor(t) : "var(--bg)",
                      color: t > 0.55 ? "#fff" : "var(--text-dim)",
                    }}
                  >
                    {v && showValues ? format(v) : ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="heatmap-legend">
        <span>low</span>
        <span className="ramp" style={{ background: `linear-gradient(90deg, ${rampColor(0.12)}, ${rampColor(1)})` }} />
        <span>high ({format(max)})</span>
      </div>
    </div>
  );
}

/** Horizontal bars for a few labelled counts (one series, so no legend). */
export function Meters({ items, color }) {
  const max = Math.max(1, ...items.map(([, v]) => v));
  return (
    <div>
      {items.map(([label, value]) => (
        <div className="meter-row" key={label} title={`${label}: ${value}`}>
          <span className="meter-label">{label}</span>
          <span className="meter-track">
            <span className="meter-fill" style={{ display: "block", width: `${(value / max) * 100}%`, background: color }} />
          </span>
          <span className="meter-val">{value}</span>
        </div>
      ))}
    </div>
  );
}
