"""Dashboard analytics as pure functions over stored documents (no DB access),
so every number is easy to test and explain.

    response_metrics  how fast departments acknowledge / resolve, reviewer wait
    trends            live board, Growing / Stable / Fading per situation, posts per hour
    heatmaps          department x hour of day, need x language
    daily_report      the stored end-of-day situation report

Times: ticket and review timestamps are wall-clock; post times (`created_at`)
come from the posts, so trends use a simulation clock = newest post time
(replayed data then looks the same as live data). Hours of day and report days
use ANALYTICS_TZ_OFFSET_MINUTES (IST by default).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any

from ..config import ACK_LIMIT_MINUTES, ANALYTICS_TZ_OFFSET_MINUTES
from ..pipeline.routing import DEFAULT_DEPARTMENT, DEPARTMENT_BY_NEED, route_department

TZ = timezone(timedelta(minutes=ANALYTICS_TZ_OFFSET_MINUTES))
HOUR = 3600
DAY = 24 * HOUR
BANDS = ("Critical", "High", "Medium", "Low")
NEEDS = tuple(DEPARTMENT_BY_NEED)  # healthcare, municipal, law, tourism
DEPARTMENTS = (*DEPARTMENT_BY_NEED.values(), DEFAULT_DEPARTMENT)
ACTIVE_STATUSES = ("pending", "auto_routed", "confirmed")
ROUTED_STATUSES = ("auto_routed", "confirmed")
OPEN_TICKET_STATUSES = ("routed", "acknowledged")
LANGUAGE_ORDER = ("en", "hi", "kn", "ta", "te")


def _minutes(seconds: float) -> float:
    return round(seconds / 60, 1)


def _median_minutes(values: list[float]) -> float | None:
    return _minutes(median(values)) if values else None


def _band(situation: dict[str, Any]) -> str | None:
    return (situation.get("priority") or {}).get("band")


def _priority(situation: dict[str, Any]) -> float:
    return (situation.get("priority") or {}).get("priority_score") or 0.0


def local_hour(ts: float) -> int:
    return datetime.fromtimestamp(ts, TZ).hour


def local_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, TZ).date().isoformat()


def day_bounds(day: str) -> tuple[float, float]:
    d = date.fromisoformat(day)
    start = datetime(d.year, d.month, d.day, tzinfo=TZ).timestamp()
    return start, start + DAY


# ---------------------------------------------------------------------------
# Response metrics
# ---------------------------------------------------------------------------
def ticket_times(ticket: dict[str, Any]) -> dict[str, float | None]:
    """When a ticket was routed, first acknowledged (resolving counts as
    acknowledging) and resolved, from its history."""
    events = ticket.get("history") or []

    def first(status: str) -> float | None:
        return next((e["at"] for e in events if e.get("status") == status), None)

    resolved = first("resolved")
    return {
        "routed": first("routed") or ticket.get("created_at"),
        "acknowledged": first("acknowledged") or resolved,
        "resolved": resolved,
    }


def _ticket_group_stats(tickets: list[dict[str, Any]], now: float) -> dict[str, Any]:
    ack, resolve = [], []
    open_count = overdue = 0
    for ticket in tickets:
        times = ticket_times(ticket)
        routed = times["routed"]
        if routed is not None and times["acknowledged"] is not None:
            ack.append(times["acknowledged"] - routed)
        if routed is not None and times["resolved"] is not None:
            resolve.append(times["resolved"] - routed)
        if ticket.get("status") in OPEN_TICKET_STATUSES:
            open_count += 1
        limit = ACK_LIMIT_MINUTES.get(ticket.get("band") or "")
        if ticket.get("status") == "routed" and limit is not None and routed is not None and now - routed > limit * 60:
            overdue += 1
    return {
        "tickets": len(tickets),
        "open": open_count,
        "overdue_unacknowledged": overdue,
        "median_ack_min": _median_minutes(ack),
        "acknowledged_n": len(ack),
        "median_resolve_min": _median_minutes(resolve),
        "resolved_n": len(resolve),
    }


def response_metrics(tickets: list[dict], situations: list[dict], now: float) -> dict[str, Any]:
    """Department response (cancelled tickets left out) and reviewer wait."""
    live = [t for t in tickets if t.get("status") != "cancelled"]
    by_department = {}
    for department in sorted({t["department"] for t in live}):
        mine = [t for t in live if t["department"] == department]
        by_department[department] = {
            **_ticket_group_stats(mine, now),
            "open_by_band": {
                band: sum(1 for t in mine if t.get("band") == band and t.get("status") in OPEN_TICKET_STATUSES)
                for band in BANDS
            },
        }

    waits: dict[str, list[float]] = defaultdict(list)
    for s in situations:
        if s.get("decided_at") and s.get("created_at"):
            waits[_band(s) or "unknown"].append(s["decided_at"] - s["created_at"])
    pending = [s for s in situations if s.get("status") == "pending"]
    return {
        "by_band": {band: _ticket_group_stats([t for t in live if t.get("band") == band], now) for band in BANDS},
        "by_department": by_department,
        "review": {
            "median_wait_min_by_band": {band: _median_minutes(waits[band]) for band in BANDS},
            "decided_n": sum(len(v) for v in waits.values()),
            "pending": len(pending),
            "oldest_pending_min": _minutes(now - min(s["created_at"] for s in pending)) if pending else None,
            "auto_routed": sum(1 for s in situations if s.get("status") == "auto_routed"),
        },
        "cancelled_tickets": len(tickets) - len(live),
        "ack_limit_min": ACK_LIMIT_MINUTES,
    }


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
def classify_trend(last_hour: int, previous_hour: int) -> tuple[str, float | None]:
    """change = (last - previous) / max(1, previous): >= +0.2 growing,
    <= -0.2 fading, otherwise stable; no reports in either hour = quiet."""
    if last_hour == 0 and previous_hour == 0:
        return "quiet", None
    change = (last_hour - previous_hour) / max(1, previous_hour)
    if change >= 0.2:
        return "growing", round(change, 2)
    if change <= -0.2:
        return "fading", round(change, 2)
    return "stable", round(change, 2)


def trends(situations: list[dict], tweets: list[dict], clock: float, top: int = 10) -> dict[str, Any]:
    """Reports are the stored tweets of a cluster; exact reposts never reach
    them (dropped in preprocessing), near-copies still count."""
    stamps_by_cluster: dict[str, list[float]] = defaultdict(list)
    for t in tweets:
        if t.get("cluster_id") and isinstance(t.get("created_at"), (int, float)):
            stamps_by_cluster[t["cluster_id"]].append(t["created_at"])

    active = [
        s for s in situations
        if s.get("status") in ACTIVE_STATUSES and (s.get("last_report_at") or s.get("created_at") or 0) >= clock - DAY
    ]
    board = {band: 0 for band in BANDS}
    for s in active:
        if s.get("status") in ROUTED_STATUSES and _band(s) in board:
            board[_band(s)] += 1

    rows = []
    for s in sorted(active, key=_priority, reverse=True)[:top]:
        stamps = stamps_by_cluster.get(s.get("cluster_id"), [])
        last = sum(1 for ts in stamps if clock - HOUR < ts <= clock)
        previous = sum(1 for ts in stamps if clock - 2 * HOUR < ts <= clock - HOUR)
        trend, change = classify_trend(last, previous)
        rows.append({
            "id": s["id"],
            "summary": s.get("summary"),
            "summary_i18n": s.get("summary_i18n") or {},
            "status": s.get("status"),
            "band": _band(s),
            "priority": _priority(s),
            "department": s.get("department"),
            "location": s.get("location"),
            "reports_last_hour": last,
            "reports_previous_hour": previous,
            "change": change,
            "trend": trend,
            "priority_history": [h.get("priority") for h in s.get("score_history") or []],
        })

    # Posts that passed both gates per hour, oldest first; bucket i ends at clock - (23 - i) h.
    counts = [0] * 24
    for t in tweets:
        ts = t.get("created_at")
        if isinstance(ts, (int, float)) and clock - DAY < ts <= clock:
            counts[23 - int((clock - ts) // HOUR)] += 1
    hourly = [
        {"end": clock - (23 - i) * HOUR, "label": datetime.fromtimestamp(clock - (23 - i) * HOUR, TZ).strftime("%H:%M"),
         "posts": counts[i]}
        for i in range(24)
    ]
    return {
        "clock": clock,
        "board": {**board, "pending": sum(1 for s in active if s.get("status") == "pending")},
        "situations": rows,
        "hourly": hourly,
    }


# ---------------------------------------------------------------------------
# Heatmaps (general, not geographic)
# ---------------------------------------------------------------------------
def language_column(tweet: dict[str, Any]) -> str:
    if tweet.get("is_code_mixed"):
        return "code-mixed"
    lang = tweet.get("lang") or "unknown"
    return f"{lang}-rom" if tweet.get("is_romanized") and lang != "en" else lang


def heatmaps(tweets: list[dict]) -> dict[str, Any]:
    """department x hour of day: reports whose strongest need routes to that
    department (same rule as routing), by local hour posted.
    need x language: mean need probability per language column."""
    by_hour = {department: [0] * 24 for department in DEPARTMENTS}
    sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, int] = defaultdict(int)
    for t in tweets:
        if not isinstance(t.get("created_at"), (int, float)):
            continue
        needs = {k: float(v) for k, v in (t.get("needs") or {}).items() if k in NEEDS}
        department, _ = route_department(needs)
        by_hour.setdefault(department, [0] * 24)[local_hour(t["created_at"])] += 1
        column = language_column(t)
        counts[column] += 1
        for need in NEEDS:
            sums[need][column] += needs.get(need, 0.0)

    columns = [c for c in LANGUAGE_ORDER if c in counts] + sorted(c for c in counts if c not in LANGUAGE_ORDER)
    return {
        "department_by_hour": {
            "rows": list(by_hour),
            "cols": list(range(24)),
            "cells": [by_hour[d] for d in by_hour],
            "reports": sum(counts.values()),
        },
        "need_by_language": {
            "rows": list(NEEDS),
            "cols": columns,
            "cells": [[round(sums[need][c] / counts[c], 3) for c in columns] for need in NEEDS],
            "reports": [counts[c] for c in columns],
        },
    }


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------
REPORT_NOTE = (
    "Scores are decision support. Situations marked auto-routed were sent to departments "
    "without a reviewer's decision; all others were confirmed by a reviewer."
)


def _peak(situation: dict[str, Any]) -> tuple[float, str | None]:
    history = situation.get("score_history") or []
    if not history:
        return _priority(situation), _band(situation)
    best = max(history, key=lambda h: h.get("priority") or 0.0)
    return best.get("priority") or 0.0, best.get("band")


def daily_report(day: str, situations: list[dict], tickets: list[dict], generated_at: float) -> dict[str, Any]:
    """Situations active on `day` (local date, wall clock: created before its
    end and still updated after its start)."""
    start, end = day_bounds(day)

    def active(s: dict) -> bool:
        created = s.get("created_at") or 0
        return created < end and (s.get("updated_at") or created) >= start

    def decided_today(s: dict) -> bool:
        return s.get("decided_at") is not None and start <= s["decided_at"] < end

    tickets_by_situation: dict[str, list[dict]] = defaultdict(list)
    for t in tickets:
        tickets_by_situation[t["situation_id"]].append(t)

    day_situations = [s for s in situations if active(s)]
    routed = [s for s in day_situations if s.get("status") in ROUTED_STATUSES]
    entries = []
    for s in routed:
        peak_priority, peak_band = _peak(s)
        own = tickets_by_situation.get(s["id"], [])
        acks = [ticket_times(t)["acknowledged"] for t in own]
        acks = [a for a in acks if a is not None]
        entries.append({
            "id": s["id"],
            "status": s.get("status"),
            "summary": s.get("summary"),
            "summary_i18n": s.get("summary_i18n") or {},
            "location": s.get("location"),
            "languages": s.get("languages", []),
            "reports": s.get("n_reports_unique") or s.get("post_count", 0),
            "peak_priority": peak_priority,
            "peak_band": peak_band,
            "departments": [
                {"department": t["department"], "status": t.get("status"), "verified": t.get("verified", True)}
                for t in own
            ],
            # wall clock both ends: when the situation was detected -> first department acknowledgement
            "detected_to_ack_min": _minutes(min(acks) - s["created_at"]) if acks and s.get("created_at") else None,
        })
    entries.sort(key=lambda e: e["peak_priority"], reverse=True)

    departments: dict[str, dict[str, int]] = defaultdict(
        lambda: {"opened": 0, "acknowledged": 0, "resolved": 0, "cancelled": 0, "unverified": 0}
    )
    for t in tickets:
        row = departments[t["department"]]
        if start <= (t.get("created_at") or 0) < end:
            row["opened"] += 1
            row["unverified"] += 0 if t.get("verified", True) else 1
        for event in t.get("history") or []:
            if event.get("status") in ("acknowledged", "resolved", "cancelled") and start <= event["at"] < end:
                row[event["status"]] += 1
    departments = {d: row for d, row in departments.items() if any(row.values())}

    return {
        "id": day,
        "date": day,
        "utc_offset_minutes": ANALYTICS_TZ_OFFSET_MINUTES,
        "generated_at": generated_at,
        "header": {
            "confirmed_by_band": {
                band: sum(1 for s in routed if s.get("status") == "confirmed" and _band(s) == band) for band in BANDS
            },
            "auto_routed_unverified": sum(1 for s in routed if s.get("status") == "auto_routed"),
            "pending": sum(1 for s in day_situations if s.get("status") == "pending"),
            "marked_fake": sum(1 for s in situations if s.get("status") == "fake" and decided_today(s)),
            "rejected": sum(1 for s in situations if s.get("status") == "rejected" and decided_today(s)),
        },
        "situations": entries,
        "departments": dict(sorted(departments.items())),
        "note": REPORT_NOTE,
    }
