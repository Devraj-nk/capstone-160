import { useEffect, useState } from "react";
import { getAnalyticsSummary, getConfirmedSituations } from "../api/client";

export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [situations, setSituations] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([getAnalyticsSummary(), getConfirmedSituations()])
      .then(([summaryData, situationsData]) => {
        setSummary(summaryData);
        setSituations(situationsData);
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section>
      <h1>Situation Routing Dashboard</h1>
      <p>Trends, heatmaps, and daily reports across confirmed situations.</p>
      {error && <p role="alert">Failed to load: {error}</p>}
      {summary && (
        <ul>
          <li>Total: {summary.total}</li>
          <li>Pending: {summary.pending}</li>
          <li>Confirmed: {summary.confirmed}</li>
          <li>Rejected: {summary.rejected}</li>
        </ul>
      )}
      <h2>Confirmed situations</h2>
      <ul>
        {situations.map((s) => (
          <li key={s.id}>
            {s.department ?? "unassigned"} — {s.summary ?? s.text}
          </li>
        ))}
      </ul>
    </section>
  );
}
