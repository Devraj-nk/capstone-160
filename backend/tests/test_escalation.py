"""Auto-escalation: pending High/Critical situations get routed (unverified)
when no reviewer decides in time; reviewers keep the final say."""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from app.config import AUTO_ROUTE_MINUTES
from app.db import find_documents, find_one_document
from app.main import app
from app.pipeline import escalation, worker
from app.pipeline.escalation import escalate_overdue, next_due
from app.pipeline.orchestrator import orchestrator

client = TestClient(app)

HOUR = 3600
# Deadlines in minutes, read from config so changing a default doesn't break the tests.
CRITICAL = AUTO_ROUTE_MINUTES["Critical"]
HIGH = AUTO_ROUTE_MINUTES["High"]
assert 0 < CRITICAL < HIGH, "these tests assume Critical escalates sooner than High"


def upsert(cluster_id="c1", band="Critical", priority=0.8, likely_fake=False) -> str:
    built = {
        "situation": {
            "cluster_id": cluster_id,
            "text": "Flood near Rajajinagar",
            "language": "en",
            "languages": ["en"],
            "post_count": 3,
            "tweet_ids": ["t0", "t1", "t2"],
            "n_reports_unique": 3,
            "first_report_at": 1_780_000_000.0,
            "last_report_at": 1_780_000_120.0,
            "location": "Rajajinagar",
            "sentiment": {},
            "needs": {"municipal": 0.9, "active": ["municipal"]},
            "fake_news": {"fake_score": 0.7 if likely_fake else 0.1, "likely_fake": likely_fake},
            "priority": {"priority_score": priority, "band": band},
            "department": "Public Municipal",
            "summary": "Flooding reported.",
            "summary_i18n": {"en": "Flooding reported."},
            "summary_method": "template_v1",
            "representative": {},
            "evidence_posts": [],
            "evidence_version": "v1",
            "signals": {},
        },
        "evidence": [],
    }
    return asyncio.run(orchestrator._upsert_situation(built))[0]


def situation(situation_id: str) -> dict:
    return asyncio.run(find_one_document("situations", {"id": situation_id}))


def escalate(minutes_later: float) -> list[str]:
    return asyncio.run(escalate_overdue(now=time.time() + minutes_later * 60))


def test_deadline_keeps_earliest_and_clears_for_non_urgent_bands():
    now = 1_000_000.0
    high = next_due(None, "High", now)
    assert high == now + HIGH * 60
    assert next_due(None, "Critical", now) == now + CRITICAL * 60
    # High -> Critical just before the High deadline: the earlier High deadline still applies
    late_rise = now + (HIGH - CRITICAL / 2) * 60
    assert next_due(high, "Critical", late_rise) == high
    # High -> Critical early on: the sooner Critical deadline takes over
    early_rise = now + 60
    assert next_due(high, "Critical", early_rise) == early_rise + CRITICAL * 60
    # dropping to Medium clears it; rising again starts a fresh deadline
    assert next_due(high, "Medium", now) is None
    assert next_due(None, "High", now + HOUR) == now + HOUR + HIGH * 60
    assert next_due(None, "Low", now) is None


def test_critical_situation_without_review_is_auto_routed_unverified():
    situation_id = upsert(band="Critical")
    assert escalate(minutes_later=CRITICAL / 2) == []          # not yet due
    assert escalate(minutes_later=CRITICAL + 1) == [situation_id]

    doc = situation(situation_id)
    assert doc["status"] == "auto_routed"
    assert doc["routed_to"] == "Public Municipal"
    assert doc["escalated_at"] is not None
    ticket = client.get("/tickets").json()[0]
    assert ticket["verified"] is False
    assert ticket["history"][0]["by"] == "auto_escalation"
    # escalation is not a human label: no verdict is written
    assert asyncio.run(find_documents("verdicts", {})) == []
    # and it is not escalated twice
    assert escalate(minutes_later=60) == []


