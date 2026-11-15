import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getAnalyticsSummary,
  getHeatmaps,
  getPipelineStats,
  getResponseMetrics,
  getTickets,
  getTrends,
  updateTicket,
} from "../api/client";
import {
  BandTag,
  HeatmapsPanel,
  HourlyPanel,
  LiveBoard,
  ResponsePanel,
  TrendsPanel,
} from "../components/AnalyticsPanels.jsx";
import { Meters } from "../components/Charts.jsx";
import { FilteredPanel } from "../components/FilteredPanel.jsx";
import { deptColor } from "../departments.js";

const NEXT_STATUS = { routed: ["acknowledged", "resolved"], acknowledged: ["resolved"] };
const BAND_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };
const REFRESH_MS = 10000;

function openFor(seconds) {
  const m = Math.max(0, Math.round(seconds / 60));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

function TicketRow({ t, now, ackLimitMin, busy, onAdvance }) {
  const age = now - t.created_at;
  const overdue = t.status === "routed" && ackLimitMin != null && age > ackLimitMin * 60;
  return (
    <div className={`ticket ${overdue ? "overdue" : ""}`}>
      <BandTag band={t.band} />
      <div style={{ minWidth: 0 }}>
        <p className="ticket-summary">{t.summary}</p>
        <div className="ticket-meta">
          <span>{t.status}</span>
          <span>· open {openFor(age)}</span>
          <span>· priority {t.queue_priority?.toFixed(2)}</span>
          {t.reviewer_flag === "fake" ? (
            <span className="tag tag-fake">Reviewer: possibly fake</span>
          ) : (
            !t.verified && <span className="tag tag-warn">Unverified</span>
          )}
          {overdue && <span className="tag band-critical">Overdue · limit {ackLimitMin} min</span>}
        </div>
      </div>
      <div className="ticket-actions">
        {(NEXT_STATUS[t.status] ?? []).map((next) => (
          <button
            key={next}
            type="button"
            className={`btn ${next === "acknowledged" ? "btn-primary" : "btn-ok"}`}
            disabled={busy}
            onClick={() => onAdvance(t.id, next)}
          >
            {next === "acknowledged" ? "Acknowledge" : "Resolve"}
          </button>
        ))}
      </div>
    </div>
  );
}

function eventTime(ticket, status) {
  return (ticket.history ?? []).find((e) => e.status === status)?.at ?? null;
}

function since(seconds, now) {
  const m = Math.max(0, Math.round((now - seconds) / 60));
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.floor(m / 60)} h ago`;
  return `${Math.floor(m / 1440)} d ago`;
}

/** Resolved tickets: off the live queues, kept here (collapsed) for reference. */
function ResolvedTickets({ tickets, now }) {
  const resolved = tickets
    .filter((t) => t.status === "resolved")
    .map((t) => ({ ...t, resolvedAt: eventTime(t, "resolved") ?? t.updated_at, ackAt: eventTime(t, "acknowledged") }))
    .sort((a, b) => b.resolvedAt - a.resolvedAt);
  return (
    <details className="resolved">
      <summary>
        Resolved <span className="mono muted">{resolved.length}</span>
        <span className="muted"> · off the queues, kept for reference</span>
      </summary>
      {resolved.length === 0 && <p className="empty-note">Nothing resolved yet.</p>}
      {resolved.map((t) => (
        <div className="ticket resolved-ticket" key={t.id}>
          <BandTag band={t.band} />
          <div style={{ minWidth: 0 }}>
            <p className="ticket-summary">{t.summary}</p>
            <div className="ticket-meta">
              <span className="dept-dot" style={{ background: deptColor(t.department) }} />
              <span>{t.department}</span>
              <span>· resolved {since(t.resolvedAt, now)}</span>
              {t.ackAt && <span>· acknowledged in {openFor(t.ackAt - t.created_at)}</span>}
              <span>· resolved in {openFor(t.resolvedAt - t.created_at)}</span>
              {t.reviewer_flag === "fake" && <span className="tag tag-fake">Reviewer: possibly fake</span>}
              {!t.verified && t.reviewer_flag !== "fake" && <span className="tag tag-warn">Unverified</span>}
            </div>
          </div>
          <span className="tag tag-ok">Resolved</span>
        </div>
      ))}
    </details>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [trends, setTrends] = useState(null);
  const [heatmaps, setHeatmaps] = useState(null);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([
      getAnalyticsSummary(),
      getTickets(),
      getPipelineStats(),
      getTrends(),
      getHeatmaps(),
      getResponseMetrics(),
    ])
      .then(([summaryData, ticketData, pipelineData, trendData, heatmapData, responseData]) => {
        setSummary(summaryData);
        setTickets(ticketData);
        setPipeline(pipelineData);
        setTrends(trendData);
        setHeatmaps(heatmapData);
        setResponse(responseData);
        setError(null);
        setUpdatedAt(new Date());
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  async function advance(ticketId, status) {
    setBusy(true);
    try {
      await updateTicket(ticketId, status);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const now = Date.now() / 1000;
  const openTickets = tickets
    .filter((t) => t.status === "routed" || t.status === "acknowledged")
    .sort(
      (a, b) =>
        (BAND_ORDER[a.band] ?? 9) - (BAND_ORDER[b.band] ?? 9) || (b.queue_priority ?? 0) - (a.queue_priority ?? 0)
    );
  const byDepartment = openTickets.reduce((acc, t) => {
    (acc[t.department] ??= []).push(t);
    return acc;
  }, {});

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">
            What is happening now, and how fast departments respond
            {updatedAt && <span className="muted"> · updated {updatedAt.toLocaleTimeString()}</span>}
          </p>
        </div>
        <div className="page-tools">
          <Link className="btn" to="/reports">
            Daily reports →
          </Link>
        </div>
      </div>

      {error && (
        <p className="alert" role="alert">
          Can't load the dashboard ({error}). Check that the backend is running and the database is reachable.
        </p>
      )}

      {trends && <LiveBoard trends={trends} summary={summary} />}

      <div className="grid grid-main">
        <section className="card">
          <div className="card-head">
            <div>
              <h2 className="card-title">Department queues</h2>
              <p className="card-sub">Open tickets, most urgent first</p>
            </div>
            <span className="mono muted">{openTickets.length} open</span>
          </div>
          {Object.keys(byDepartment).length === 0 && <p className="empty-note">No open tickets.</p>}
          {Object.entries(byDepartment).map(([dept, deptTickets]) => (
            <div className="dept-block" key={dept}>
              <div className="dept-head">
                <span className="dept-dot" style={{ background: deptColor(dept) }} />
                <span className="dept-name">{dept}</span>
                <span className="mono muted">{deptTickets.length}</span>
              </div>
              {deptTickets.map((t) => (
                <TicketRow
                  key={t.id}
                  t={t}
                  now={now}
                  ackLimitMin={response?.ack_limit_min?.[t.band]}
                  busy={busy}
                  onAdvance={advance}
                />
              ))}
            </div>
          ))}
          <ResolvedTickets tickets={tickets} now={now} />
        </section>

        <div className="stack">
          {summary && (
            <section className="card">
              <div className="card-head">
                <h2 className="card-title">Situations</h2>
                <span className="mono muted">{summary.total} total</span>
              </div>
              <Meters
                items={[
                  ["Pending review", summary.pending],
                  ["Confirmed", summary.confirmed],
                  ["Auto-routed", summary.auto_routed],
                  ["Flagged fake by reviewer", summary.fake],
                ]}
              />
            </section>
          )}
          {summary && Object.keys(summary.by_department).length > 0 && (
            <section className="card">
              <div className="card-head">
                <h2 className="card-title">By department</h2>
              </div>
              <Meters items={Object.entries(summary.by_department).sort((a, b) => b[1] - a[1])} />
            </section>
          )}
          {pipeline && (
            <section className="card">
              <div className="card-head">
                <h2 className="card-title">Pipeline</h2>
                <span className={`tag ${pipeline.worker_running ? "tag-ok" : "band-critical"}`}>
                  {pipeline.worker_running ? "Running" : "Stopped"}
                </span>
              </div>
              <Meters
                items={[
                  ["Queue", pipeline.queue_size],
                  ["Live clusters", pipeline.cluster_count],
                  ["Processed", pipeline.counts.received ?? 0],
                  ["Errors", pipeline.counts.error ?? 0],
                ]}
              />
              <p className="card-sub" style={{ marginTop: 10 }}>
                Models: {pipeline.model_backend}
                {pipeline.last_error && ` · last error: ${pipeline.last_error}`}
              </p>
            </section>
          )}
          <FilteredPanel refreshKey={updatedAt?.getTime()} />
        </div>
      </div>

      {trends && (
        <div className="section">
          <TrendsPanel trends={trends} />
        </div>
      )}
      {trends && (
        <div className="section">
          <HourlyPanel trends={trends} />
        </div>
      )}
      {heatmaps && <HeatmapsPanel heatmaps={heatmaps} />}
      {response && <ResponsePanel response={response} />}
    </div>
  );
}
