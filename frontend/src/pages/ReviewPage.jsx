import { useEffect, useState } from "react";
import { decideSituation, getPendingSituations } from "../api/client";

export default function ReviewPage() {
  const [situations, setSituations] = useState([]);
  const [error, setError] = useState(null);

  async function load() {
    try {
      setSituations(await getPendingSituations());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDecision(id, decision) {
    await decideSituation(id, decision);
    load();
  }

  return (
    <section>
      <h1>Human Review Interface</h1>
      <p>Confirm or reject AI-generated situations before they're routed to a department.</p>
      {error && <p role="alert">Failed to load: {error}</p>}
      {situations.length === 0 && !error && <p>No pending situations.</p>}
      <ul>
        {situations.map((s) => (
          <li key={s.id}>
            <p>{s.text}</p>
            <p>
              department: {s.department ?? "unassigned"} | priority:{" "}
              {s.priority?.priority_score ?? "n/a"}
            </p>
            <button onClick={() => handleDecision(s.id, "approve")}>Approve</button>
            <button onClick={() => handleDecision(s.id, "reject")}>Reject</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