def test_high_waits_its_longer_deadline_medium_and_low_never():
    high = upsert(cluster_id="h", band="High", priority=0.6)
    upsert(cluster_id="m", band="Medium", priority=0.4)
    upsert(cluster_id="l", band="Low", priority=0.2)
    assert escalate(minutes_later=CRITICAL + 1) == []  # past the Critical deadline, not High's
    assert escalate(minutes_later=HIGH + 1) == [high]
    assert escalate(minutes_later=24 * 60) == []


def test_likely_fake_situations_are_never_auto_routed():
    upsert(band="Critical", likely_fake=True)
    assert escalate(minutes_later=24 * 60) == []
    assert client.get("/tickets").json() == []


def test_reviewed_situations_are_not_escalated():
    situation_id = upsert(band="Critical")
    client.post(f"/situations/{situation_id}/decision", json={"decision": "reject"})
    assert escalate(minutes_later=60) == []
    assert client.get("/tickets").json() == []


def test_reviewer_approval_verifies_the_auto_routed_tickets():
    situation_id = upsert(band="Critical")
    escalate(minutes_later=CRITICAL + 1)
    body = client.post(f"/situations/{situation_id}/decision", json={"decision": "approve"}).json()
    assert body["status"] == "confirmed"
    tickets = client.get("/tickets").json()
    assert len(tickets) == 1 and tickets[0]["verified"] is True
    assert asyncio.run(find_documents("verdicts", {}))[0]["verdict"] == "true"


def test_reviewer_fake_flags_but_does_not_cancel_the_auto_routed_tickets():
    situation_id = upsert(band="Critical")
    escalate(minutes_later=CRITICAL + 1)
    client.post(f"/situations/{situation_id}/decision", json={"decision": "fake"})
    ticket = client.get("/tickets").json()[0]
    assert ticket["status"] == "routed" and ticket["reviewer_flag"] == "fake"
    assert situation(situation_id)["status"] == "fake"


def test_reject_through_the_api_still_cancels_the_auto_routed_tickets():
    situation_id = upsert(band="Critical")
    escalate(minutes_later=CRITICAL + 1)
    client.post(f"/situations/{situation_id}/decision", json={"decision": "reject"})
    assert client.get("/tickets").json()[0]["status"] == "cancelled"


def test_auto_routed_situations_stay_in_the_review_queue_and_follow_rescoring():
    situation_id = upsert(band="Critical", priority=0.8)
    pending_only = upsert(cluster_id="c2", band="Medium", priority=0.4)
    escalate(minutes_later=CRITICAL + 1)

    queue = client.get("/situations?status=pending&status=auto_routed").json()
    assert {s["id"] for s in queue} == {situation_id, pending_only}
    assert client.get("/analytics/summary").json()["auto_routed"] == 1

    upsert(band="Critical", priority=0.9)  # new posts rescore the same cluster
    assert client.get("/tickets").json()[0]["queue_priority"] == 0.9
    assert situation(situation_id)["status"] == "auto_routed"


def test_band_rising_while_pending_keeps_the_earlier_deadline(monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr(time, "time", lambda: clock[0])  # wall clock used by the orchestrator
    situation_id = upsert(band="High", priority=0.6)
    first_due = situation(situation_id)["escalation_due_at"]
    clock[0] += (HIGH - CRITICAL / 2) * 60  # rises to Critical shortly before High's deadline
    upsert(band="Critical", priority=0.8)
    assert situation(situation_id)["escalation_due_at"] == first_due


def test_escalate_endpoint_runs_the_check_now():
    upsert(band="Critical")
    assert client.post("/pipeline/escalate").json() == {"auto_routed": []}  # just created, not due


def test_background_worker_escalates_without_any_new_posts(monkeypatch):
    monkeypatch.setitem(escalation.AUTO_ROUTE_MINUTES, "Critical", 0.001)  # ~60 ms
    situation_id = upsert(band="Critical")

    async def run() -> None:
        worker.start(orchestrator, poll_interval=0.01, escalation_every=0.02)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            doc = await find_one_document("situations", {"id": situation_id})
            if doc["status"] == "auto_routed":
                break
            await asyncio.sleep(0.02)
        await worker.stop()

    asyncio.run(run())
    assert situation(situation_id)["status"] == "auto_routed"
    assert orchestrator.stats["auto_routed"] == 1
