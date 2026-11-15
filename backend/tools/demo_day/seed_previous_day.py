"""Replay a full past day into the database, then store that day's report.

    cd backend
    python tools/demo_day/seed_previous_day.py                 # yesterday (IST)
    python tools/demo_day/seed_previous_day.py --date 2026-11-03

DEMO DATA. The posts in posts.csv are written for the demo. They run through the
real pipeline (models, clustering, scoring, routing) with the clock set to that
day, and the reviewer and department actions below are scripted, so the stored
times (decisions, tickets, auto-routing) all fall on that day:
  - some situations are backed by a reviewer within minutes,
  - one Critical is left unreviewed and gets auto-routed, then verified later,
  - the rumour is flagged fake by a reviewer (still routed, with a warning),
  - departments acknowledge (one of them late) and resolve some tickets.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import itertools
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # so .env is found
os.environ["PIPELINE_WORKER_ENABLED"] = "false"  # this script drives every step itself

IST = timezone(timedelta(hours=5, minutes=30))

# Simulated clock: starts at the moment we set and keeps running with real time,
# so anything that measures elapsed time still sees time pass.
_real_time = time.time
_clock = {"base": None, "set_at": 0.0}


def set_clock(ts: float) -> None:
    _clock["base"], _clock["set_at"] = ts, _real_time()


time.time = lambda: _real_time() if _clock["base"] is None else _clock["base"] + (_real_time() - _clock["set_at"])

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# Scripted people. Minutes are counted from when the situation appears (review)
# or from when its ticket is opened (acknowledge / resolve). None = never.
PLAN = {
    "mangaluru_landslide": {"review": ("approve", 0.5, "Confirmed with Mangaluru fire control room"), "ack": 4, "resolve": 150},
    "pune_bus_fire": {"review": ("approve", 0.8, "Matches PMPML control room report"), "ack": 6, "resolve": 90},
    "kolkata_collapse": {"review": ("approve", 45, "Verified after auto-routing; NDRF on site"), "ack": 25, "resolve": None},
    "guwahati_flood": {"review": ("approve", 0.7, "Multiple independent reports with photos"), "ack": 70, "resolve": None},
    "hyderabad_power": {"review": ("approve", 12, "TSSPDCL outage confirmed"), "ack": 30, "resolve": 200},
    "kabini_rumour": {"review": ("fake", 2, "Dam authority says no damage; copy-paste forward")},
}


def at(day: str, hhmm: str) -> float:
    return datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=IST).timestamp()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=(datetime.now(IST) - timedelta(days=1)).date().isoformat())
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000",
                        help="refuse to run while a backend is serving this database")
    args = parser.parse_args()
    day = args.date

    # A running backend shares the database and would mix its live clusters,
    # auto-routing and decisions with the replayed day. Stop it first.
    try:
        import httpx

        httpx.get(f"{args.backend_url}/health", timeout=2)
        print(f"A backend is running at {args.backend_url}. Stop it (Ctrl+C in its terminal), then run this again.")
        return 1
    except Exception:  # noqa: BLE001 - nothing listening: safe to go on
        pass

    posts = list(csv.DictReader(open(HERE / "posts.csv", encoding="utf-8")))
    seq = itertools.count()
    events: list = []

    def schedule(ts: float, kind: str, payload) -> None:
        heapq.heappush(events, (ts, next(seq), kind, payload))

    for p in posts:
        schedule(at(day, p["time_ist"]), "post", p)
    first, last = at(day, "07:30"), at(day, "23:50")
    for minute in range(int((last - first) // 60) + 1):  # the worker's escalation check, once a minute
        schedule(first + minute * 60, "tick", None)

    tag_of_post = {p["post_id"]: p["event"] for p in posts}
    situation_of_tag: dict[str, str] = {}
    review_scheduled: set[str] = set()
    ticket_scheduled: set[str] = set()
    log: list[str] = []

    def clock_str(ts: float) -> str:
        return datetime.fromtimestamp(ts, IST).strftime("%H:%M")

    with TestClient(app) as c:
        c.post("/pipeline/reset")  # replay the day on its own clusters, not today's restored ones
        if any(s for s in c.get("/situations").json() if day == datetime.fromtimestamp(s["created_at"], IST).date().isoformat()):
            print(f"{day} already has situations in the database; not seeding twice.")
            return 1

        def find_situations() -> None:
            for s in c.get("/situations").json():
                tags = {tag_of_post.get(str(t)) for t in s["tweet_ids"]} - {None}
                for tag in tags:
                    situation_of_tag.setdefault(tag, s["id"])

        def schedule_ticket_work() -> None:
            sid_to_tag = {sid: tag for tag, sid in situation_of_tag.items()}
            for t in c.get("/tickets").json():
                tag = sid_to_tag.get(t["situation_id"])
                if not tag or t["id"] in ticket_scheduled or tag not in PLAN:
                    continue
                ticket_scheduled.add(t["id"])
                plan = PLAN[tag]
                if plan.get("ack") is not None:
                    schedule(t["created_at"] + plan["ack"] * 60, "ack", (t["id"], tag))
                if plan.get("resolve") is not None:
                    schedule(t["created_at"] + plan["resolve"] * 60, "resolve", (t["id"], tag))

        stages: dict[str, int] = {}
        while events:
            ts, _, kind, payload = heapq.heappop(events)
            set_clock(ts)
            if kind == "post":
                out = c.post("/pipeline/process", json={"text": payload["text"], "created_at": ts,
                                                        "attributes": {"tweet_id": payload["post_id"]}}).json()
                stages[out["stage"]] = stages.get(out["stage"], 0) + 1
                find_situations()
                for tag, sid in situation_of_tag.items():
                    if tag in PLAN and sid not in review_scheduled:
                        review_scheduled.add(sid)
                        decision, delay, note = PLAN[tag]["review"]
                        schedule(ts + delay * 60, "review", (sid, tag, decision, note))
            elif kind == "tick":
                routed = c.post("/pipeline/escalate").json()["auto_routed"]
                for sid in routed:
                    tag = next((t for t, s in situation_of_tag.items() if s == sid), sid[:8])
                    log.append(f"{clock_str(ts)}  auto-routed (no reviewer in time): {tag}")
                if routed:
                    schedule_ticket_work()
            elif kind == "review":
                sid, tag, decision, note = payload
                r = c.post(f"/situations/{sid}/decision", json={"decision": decision, "note": note})
                if r.status_code == 200:
                    s = r.json()
                    log.append(f"{clock_str(ts)}  reviewer: {decision:<7} {tag} ({s['priority']['band']}) -> {s['status']}")
                    schedule_ticket_work()
            else:  # ack / resolve
                ticket_id, tag = payload
                status = "acknowledged" if kind == "ack" else "resolved"
                r = c.post(f"/tickets/{ticket_id}/status", json={"status": status})
                if r.status_code == 200:
                    log.append(f"{clock_str(ts)}  department {r.json()['department']}: {status} ({tag})")

        set_clock(at(day, "23:59") + 120)  # just after midnight: the day's report is stored
        report = c.post(f"/reports/daily/{day}").json()
        set_clock(_real_time())

    print(f"Seeded {day}: {len(posts)} posts -> {stages}")
    print("\n".join(sorted(log)))
    h = report["header"]
    print(f"\nStored report {day}: confirmed {h['confirmed_by_band']}, auto-routed unverified {h['auto_routed_unverified']}, "
          f"pending {h['pending']}, fake {h['marked_fake']}, rejected {h['rejected']}; {len(report['situations'])} situations listed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
