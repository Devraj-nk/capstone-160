import { HeatmapGrid, HourlyBars, Sparkline } from "./Charts.jsx";

export const BANDS = ["Critical", "High", "Medium", "Low"];
const ARROWS = { growing: "↑ Growing", fading: "↓ Fading", stable: "→ Stable", quiet: "· Quiet" };

export function BandTag({ band }) {
  return <span className={`tag band-${(band ?? "low").toLowerCase()}`}>{band ?? "?"}</span>;
}

function minutes(value) {
  return value == null ? "—" : `${value} min`;
}

/** Live situation board: routed situations active in the last 24 h, by band. */
export function LiveBoard({ trends, summary }) {
  return (
    <div className="tiles">
      {BANDS.map((band) => (
        <div className="tile" key={band}>
          <div className="tile-top">
            <BandTag band={band} />
            <span className="label">live · 24 h</span>
          </div>
          <div className="tile-num">{trends.board[band]}</div>
        </div>
      ))}
      <div className="tile">
        <div className="tile-top">
          <span className="tag tag-neutral">Review</span>
        </div>
        <div className="tile-num">{trends.board.pending}</div>
        <div className="tile-note">waiting for a reviewer</div>
      </div>
      {summary && (
        <div className="tile">
          <div className="tile-top">
            <span className="tag tag-warn">Unverified</span>
          </div>
          <div className="tile-num">{summary.auto_routed}</div>
          <div className="tile-note">auto-routed, not yet reviewed</div>
        </div>
      )}
    </div>
  );
}

/** Which active situations are growing, stable or fading. */
export function TrendsPanel({ trends }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Trends</h2>
          <p className="card-sub">Active situations — growing or fading compared with the hour before</p>
        </div>
      </div>
      {trends.situations.length === 0 ? (
        <p className="empty-note">No active situations.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Trend</th>
                <th>Band</th>
                <th>Priority</th>
                <th>Situation</th>
              </tr>
            </thead>
            <tbody>
              {trends.situations.map((s) => (
                <tr key={s.id}>
                  <td>
                    <span className={`trend trend-${s.trend}`}>{ARROWS[s.trend] ?? s.trend}</span>
                  </td>
                  <td>
                    <BandTag band={s.band} />
                  </td>
                  <td>
                    <Sparkline values={s.priority_history} />
                  </td>
                  <td className="strong col-wide">{s.summary ?? s.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function HourlyPanel({ trends }) {
  const total = trends.hourly.reduce((n, d) => n + d.posts, 0);
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Posts per hour</h2>
          <p className="card-sub">Posts that passed both filters, last 24 h · hover a bar for its count</p>
        </div>
        <span className="mono muted">{total} total</span>
      </div>
      <HourlyBars data={trends.hourly} />
    </section>
  );
}

/** General (non-geographic) heatmaps. */
export function HeatmapsPanel({ heatmaps }) {
  const byHour = heatmaps.department_by_hour;
  const byLanguage = heatmaps.need_by_language;
  return (
    <div className="grid grid-2 section">
      <section className="card">
        <div className="card-head">
          <div>
            <h2 className="card-title">Department × hour of day</h2>
            <p className="card-sub">
              {byHour.reports} reports, last {heatmaps.window_days} days (IST)
            </p>
          </div>
        </div>
        <HeatmapGrid
          rows={byHour.rows}
          cols={byHour.cols}
          cells={byHour.cells}
          colLabel={(h) => String(h).padStart(2, "0")}
          showValues={false}
          compact
        />
      </section>
      <section className="card">
        <div className="card-head">
          <div>
            <h2 className="card-title">Need × language</h2>
            <p className="card-sub">Average need score; reports per language in brackets</p>
          </div>
        </div>
        <HeatmapGrid
          rows={byLanguage.rows}
          cols={byLanguage.cols}
          cells={byLanguage.cells}
          colLabel={(c) => `${c} (${byLanguage.reports[byLanguage.cols.indexOf(c)]})`}
          format={(v) => (v == null ? "" : v.toFixed(2))}
        />
      </section>
    </div>
  );
}

/** How fast departments and reviewers respond. */
export function ResponsePanel({ response }) {
  const departments = Object.entries(response.by_department);
  const review = response.review;
  return (
    <section className="card section">
      <div className="card-head">
        <div>
          <h2 className="card-title">Response times</h2>
          <p className="card-sub">
            Waiting for review: {review.pending}
            {review.oldest_pending_min != null && ` (oldest ${review.oldest_pending_min} min)`} · auto-routed awaiting
            review: {review.auto_routed} · decided by reviewers: {review.decided_n}
          </p>
        </div>
      </div>
      <div className="grid grid-2">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Band</th>
                <th className="num">Tickets</th>
                <th className="num">Open</th>
                <th className="num">Overdue</th>
                <th className="num">To ack</th>
                <th className="num">To resolve</th>
                <th className="num">Review wait</th>
              </tr>
            </thead>
            <tbody>
              {BANDS.map((band) => {
                const row = response.by_band[band];
                return (
                  <tr key={band}>
                    <td>
                      <BandTag band={band} /> <span className="muted">≤{response.ack_limit_min[band]} min</span>
                    </td>
                    <td className="num">{row.tickets}</td>
                    <td className="num">{row.open}</td>
                    <td className="num" style={row.overdue_unacknowledged ? { color: "var(--critical)" } : undefined}>
                      {row.overdue_unacknowledged}
                    </td>
                    <td className="num">{minutes(row.median_ack_min)}</td>
                    <td className="num">{minutes(row.median_resolve_min)}</td>
                    <td className="num">{minutes(review.median_wait_min_by_band[band])}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="table-wrap">
          {departments.length === 0 ? (
            <p className="empty-note">No department tickets yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Department</th>
                  <th className="num">Open C/H/M/L</th>
                  <th className="num">Overdue</th>
                  <th className="num">To ack</th>
                  <th className="num">To resolve</th>
                </tr>
              </thead>
              <tbody>
                {departments.map(([dept, row]) => (
                  <tr key={dept}>
                    <td className="strong">{dept}</td>
                    <td className="num">{BANDS.map((b) => row.open_by_band[b]).join(" / ")}</td>
                    <td className="num" style={row.overdue_unacknowledged ? { color: "var(--critical)" } : undefined}>
                      {row.overdue_unacknowledged}
                    </td>
                    <td className="num">{minutes(row.median_ack_min)}</td>
                    <td className="num">{minutes(row.median_resolve_min)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <p className="card-sub" style={{ marginTop: 10 }}>
        Medians in minutes. Overdue = not acknowledged within the band's limit.
      </p>
    </section>
  );
}
