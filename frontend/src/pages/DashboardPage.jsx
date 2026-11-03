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
import { HeatmapsPanel, LiveBoard, ResponsePanel, TrendsPanel } from "../components/AnalyticsPanels.jsx";
import { SummaryLanguageSelect, summaryIn, useSummaryLanguage } from "../components/SummaryLanguage.jsx";

const NEXT_STATUS = { routed: ["acknowledged", "resolved"], acknowledged: ["resolved"] };

export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [trends, setTrends] = useState(null);
  const [heatmaps, setHeatmaps] = useState(null);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [lang, setLang] = useSummaryLanguage();

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
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [load]);

  async function advance(ticketId, status) {
    try {
      await updateTicket(ticketId, status);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const openTickets = tickets.filter((t) => t.status === "routed" || t.status === "acknowledged");
  const byDepartment = openTickets.reduce((acc, t) => {
    (acc[t.department] ??= []).push(t);
    return acc;
  }, {});

  return (
    <section>
      <h1>Situation Routing Dashboard</h1>
      <p>
        Trends, heatmaps and response times across situations · <Link to="/reports">Daily reports</Link>
      </p>
      <SummaryLanguageSelect value={lang} onChange={setLang} />
      {error && <p role="alert">Failed to load: {error}</p>}
      {trends && <LiveBoard trends={trends} />}
      {summary && (
        <ul>
          <li>Total: {summary.total}</li>
          <li>Pending: {summary.pending}</li>
          <li>Confirmed: {summary.confirmed}</li>
          <li>Rejected: {summary.rejected}</li>
          <li>Marked fake: {summary.fake}</li>
          <li>Auto-routed, awaiting review: {summary.auto_routed}</li>
        </ul>
      )}
      {summary && Object.keys(summary.by_department).length > 0 && (
        <>
          <h2>Situations by department</h2>
          <ul>
            {Object.entries(summary.by_department).map(([dept, count]) => (
              <li key={dept}>
                {dept}: {count}
              </li>
            ))}
          </ul>
        </>
      )}
      <h2>Department queues</h2>
      {Object.keys(byDepartment).length === 0 && <p>No open tickets.</p>}
      {Object.entries(byDepartment).map(([dept, deptTickets]) => (
        <div key={dept}>
          <h3>
            {dept} ({deptTickets.length})
          </h3>
          <ul>
            {deptTickets.map((t) => (
              <li key={t.id}>
                [{t.band ?? "?"} {t.queue_priority}] {!t.verified && <strong>UNVERIFIED </strong>}
                {summaryIn(t, lang)} — <em>{t.status}</em>{" "}
                {(NEXT_STATUS[t.status] ?? []).map((next) => (
                  <button key={next} onClick={() => advance(t.id, next)}>
                    {next === "acknowledged" ? "Acknowledge" : "Resolve"}
                  </button>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {trends && <TrendsPanel trends={trends} lang={lang} />}
      {heatmaps && <HeatmapsPanel heatmaps={heatmaps} />}
      {response && <ResponsePanel response={response} />}
      {summary && Object.keys(summary.dropped_by_reason).length > 0 && (
        <>
          <h2>Filtered before analysis (last 7 days)</h2>
          <ul>
            {Object.entries(summary.dropped_by_reason).map(([reason, count]) => (
              <li key={reason}>
                {reason}: {count}
              </li>
            ))}
          </ul>
        </>
      )}
      {pipeline && (
        <>
          <h2>Pipeline</h2>
          <p>
            models: {pipeline.model_backend} · worker: {pipeline.worker_running ? "running" : "stopped"} · queue:{" "}
            {pipeline.queue_size} · clusters: {pipeline.cluster_count} · processed since start:{" "}
            {pipeline.counts.received ?? 0} · errors: {pipeline.counts.error ?? 0}
          </p>
        </>
      )}
    </section>
  );
}
