import { useEffect, useState } from "react";
import { decideSituation, getPendingSituations } from "../api/client";
import { SummaryLanguageSelect, summaryIn, useSummaryLanguage } from "../components/SummaryLanguage.jsx";

function pct(value) {
  return value == null ? "n/a" : `${Math.round(value * 100)}%`;
}

export default function ReviewPage() {
  const [situations, setSituations] = useState([]);
  const [notes, setNotes] = useState({});
  const [error, setError] = useState(null);
  const [lang, setLang] = useSummaryLanguage();

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
    // New posts keep arriving through the pipeline worker.
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  async function handleDecision(id, decision) {
    try {
      await decideSituation(id, decision, notes[id]);
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <h1>Human Review Interface</h1>
      <p>Confirm or reject AI-generated situations before they're routed to a department.</p>
      <SummaryLanguageSelect value={lang} onChange={setLang} />
      {error && <p role="alert">Failed to load: {error}</p>}
      {situations.length === 0 && !error && <p>No pending situations.</p>}
      <ul>
        {situations.map((s) => (
          <li key={s.id}>
            <h3>
              [{s.priority?.band ?? "?"}] {s.department ?? "unassigned"} — priority{" "}
              {s.priority?.priority_score ?? "n/a"}
            </h3>
            {s.status === "auto_routed" && (
              <p role="status">
                <strong>Auto-routed to {s.routed_to}</strong> — no reviewer decided in time. Please verify: approve
                to confirm, or reject / mark fake to cancel the department tickets.
              </p>
            )}
            <p>{summaryIn(s, lang)}</p>
            <p>
              {s.post_count} posts · languages: {(s.languages ?? []).join(", ") || s.language || "n/a"} ·
              fake risk: {pct(s.fake_news?.fake_score)}
              {s.fake_news?.likely_fake && <strong> (likely fake)</strong>} · credibility:{" "}
              {pct(s.fake_news?.credibility)}
            </p>
            {s.representative?.text && (
              <blockquote>
                [{s.representative.lang}] {s.representative.text}
                {s.representative.text_en && s.representative.text_en !== s.representative.text && (
                  <div>
                    <small>EN: {s.representative.text_en}</small>
                  </div>
                )}
              </blockquote>
            )}
            <details>
              <summary>Evidence ({s.evidence_posts?.length ?? 0})</summary>
              <ol>
                {(s.evidence_posts ?? []).map((e) => (
                  <li key={e.post_id}>
                    [{e.lang ?? "?"}] {e.text}
                    {e.text_en && e.text_en !== e.text && <small> (EN: {e.text_en})</small>}{" "}
                    <small>
                      score {e.score ?? "n/a"}
                      {e.why?.length > 0 && ` · ${e.why.join(", ")}`}
                    </small>
                  </li>
                ))}
              </ol>
            </details>
            <input
              placeholder="Reviewer note (optional)"
              value={notes[s.id] ?? ""}
              onChange={(e) => setNotes({ ...notes, [s.id]: e.target.value })}
            />
            <button onClick={() => handleDecision(s.id, "approve")}>Approve &amp; route</button>
            <button onClick={() => handleDecision(s.id, "reject")}>Reject</button>
            <button onClick={() => handleDecision(s.id, "fake")}>Mark fake</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
