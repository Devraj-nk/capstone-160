import { useEffect, useState } from "react";
import { getFilteredPosts } from "../api/client";

const REASONS = [
  [null, "All"],
  ["not_disaster", "Not a disaster"],
  ["repost", "Reposts"],
  ["invalid", "Invalid"],
];
const TAG = { not_disaster: ["tag-neutral", "Not a disaster"], repost: ["tag-warn", "Repost"], invalid: ["tag-fake", "Invalid"] };

function why(post) {
  const d = post.detail || {};
  if (post.reason === "not_disaster" && d.disaster_confidence != null) {
    return `disaster model ${Math.round(d.disaster_confidence * 100)}% (needs ${Math.round((d.threshold ?? 0.5) * 100)}%)`;
  }
  if (post.reason === "repost" && d.repost_count) return `copy #${d.repost_count} of an earlier post`;
  if (post.reason === "invalid") return "empty or symbols only";
  return "";
}

function ago(seconds) {
  const m = Math.max(0, Math.round((Date.now() / 1000 - seconds) / 60));
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.floor(m / 60)} h ago`;
  return `${Math.floor(m / 1440)} d ago`;
}

/** Posts removed before analysis, to show the system saw and filtered them. */
export function FilteredPanel({ refreshKey }) {
  const [reason, setReason] = useState(null);
  const [data, setData] = useState(null);

  useEffect(() => {
    getFilteredPosts(reason)
      .then(setData)
      .catch(() => setData(null));
  }, [reason, refreshKey]);

  const counts = data?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="card-title">Filtered out</h2>
          <p className="card-sub">Seen by the system but removed before analysis · last 7 days</p>
        </div>
        <span className="mono muted">{total}</span>
      </div>
      <div className="filter-tabs" role="tablist">
        {REASONS.filter(([key]) => key === null || counts[key]).map(([key, label]) => (
          <button
            key={label}
            type="button"
            role="tab"
            aria-selected={reason === key}
            className={`filter-tab ${reason === key ? "active" : ""}`}
            onClick={() => setReason(key)}
          >
            {label} <span className="mono">{key ? counts[key] ?? 0 : total}</span>
          </button>
        ))}
      </div>
      {data && data.posts.length === 0 && <p className="empty-note">Nothing filtered yet.</p>}
      <ul className="filtered-list">
        {(data?.posts ?? []).map((p) => {
          const [cls, label] = TAG[p.reason] ?? ["tag-neutral", p.reason];
          return (
            <li key={p.id} className="filtered-item">
              <div className="filtered-top">
                <span className={`tag ${cls}`}>{label}</span>
                {p.detail?.lang && <span className="mono muted">{p.detail.lang}</span>}
                <span className="mono muted" style={{ marginLeft: "auto" }}>
                  {ago(p.dropped_at)}
                </span>
              </div>
              <p className="filtered-text">{p.text}</p>
              <div className="filtered-why">{why(p)}</div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
