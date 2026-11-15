import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getDailyReport, getTodayReport, listDailyReports, rebuildDailyReport } from "../api/client";
import { BandTag, BANDS } from "../components/AnalyticsPanels.jsx";
import { deptColor } from "../departments.js";

/** /reports — stored daily reports, newest first, plus today's so far. */
export function ReportListPage() {
  const [reports, setReports] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    listDailyReports()
      .then(setReports)
      .catch((err) => setError(err.message))
      .finally(() => setLoaded(true));
  }, []);

  return (
    <div className="page" style={{ maxWidth: 900 }}>
      <div className="page-head">
        <div>
          <h1 className="page-title">Daily reports</h1>
          <p className="page-sub">One report per day (IST), stored automatically once the day ends.</p>
        </div>
        <div className="page-tools">
          <Link className="btn btn-primary" to="/reports/today">
            Today so far →
          </Link>
        </div>
      </div>
      {error && (
        <p className="alert" role="alert">
          Can't load reports ({error}). Check that the backend is running and the database is reachable.
        </p>
      )}
      <section className="card">
        {loaded && reports.length === 0 && !error && <p className="empty-note">No stored reports yet.</p>}
        <ul className="report-list">
          {reports.map((r) => {
            const confirmed = BANDS.reduce((n, b) => n + (r.header?.confirmed_by_band?.[b] ?? 0), 0);
            const critical = r.header?.confirmed_by_band?.Critical ?? 0;
            return (
              <li key={r.id}>
                <Link className="report-item" to={`/reports/${r.id}`}>
                  <span className="report-date">{r.id}</span>
                  <span className="report-stats">
                    {critical > 0 && <span className="tag band-critical">{critical} critical</span>}
                    <span className="tag tag-ok">{confirmed} confirmed</span>
                    <span className="tag tag-warn">{r.header?.auto_routed_unverified ?? 0} auto-routed</span>
                    <span className="tag tag-fake">{r.header?.marked_fake ?? 0} fake</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}

/** /reports/:day (or /reports/today) — one report, printable to PDF from the browser. */
export function ReportPage() {
  const { day } = useParams();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setReport(null);
    setError(null);
    (day === "today" ? getTodayReport() : getDailyReport(day))
      .then(setReport)
      .catch((err) => setError(err.message));
  }, [day]);

  async function rebuild() {
    setBusy(true);
    try {
      setReport(await rebuildDailyReport(report.date));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error)
    return (
      <div className="page" style={{ maxWidth: 900 }}>
        <p className="alert" role="alert">
          Can't load this report ({error}).
        </p>
        <Link to="/reports">← All reports</Link>
      </div>
    );
  if (!report)
    return (
      <div className="page">
        <p className="empty-note">Loading…</p>
      </div>
    );

  const { header } = report;
  const tz = `UTC+${Math.floor(report.utc_offset_minutes / 60)}:${String(report.utc_offset_minutes % 60).padStart(2, "0")}`;
  const departments = Object.entries(report.departments);

  return (
    <div className="page" style={{ maxWidth: 900 }}>
      <div className="page-head no-print">
        <Link to="/reports">← All reports</Link>
        <div className="page-tools">
          <button type="button" className="btn" onClick={rebuild} disabled={busy}>
            Rebuild
          </button>
          <button type="button" className="btn btn-primary" onClick={() => window.print()}>
            Print / save as PDF
          </button>
        </div>
      </div>

      <section className="card">
        <div className="label">Daily situation report</div>
        <h1 className="page-title" style={{ marginTop: 4 }}>
          {report.date}
        </h1>
        <p className="card-sub">
          Times in {tz} · generated {new Date(report.generated_at * 1000).toLocaleString()}
        </p>

        <div className="tiles" style={{ marginTop: 16, marginBottom: 0 }}>
          {BANDS.map((b) => (
            <div className="tile" key={b}>
              <BandTag band={b} />
              <div className="tile-num">{header.confirmed_by_band[b]}</div>
              <div className="tile-note">confirmed</div>
            </div>
          ))}
          <div className="tile">
            <span className="tag tag-warn">Unverified</span>
            <div className="tile-num">{header.auto_routed_unverified}</div>
            <div className="tile-note">auto-routed</div>
          </div>
          <div className="tile">
            <span className="tag tag-neutral">Other</span>
            <div className="tile-num">{header.pending}</div>
            <div className="tile-note">
              pending · {header.marked_fake} flagged fake
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">Situations</h2>
          <span className="mono muted">{report.situations.length}</span>
        </div>
        {report.situations.length === 0 && <p className="empty-note">No routed situations this day.</p>}
        <ol className="sit-list">
          {report.situations.map((s) => (
            <li className="sit-item" key={s.id}>
              <div className="sit-top">
                <BandTag band={s.peak_band} />
                {s.status === "auto_routed" && <span className="tag tag-warn">Auto-routed · unverified</span>}
                {s.status === "fake" && <span className="tag tag-fake">Reviewer: possibly fake · still routed</span>}
                <span className="mono muted">peak {Number(s.peak_priority).toFixed(2)}</span>
              </div>
              <p className="sit-summary">{s.summary ?? s.text}</p>
              <div className="sit-meta">
                {s.location && <>Location: {s.location} · </>}
                {s.reports} independent reports · languages: {s.languages.join(", ") || "—"} · detected →
                acknowledged: {s.detected_to_ack_min == null ? "not yet" : `${s.detected_to_ack_min} min`}
                <br />
                Departments:{" "}
                {s.departments.length === 0
                  ? "—"
                  : s.departments
                      .map((d) => `${d.department} (${d.status}${d.verified ? "" : ", unverified"})`)
                      .join(", ")}
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="card-title">Departments</h2>
        </div>
        {departments.length === 0 ? (
          <p className="empty-note">No ticket activity this day.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Department</th>
                  <th className="num">Opened</th>
                  <th className="num">Acknowledged</th>
                  <th className="num">Resolved</th>
                  <th className="num">Cancelled</th>
                  <th className="num">Unverified</th>
                </tr>
              </thead>
              <tbody>
                {departments.map(([dept, row]) => (
                  <tr key={dept}>
                    <td className="strong">
                      <span className="dept-dot" style={{ display: "inline-block", background: deptColor(dept), marginRight: 8 }} />
                      {dept}
                    </td>
                    <td className="num">{row.opened}</td>
                    <td className="num">{row.acknowledged}</td>
                    <td className="num">{row.resolved}</td>
                    <td className="num">{row.cancelled}</td>
                    <td className="num">{row.unverified}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="card-sub" style={{ marginTop: 12 }}>
          <em>{report.note}</em>
        </p>
      </section>
    </div>
  );
}
