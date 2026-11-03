import { HeatmapGrid, HourlyBars, Sparkline } from "./Charts.jsx";
import { summaryIn } from "./SummaryLanguage.jsx";

const BANDS = ["Critical", "High", "Medium", "Low"];
const ARROWS = { growing: "↑ growing", fading: "↓ fading", stable: "→ stable", quiet: "· quiet" };

function minutes(value) {
  return value == null ? "—" : `${value} min`;
}

/** Live situation board: routed situations active in the last 24 h, by band. */
export function LiveBoard({ trends }) {
  return (
    <div>
      <h2>Live situations (last 24 h)</h2>
      <p>
        {BANDS.map((band) => (
          <span key={band} style={{ marginRight: "1.5em" }}>
            <strong>{band}:</strong> {trends.board[band]}
          </span>
        ))}
        <span>pending review: {trends.board.pending}</span>
      </p>
    </div>
  );
}

/** Which active situations are growing, stable or fading, plus posts per hour. */
export function TrendsPanel({ trends, lang }) {
  return (
    <div>
      <h2>Trends</h2>
      {trends.situations.length === 0 ? (
        <p>No active situations.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Trend</th>
              <th>Band</th>
              <th>Reports (last h / previous h)</th>
              <th>Priority history</th>
              <th>Situation</th>
            </tr>
          </thead>
          <tbody>
            {trends.situations.map((s) => (
              <tr key={s.id}>
                <td>{ARROWS[s.trend]}</td>
                <td>{s.band}</td>
                <td>
                  {s.reports_last_hour} / {s.reports_previous_hour}
                </td>
                <td>
                  <Sparkline values={s.priority_history} />
                </td>
                <td>{summaryIn(s, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Posts per hour (passed both gates, last 24 h)</h3>
      <HourlyBars data={trends.hourly} />
    </div>
  );
}

/** General (non-geographic) heatmaps. */
export function HeatmapsPanel({ heatmaps }) {
  const byHour = heatmaps.department_by_hour;
  const byLanguage = heatmaps.need_by_language;
  return (
    <div>
      <h2>Heatmaps (last {heatmaps.window_days} days)</h2>
      <HeatmapGrid
        caption={`Reports by department and hour of day (${byHour.reports} reports)`}
        rows={byHour.rows}
        cols={byHour.cols}
        cells={byHour.cells}
        colLabel={(h) => String(h).padStart(2, "0")}
      />
      <br />
      <HeatmapGrid
        caption="Average need score by language (reports per language in brackets)"
        rows={byLanguage.rows}
        cols={byLanguage.cols}
        cells={byLanguage.cells}
        colLabel={(c) => `${c} (${byLanguage.reports[byLanguage.cols.indexOf(c)]})`}
        format={(v) => (v == null ? "" : v.toFixed(2))}
      />
    </div>
  );
}

/** How fast departments and reviewers respond. */
export function ResponsePanel({ response }) {
  const departments = Object.entries(response.by_department);
  return (
    <div>
      <h2>Response</h2>
      <table>
        <thead>
          <tr>
            <th>Band</th>
            <th>Tickets</th>
            <th>Open</th>
            <th>Overdue (not acknowledged in time)</th>
            <th>Median to acknowledge</th>
            <th>Median to resolve</th>
            <th>Median reviewer wait</th>
          </tr>
        </thead>
        <tbody>
          {BANDS.map((band) => {
            const row = response.by_band[band];
            return (
              <tr key={band}>
                <td>
                  {band} <small>(limit {response.ack_limit_min[band]} min)</small>
                </td>
                <td>{row.tickets}</td>
                <td>{row.open}</td>
                <td>{row.overdue_unacknowledged}</td>
                <td>{minutes(row.median_ack_min)}</td>
                <td>{minutes(row.median_resolve_min)}</td>
                <td>{minutes(response.review.median_wait_min_by_band[band])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {departments.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Department</th>
              <th>Open (C / H / M / L)</th>
              <th>Overdue</th>
              <th>Median to acknowledge</th>
              <th>Median to resolve</th>
            </tr>
          </thead>
          <tbody>
            {departments.map(([dept, row]) => (
              <tr key={dept}>
                <td>{dept}</td>
                <td>{BANDS.map((b) => row.open_by_band[b]).join(" / ")}</td>
                <td>{row.overdue_unacknowledged}</td>
                <td>{minutes(row.median_ack_min)}</td>
                <td>{minutes(row.median_resolve_min)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        Waiting for review: {response.review.pending}
        {response.review.oldest_pending_min != null && ` (oldest ${response.review.oldest_pending_min} min)`} ·
        auto-routed awaiting review: {response.review.auto_routed} · decided by reviewers:{" "}
        {response.review.decided_n}
      </p>
    </div>
  );
}
