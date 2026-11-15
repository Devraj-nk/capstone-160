"""Analytics dashboard: response metrics, trends, heatmaps, daily report."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.analysis import clustering, need_detection
from app.analytics import metrics, service
from app.analytics.metrics import TZ, classify_trend, day_bounds
from app.db import find_documents, insert_document
from app.main import app

client = TestClient(app)

HOUR = 3600
CLOCK = datetime(2026, 11, 3, 12, 0, tzinfo=TZ).timestamp()  # 12:00 IST


def at_ist(hour: int, minute: int = 0, day: int = 3) -> float:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ).timestamp()


# --- trends -----------------------------------------------------------------


@pytest.mark.parametrize(
    "last, previous, expected",
    [(5, 2, ("growing", 1.5)), (2, 5, ("fading", -0.6)), (5, 5, ("stable", 0.0)),
     (0, 0, ("quiet", None)), (1, 0, ("growing", 1.0)), (6, 5, ("growing", 0.2))],
)
def test_classify_trend(last, previous, expected):
    assert classify_trend(last, previous) == expected


def _situation(sid, cluster, status, band, priority, last_report_at, history=()):
    return {
        "id": sid, "cluster_id": cluster, "status": status, "summary": f"{sid} summary",
        "priority": {"priority_score": priority, "band": band}, "department": "Public Municipal",
        "last_report_at": last_report_at, "created_at": last_report_at,
        "score_history": [{"priority": p} for p in history],
    }


def test_trends_board_arrows_and_hourly_series():
    tweets = (
        [{"cluster_id": "c1", "created_at": CLOCK - 1.5 * HOUR + i} for i in range(2)]   # previous hour
        + [{"cluster_id": "c1", "created_at": CLOCK - 0.5 * HOUR + i} for i in range(5)]  # last hour
        + [{"cluster_id": "c2", "created_at": CLOCK - 1.5 * HOUR + i} for i in range(3)]
        + [{"cluster_id": "c2", "created_at": CLOCK - 10}]
    )
    situations = [
        _situation("growing", "c1", "confirmed", "Critical", 0.8, CLOCK - 60, history=(0.6, 0.8)),
        _situation("fading", "c2", "pending", "High", 0.6, CLOCK - 10),
        _situation("rejected", "c3", "rejected", "Critical", 0.9, CLOCK - 10),
        _situation("old", "c4", "confirmed", "High", 0.7, CLOCK - 30 * HOUR),
    ]
    out = metrics.trends(situations, tweets, CLOCK)

    assert out["board"] == {"Critical": 1, "High": 0, "Medium": 0, "Low": 0, "pending": 1}
    rows = {r["id"]: r for r in out["situations"]}
    assert set(rows) == {"growing", "fading"}  # rejected and >24 h old left out
    assert (rows["growing"]["trend"], rows["growing"]["reports_last_hour"], rows["growing"]["reports_previous_hour"]) == (
        "growing", 5, 2,
    )
    assert rows["growing"]["priority_history"] == [0.6, 0.8]
    assert rows["fading"]["trend"] == "fading"
    assert [r["id"] for r in out["situations"]] == ["growing", "fading"]  # priority order

    assert len(out["hourly"]) == 24
    assert sum(h["posts"] for h in out["hourly"]) == len(tweets)
    assert out["hourly"][-1]["posts"] == 6 and out["hourly"][-2]["posts"] == 5
    assert out["hourly"][-1]["label"] == "12:00"


# --- heatmaps ---------------------------------------------------------------


def test_heatmaps_department_by_local_hour_and_need_by_language():
    tweets = [
        {"created_at": at_ist(9, 15), "lang": "en", "needs": {"municipal": 0.9, "healthcare": 0.1}},
        {"created_at": at_ist(9, 45), "lang": "en", "needs": {"municipal": 0.1, "healthcare": 0.1}},
        {"created_at": at_ist(22, 5), "lang": "kn", "is_romanized": True, "needs": {"healthcare": 0.7}},
        {"created_at": at_ist(22, 30), "lang": "hi", "is_code_mixed": True, "needs": {"law": 0.8}},
    ]
    out = metrics.heatmaps(tweets)

    grid = dict(zip(out["department_by_hour"]["rows"], out["department_by_hour"]["cells"]))
    assert grid["Public Municipal"][9] == 1
    assert grid["Disaster Management"][9] == 1  # no need above its threshold
    assert grid["Healthcare"][22] == 1 and grid["Law & Order"][22] == 1
    assert sum(sum(row) for row in grid.values()) == 4

    need = out["need_by_language"]
    assert need["cols"] == ["en", "code-mixed", "kn-rom"]
    assert need["reports"] == [2, 1, 1]
    cells = dict(zip(need["rows"], need["cells"]))
    assert cells["municipal"][0] == 0.5  # mean of 0.9 and 0.1
    assert cells["healthcare"][2] == 0.7
    assert cells["law"][1] == 0.8


# --- response metrics -------------------------------------------------------


def _ticket(tid, department, band, status, routed, **events):
    history = [{"status": "routed", "at": routed}] + [{"status": s, "at": t} for s, t in events.items()]
    return {"id": tid, "situation_id": f"s_{tid}", "department": department, "band": band, "status": status,
            "created_at": routed, "history": history, "verified": True}


def test_response_metrics_medians_overdue_and_review_wait():
    now = CLOCK
    t0 = now - 3 * HOUR
    tickets = [
        _ticket("a", "Public Municipal", "Critical", "resolved", t0, acknowledged=t0 + 300, resolved=t0 + 1800),
        _ticket("b", "Healthcare", "Critical", "acknowledged", t0, acknowledged=t0 + 900),
        _ticket("c", "Public Municipal", "High", "routed", now - 2 * HOUR),        # past the 60 min limit
        _ticket("d", "Public Municipal", "Critical", "routed", now - 5 * 60),       # within 15 min
        _ticket("e", "Healthcare", "High", "resolved", t0, resolved=t0 + 600),       # resolved without ack step
        _ticket("x", "Healthcare", "Critical", "cancelled", t0, cancelled=t0 + 60),
    ]
    situations = [
        {"id": "s1", "status": "confirmed", "priority": {"band": "Critical"}, "created_at": now - 1000, "decided_at": now - 400},
        {"id": "s2", "status": "confirmed", "priority": {"band": "Critical"}, "created_at": now - 1000, "decided_at": now - 800},
        {"id": "s3", "status": "pending", "priority": {"band": "Medium"}, "created_at": now - 1200},
        {"id": "s4", "status": "auto_routed", "priority": {"band": "Critical"}, "created_at": now - 600},
    ]
    out = metrics.response_metrics(tickets, situations, now)

    critical = out["by_band"]["Critical"]
    assert critical["tickets"] == 3  # cancelled one left out
    assert critical["median_ack_min"] == 10.0  # 5 and 15 minutes
    assert critical["median_resolve_min"] == 30.0
    assert critical["open"] == 2 and critical["overdue_unacknowledged"] == 0
    high = out["by_band"]["High"]
    assert high["overdue_unacknowledged"] == 1
    assert high["median_ack_min"] == 10.0  # resolved counts as acknowledged
    assert out["by_department"]["Public Municipal"]["open_by_band"] == {"Critical": 1, "High": 1, "Medium": 0, "Low": 0}
    assert out["cancelled_tickets"] == 1

    review = out["review"]
    assert review["median_wait_min_by_band"]["Critical"] == 6.7  # waits of 600 s and 200 s
    assert review["decided_n"] == 2
    assert review["pending"] == 1 and review["oldest_pending_min"] == 20.0
    assert review["auto_routed"] == 1


# --- daily report -----------------------------------------------------------


def test_daily_report_contents():
    day = "2026-11-02"
    start, end = day_bounds(day)
    assert end - start == 24 * HOUR
    assert datetime.fromtimestamp(start, TZ).strftime("%Y-%m-%d %H:%M") == "2026-11-02 00:00"

    in_day = start + 10 * HOUR
    situations = [
        {"id": "flood", "status": "confirmed", "summary": "Flooding reported.", "location": "Rajajinagar",
         "languages": ["en", "kn"], "n_reports_unique": 6, "priority": {"priority_score": 0.7, "band": "High"},
         "score_history": [{"priority": 0.6, "band": "High"}, {"priority": 0.8, "band": "Critical"},
                           {"priority": 0.7, "band": "High"}],
         "created_at": in_day, "updated_at": in_day + HOUR},
        {"id": "fire", "status": "auto_routed", "priority": {"priority_score": 0.9, "band": "Critical"},
         "created_at": in_day, "updated_at": in_day},
        {"id": "pending", "status": "pending", "priority": {"band": "Medium"}, "created_at": in_day},
        {"id": "rumour", "status": "fake", "priority": {"band": "High"}, "created_at": in_day, "decided_at": in_day + 60},
        {"id": "old", "status": "confirmed", "priority": {"priority_score": 0.95, "band": "Critical"},
         "created_at": start - 2 * HOUR, "updated_at": start - HOUR},
    ]
    tickets = [
        {"id": "t1", "situation_id": "flood", "department": "Public Municipal", "status": "acknowledged",
         "band": "High", "verified": True, "created_at": in_day + 100,
         "history": [{"status": "routed", "at": in_day + 100}, {"status": "acknowledged", "at": in_day + 700}]},
        {"id": "t2", "situation_id": "fire", "department": "Public Municipal", "status": "routed",
         "band": "Critical", "verified": False, "created_at": in_day + 200,
         "history": [{"status": "routed", "at": in_day + 200}]},
    ]
    report = metrics.daily_report(day, situations, tickets, generated_at=end)

    assert report["header"] == {
        "confirmed_by_band": {"Critical": 0, "High": 1, "Medium": 0, "Low": 0},
        "auto_routed_unverified": 1, "pending": 1, "marked_fake": 1, "rejected": 0,
    }
    # reviewer-flagged fakes are still routed, so they are listed too
    assert [e["id"] for e in report["situations"]] == ["fire", "flood", "rumour"]
    flood = report["situations"][1]
    assert (flood["peak_priority"], flood["peak_band"]) == (0.8, "Critical")
    assert flood["detected_to_ack_min"] == 11.7  # 700 s after detection
    assert flood["departments"] == [{"department": "Public Municipal", "status": "acknowledged", "verified": True}]
    assert report["departments"] == {
        "Public Municipal": {"opened": 2, "acknowledged": 1, "resolved": 0, "cancelled": 0, "unverified": 1},
    }
    assert "auto-routed" in report["note"]


# --- endpoints on pipeline data ---------------------------------------------


@pytest.fixture
def flood_situation(monkeypatch):
    vectors = iter([[1.0, 0.0, 0.5, 0.0], [1.0, 0.0, 0.0, 0.5], [1.0, 0.0, -0.5, 0.0]])
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: next(vectors))
    monkeypatch.setattr(need_detection, "_predict_need_probs",
                        lambda text: {"healthcare": 0.05, "municipal": 0.92, "tourism": 0.01, "law": 0.02})
    texts = ["Flood near Rajajinagar, water entering houses", "Rajajinagar flooded, need help",
             "Water rising at Rajajinagar, send boats"]
    for i, text in enumerate(texts):
        out = client.post("/pipeline/process", json={
            "text": text, "created_at": CLOCK - (len(texts) - i) * 600, "attributes": {"tweet_id": f"f{i}"},
        }).json()
    return out["situation_id"]


def test_situation_carries_analytics_fields(flood_situation):
    situation = client.get(f"/situations/{flood_situation}").json()
    assert situation["location"] == "Rajajinagar"
    assert situation["n_reports_unique"] == 3
    assert situation["first_report_at"] == CLOCK - 1800 and situation["last_report_at"] == CLOCK - 600
    assert situation["score_history"][-1]["n_unique"] == 3


def test_analytics_endpoints(flood_situation):
    trends = client.get("/analytics/trends").json()
    assert trends["clock"] == CLOCK - 600  # newest post, not the wall clock
    assert trends["board"]["pending"] == 1
    assert trends["situations"][0]["id"] == flood_situation
    assert trends["situations"][0]["reports_last_hour"] == 3

    heat = client.get("/analytics/heatmaps").json()
    assert heat["window_days"] == 7
    assert heat["need_by_language"]["cols"] == ["en"]
    assert sum(map(sum, heat["department_by_hour"]["cells"])) == 3

    client.post(f"/situations/{flood_situation}/decision", json={"decision": "approve"})
    ticket_id = client.get("/tickets").json()[0]["id"]
    client.post(f"/tickets/{ticket_id}/status", json={"status": "acknowledged"})
    response = client.get("/analytics/response").json()
    assert response["by_department"]["Public Municipal"]["acknowledged_n"] == 1
    assert response["review"]["decided_n"] == 1


def test_daily_report_endpoints(flood_situation):
    client.post(f"/situations/{flood_situation}/decision", json={"decision": "approve"})
    today = client.get("/reports/daily/today").json()
    assert today["header"]["confirmed_by_band"][today["situations"][0]["peak_band"]] == 1
    assert today["situations"][0]["location"] == "Rajajinagar"

    day = today["date"]
    assert client.get(f"/reports/daily/{day}").json()["date"] == day
    assert [r["id"] for r in client.get("/reports/daily").json()] == [day]
    assert client.post(f"/reports/daily/{day}").status_code == 200
    assert client.get("/reports/daily/not-a-date").status_code == 422


def test_previous_day_report_is_generated_once():
    assert asyncio.run(service.ensure_previous_day_report()) is not None
    assert asyncio.run(service.ensure_previous_day_report()) is None
    assert len(asyncio.run(find_documents("daily_reports", {}))) == 1


def test_department_counts_leave_out_rejected_but_keep_reviewer_flagged_fakes():
    for sid, status in (("a", "pending"), ("b", "rejected"), ("c", "fake"), ("d", "confirmed")):
        asyncio.run(insert_document("situations", {"id": sid, "text": "", "status": status,
                                                   "department": "Healthcare", "created_at": time.time()}))
    assert client.get("/analytics/summary").json()["by_department"] == {"Healthcare": 3}


def test_filtered_posts_lists_newest_first_with_counts(mock_database):
    import asyncio

    from fastapi.testclient import TestClient

    from app.main import app

    docs = [
        {"id": "d1", "tweet_id": "1", "text": "win a free phone", "reason": "not_disaster",
         "detail": {"lang": "en", "disaster_confidence": 0.01, "threshold": 0.5}, "dropped_at": 100.0},
        {"id": "d2", "tweet_id": "2", "text": "flood near bellandur", "reason": "repost",
         "detail": {"repost_count": 2}, "dropped_at": 200.0},
        {"id": "d3", "tweet_id": "3", "text": "cricket tonight", "reason": "not_disaster",
         "detail": {"lang": "en", "disaster_confidence": 0.02, "threshold": 0.5}, "dropped_at": 300.0},
    ]
    asyncio.run(mock_database["dropped_tweets"].insert_many([dict(d) for d in docs]))
    with TestClient(app) as client:
        all_posts = client.get("/analytics/filtered").json()
        reposts = client.get("/analytics/filtered", params={"reason": "repost"}).json()
    assert all_posts["counts"] == {"not_disaster": 2, "repost": 1}
    assert [p["tweet_id"] for p in all_posts["posts"]] == ["3", "2", "1"]
    assert [p["tweet_id"] for p in reposts["posts"]] == ["2"]
    assert "_id" not in all_posts["posts"][0]
