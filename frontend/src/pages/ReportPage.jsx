import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getDailyReport, getTodayReport, listDailyReports, rebuildDailyReport } from "../api/client";
import { SummaryLanguageSelect, summaryIn, useSummaryLanguage } from "../components/SummaryLanguage.jsx";

const BANDS = ["Critical", "High", "Medium", "Low"];
const PRINT_CSS = "@media print { nav, .no-print { display: none !important; } }";

/** /reports — stored daily reports, newest first, plus today's so far. */
export function ReportListPage() {
  const [reports, setReports] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    listDailyReports()
      .then(setReports)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section>
      <h1>Daily situation reports</h1>
      <p>
        <Link to="/reports/today">Today so far</Link> · a day's report is stored automatically once the day ends.
      </p>
      {error && <p role="alert">Failed to load: {error}</p>}
      {reports.length === 0 && !error && <p>No stored reports yet.</p>}
      <ul>
        {reports.map((r) => {
          const confirmed = BANDS.reduce((n, b) => n + (r.header?.confirmed_by_band?.[b] ?? 0), 0);
          return (
            <li key={r.id}>
              <Link to={`/reports/${r.id}`}>{r.id}</Link> — {confirmed} confirmed,{" "}
              {r.header?.auto_routed_unverified ?? 0} auto-routed, {r.header?.marked_fake ?? 0} marked fake
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** /reports/:day (or /reports/today) — one report, printable to PDF from the browser. */
export function ReportPage() {
  const { day } = useParams();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [lang, setLang] = useSummaryLanguage();

  useEffect(() => {
    setReport(null);
    (day === "today" ? getTodayReport() : getDailyReport(day))
      .then(setReport)
      .catch((err) => setError(err.message));
  }, [day]);

  async function rebuild() {
    try {
      setReport(await rebuildDailyReport(report.date));
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <p role="alert">Failed to load: {error}</p>;
  if (!report) return <p>Loading…</p>;
  const { header } = report;
  const tz = `UTC+${Math.floor(report.utc_offset_minutes / 60)}:${String(report.utc_offset_minutes % 60).padStart(2, "0")}`;

  return (
    <section>
      <style>{PRINT_CSS}</style>
      <div className="no-print">
        <Link to="/reports">All reports</Link> · <button onClick={() => window.print()}>Print / save as PDF</button>{" "}
        <button onClick={rebuild}>Rebuild</button> <SummaryLanguageSelect value={lang} onChange={setLang} />
      </div>
      <h1>Daily situation report — {report.date}</h1>
      <p>
        <small>
          Times in {tz} · generated {new Date(report.generated_at * 1000).toLocaleString()}
        </small>
      </p>

      <h2>Overview</h2>
      <p>
        Confirmed: {BANDS.map((b) => `${b} ${header.confirmed_by_band[b]}`).join(" · ")}
        <br />
        Auto-routed (no reviewer yet): {header.auto_routed_unverified} · still pending: {header.pending} · marked fake:{" "}
        {header.marked_fake} · rejected: {header.rejected}
      </p>

      <h2>Situations</h2>
      {report.situations.length === 0 && <p>No routed situations this day.</p>}
      <ol>
        {report.situations.map((s) => (
          <li key={s.id} style={{ marginBottom: "0.75em" }}>
            <strong>
              [{s.peak_band}] {s.status === "auto_routed" && "AUTO-ROUTED, UNVERIFIED · "}
            </strong>
            {summaryIn(s, lang)}
            <br />
            <small>
              {s.location ? `Location: ${s.location} · ` : ""}
              {s.reports} independent reports · languages: {s.languages.join(", ") || "—"} · peak priority{" "}
              {s.peak_priority} · detected → acknowledged:{" "}
              {s.detected_to_ack_min == null ? "not yet" : `${s.detected_to_ack_min} min`}
              <br />
              Departments:{" "}
              {s.departments.length === 0
                ? "—"
                : s.departments
                    .map((d) => `${d.department} (${d.status}${d.verified ? "" : ", unverified"})`)
                    .join(", ")}
            </small>
          </li>
        ))}
      </ol>

      <h2>Departments</h2>
      {Object.keys(report.departments).length === 0 ? (
        <p>No ticket activity this day.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Department</th>
              <th>Opened</th>
              <th>Acknowledged</th>
              <th>Resolved</th>
              <th>Cancelled</th>
              <th>Unverified</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(report.departments).map(([dept, row]) => (
              <tr key={dept}>
                <td>{dept}</td>
                <td>{row.opened}</td>
                <td>{row.acknowledged}</td>
                <td>{row.resolved}</td>
                <td>{row.cancelled}</td>
                <td>{row.unverified}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        <em>{report.note}</em>
      </p>
    </section>
  );
}
