import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { decideSituation, getPendingSituations } from "../api/client";
import { DEPT_COLOR } from "../departments.js";
import "./ReviewConsole.css";

// Review console: live version of christananda's design (human_reveiw_console.html),
// fed by the pending / auto-routed situations from the backend.

const BAND_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 };
const NEED_LABELS = { healthcare: "Healthcare", municipal: "Public Municipal", law: "Law & Order", tourism: "Tourism" };
const UNSURE_NEED = 0.3; // below its routing threshold but worth showing as "not sure yet"
const REFRESH_MS = 10000;

function band(s) {
  return s.priority?.band ?? "Low";
}

function pct(value) {
  return value == null ? "n/a" : `${Math.round(value * 100)}%`;
}

function ago(seconds, now) {
  if (!seconds) return "";
  const s = Math.max(0, Math.round(now - seconds));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function clock(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function signalColor(value) {
  if (value == null) return "var(--low)";
  if (value >= 0.7) return "var(--verified)";
  if (value >= 0.4) return "var(--high)";
  return "var(--fake)";
}

function SignalRow({ label, value, display }) {
  const width = value == null ? 0 : Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className="rc-signal">
      <div className="rc-signal-label">{label}</div>
      <div className="rc-track">
        <div className="rc-fill" style={{ width: `${width}%`, background: signalColor(value) }} />
      </div>
      <div className="rc-signal-val">{display ?? pct(value)}</div>
    </div>
  );
}

function needFlags(needs) {
  const active = needs?.active ?? [];
  return Object.entries(NEED_LABELS)
    .map(([key, label]) => ({ key, label, value: needs?.[key], sure: active.includes(key) }))
    .filter((n) => typeof n.value === "number" && (n.sure || n.value >= UNSURE_NEED))
    .sort((a, b) => b.value - a.value);
}

function QueueCard({ s, active, now, onSelect }) {
  const b = band(s);
  const dept = s.routed_to ?? s.department ?? "Unassigned";
  return (
    <li>
      <button type="button" className={`rc-qcard ${active ? "active" : ""}`} onClick={() => onSelect(s.id)}>
        <div className="rc-qcard-top">
          <span className={`rc-tag rc-band-${b.toLowerCase()}`}>{b}</span>
          <span className="rc-qcard-time">{ago(s.last_report_at ?? s.updated_at ?? s.created_at, now)}</span>
        </div>
        <div className="rc-qcard-title">{s.representative?.text_en || s.representative?.text || s.text}</div>
        <div className="rc-qcard-meta">
          <span className="rc-dept-dot" style={{ background: DEPT_COLOR[dept] ?? "var(--low)" }} />
          <span className="rc-qcard-dept">
            {dept} · {s.post_count} posts
          </span>
          {s.status === "auto_routed" && <span className="rc-auto-chip">Auto-routed</span>}
        </div>
      </button>
    </li>
  );
}

function SentimentTag({ label, negativity }) {
  if (!label) return null;
  const strength = negativity == null ? null : label === "negative" ? negativity : 1 - negativity;
  return (
    <span className={`rc-sent rc-sent-${label}`} title="Sentiment model output">
      {label}
      {strength != null && ` ${Math.round(strength * 100)}%`}
    </span>
  );
}

function ReviewPane({ s, now, openedAt, note, setNote, busy, onDecide }) {
  const b = band(s);
  const fake = s.fake_news ?? {};
  const pr = s.priority ?? {};
  const rep = s.representative ?? {};
  const flags = needFlags(s.needs);
  const evidence = s.evidence_posts ?? [];
  const dueIn = s.status === "pending" && s.escalation_due_at ? s.escalation_due_at - now : null;

  return (
    <div className="rc-review-inner">
      <div className="rc-rv-header">
        <div className="rc-rv-header-left">
          <span className={`rc-tag rc-badge-lg rc-band-${b.toLowerCase()}`}>
            {b} priority · {pr.priority_score?.toFixed(2) ?? "n/a"}
          </span>
          <span className="rc-id">
            {s.department ?? "Unassigned"} · {s.id.slice(0, 8)}
          </span>
          {b === "Critical" && <span className="rc-fastpath">⚡ Top of the queue — urgent</span>}
        </div>
        <div className="rc-timer">
          Time on this
          <br />
          <span className="val">{clock(now - openedAt)}</span>
        </div>
      </div>

      {s.status === "auto_routed" && (
        <p className="rc-banner" role="status">
          <strong>Already sent to {s.routed_to}</strong> because no reviewer decided in time. Mark it Real to back it
          up, or Looks fake to warn the department. It stays routed either way.
        </p>
      )}
      {dueIn != null && dueIn > 0 && (
        <p className="rc-banner" role="status">
          Urgent reports don't wait for a reviewer: this goes to <strong>{s.department}</strong> automatically in{" "}
          <strong>{clock(dueIn)}</strong>.
        </p>
      )}
      {fake.likely_fake && (
        <p className="rc-banner fake" role="status">
          <strong>Flagged as possibly fake</strong> (fake score {fake.fake_score?.toFixed(2)}). It will not be
          auto-routed — please check the posts below.
        </p>
      )}

      <h2 className="rc-title">
        {rep.text || s.text}
        {rep.text_en && rep.text_en !== rep.text && <span className="rc-title-en">EN: {rep.text_en}</span>}
      </h2>

      <section className="rc-box">
        <div className="rc-label">What's happening, in short</div>
        <p className="rc-summary">{s.summary ?? s.text}</p>
        <div className="rc-facts">
          {s.post_count} posts · {s.n_reports_unique || s.post_count} independent ·{" "}
          {(s.languages ?? []).join(", ") || s.language || "?"}
          {s.location && ` · near ${s.location}`}
        </div>
        <div className="rc-mood">
          <span className="rc-label" style={{ marginBottom: 0 }}>Overall sentiment</span>
          <SentimentTag label={s.sentiment?.label} negativity={s.sentiment?.negativity} />
          {!s.sentiment?.label && <span className="rc-ev-meta">not available</span>}
        </div>
        {flags.length > 0 && (
          <div className="rc-needs">
            {flags.map((n) => (
              <span key={n.key} className={`rc-need ${n.sure ? "" : "uncertain"}`}>
                {!n.sure && <span className="uc-dot" />}
                {n.label} · {pct(n.value)}
                {!n.sure && " · not sure yet"}
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="rc-box">
        <div className="rc-signal-head">
          <div className="rc-label">How much can we trust this?</div>
          <div className="rc-readout">
            Fake score{" "}
            <strong style={{ color: fake.likely_fake ? "var(--fake)" : "var(--verified)" }}>
              {fake.fake_score?.toFixed(2) ?? "n/a"}
            </strong>
          </div>
        </div>
        <div className="rc-signals">
          <SignalRow label="Credibility" value={fake.credibility} />
          <SignalRow label="Likely genuine" value={fake.fake_score == null ? null : 1 - fake.fake_score} />
          <SignalRow
            label="Backed up by others"
            value={pr.corroboration}
            display={`${s.n_reports_unique || s.post_count} reports`}
          />
          <SignalRow label="Severity" value={pr.severity} />
          <SignalRow label="Actionability" value={pr.actionability} />
        </div>
        <p className="rc-signal-note">Bars are the system's own scores (0–100%). Your vote backs them up; neither is the final word.</p>
      </section>

      <div className="rc-label">Posts backing this up ({evidence.length})</div>
      <div className="rc-evidence">
        {evidence.length === 0 && <p className="rc-ev-text">No evidence posts stored.</p>}
        {evidence.map((e) => (
          <article key={e.post_id} className="rc-ev">
            <div className="rc-ev-top">
              <span className="rc-ev-tags">
                <span className="rc-ev-lang">{e.lang ?? "?"}</span>
                <SentimentTag label={e.sentiment} negativity={e.negativity} />
              </span>
              {e.why?.length > 0 && <span className="rc-ev-why">{e.why.join(" · ")}</span>}
            </div>
            <p className="rc-ev-text">{e.text}</p>
            {e.text_en && e.text_en !== e.text && <p className="rc-ev-en">EN: {e.text_en}</p>}
            <div className="rc-ev-meta">evidence score {e.score?.toFixed(2) ?? "n/a"}</div>
          </article>
        ))}
      </div>

      <div className="rc-actionbar">
        <input
          className="rc-note"
          placeholder="Reviewer note (optional) — e.g. confirmed with local news"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="rc-buttons">
          <button type="button" className="rc-btn rc-btn-true" disabled={busy} onClick={() => onDecide("approve")}>
            ▲ Real <kbd>T</kbd>
          </button>
          <button type="button" className="rc-btn rc-btn-fake" disabled={busy} onClick={() => onDecide("fake")}>
            ✕ Looks fake <kbd>F</kbd>
          </button>
          <button type="button" className="rc-btn rc-btn-skip" disabled={busy} onClick={() => onDecide("skip")}>
            Skip <kbd>→</kbd>
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ReviewPage() {
  const [situations, setSituations] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [skipped, setSkipped] = useState([]); // ids moved to the back of the queue this session
  const [notes, setNotes] = useState({});
  const [reviewed, setReviewed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [openedAt, setOpenedAt] = useState(() => Date.now() / 1000);
  const toastTimer = useRef(null);

  const load = useCallback(async () => {
    try {
      setSituations(await getPendingSituations());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    load();
    // New posts keep arriving through the pipeline worker.
    const refresh = setInterval(load, REFRESH_MS);
    const tick = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      clearInterval(refresh);
      clearInterval(tick);
      clearTimeout(toastTimer.current);
    };
  }, [load]);

  // Most urgent first; within a band, highest priority score; skipped ones last.
  const queue = useMemo(() => {
    const rank = (s) => (skipped.includes(s.id) ? 1 + skipped.indexOf(s.id) : 0);
    return [...situations].sort(
      (a, b) =>
        rank(a) - rank(b) ||
        (BAND_ORDER[band(a)] ?? 9) - (BAND_ORDER[band(b)] ?? 9) ||
        (b.priority?.priority_score ?? 0) - (a.priority?.priority_score ?? 0)
    );
  }, [situations, skipped]);

  // Keep the current selection across refreshes; fall back to the top of the queue.
  const active = queue.find((s) => s.id === activeId) ?? queue[0] ?? null;
  useEffect(() => {
    if (active && active.id !== activeId) {
      setActiveId(active.id);
      setOpenedAt(Date.now() / 1000);
    }
  }, [active, activeId]);

  function select(id) {
    setActiveId(id);
    setOpenedAt(Date.now() / 1000);
  }

  function showToast(text, color) {
    setToast({ text, color });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2200);
  }

  const decide = useCallback(
    async (action) => {
      if (!active || busy) return;
      const next = queue.find((s) => s.id !== active.id);
      if (action === "skip") {
        setSkipped((prev) => [...prev.filter((id) => id !== active.id), active.id]);
        showToast("Okay, we'll come back to this one", "var(--text-faint)");
        if (next) select(next.id);
        return;
      }
      setBusy(true);
      try {
        const updated = await decideSituation(active.id, action, notes[active.id]);
        setReviewed((n) => n + 1);
        setSituations((prev) => prev.filter((s) => s.id !== active.id));
        if (next) select(next.id);
        if (action === "approve") showToast(`Backed as real — sent to ${updated.routed_to ?? active.department}`, "var(--verified)");
        else showToast(`Flagged as possibly fake — still sent to ${updated.routed_to ?? active.department}, with a warning`, "var(--fake)");
      } catch (err) {
        showToast(`Could not save: ${err.message}`, "var(--critical)");
      } finally {
        setBusy(false);
      }
    },
    [active, busy, queue, notes]
  );

  useEffect(() => {
    function onKey(e) {
      const tag = e.target?.tagName;
      if (e.ctrlKey || e.metaKey || e.altKey || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const action = { t: "approve", f: "fake", ArrowRight: "skip" }[
        e.key.length === 1 ? e.key.toLowerCase() : e.key
      ];
      if (action) {
        e.preventDefault();
        decide(action);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [decide]);

  const urgent = situations.filter((s) => band(s) === "Critical").length;

  return (
    <div className="rc">
      <header className="rc-topbar">
        <div className="rc-brand">
          <div className="rc-brand-mark" />
          <div>
            <div className="rc-brand-text">Review Console</div>
            <div className="rc-brand-sub">Back up what's real — urgent reports go out even without a reviewer</div>
          </div>
        </div>
        <div className="rc-topbar-right">
          <div className="rc-stat">
            <span className="num">{situations.length}</span>
            <span className="lbl">Waiting</span>
          </div>
          <div className="rc-stat">
            <span className="num" style={{ color: "var(--critical)" }}>
              {urgent}
            </span>
            <span className="lbl">Critical</span>
          </div>
          <div className="rc-stat">
            <span className="num">{reviewed}</span>
            <span className="lbl">You've reviewed</span>
          </div>
        </div>
      </header>

      {error && (
        <p className="rc-alert" role="alert">
          Can't load the review queue ({error}). Check that the backend is running and the database is reachable.
        </p>
      )}

      <div className="rc-main">
        <aside className="rc-queue">
          <div className="rc-queue-head">
            <h2>What needs review</h2>
            <p>Most urgent first · T real · F fake · → skip</p>
          </div>
          <ul className="rc-queue-list">
            {queue.map((s) => (
              <QueueCard key={s.id} s={s} active={active?.id === s.id} now={now} onSelect={select} />
            ))}
          </ul>
        </aside>

        <main className="rc-review">
          {active ? (
            <ReviewPane
              s={active}
              now={now}
              openedAt={openedAt}
              note={notes[active.id] ?? ""}
              setNote={(value) => setNotes((prev) => ({ ...prev, [active.id]: value }))}
              busy={busy}
              onDecide={decide}
            />
          ) : (
            <div className="rc-empty">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 12l2 2 4-4M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9 9 4.03 9 9z" />
              </svg>
              <div>{!loaded ? "Loading…" : error ? "Queue unavailable." : "All caught up — nothing waiting for review."}</div>
            </div>
          )}
        </main>
      </div>

      {toast && (
        <div className="rc-toast" role="status">
          <span className="rc-toast-dot" style={{ background: toast.color }} />
          {toast.text}
        </div>
      )}
    </div>
  );
}
