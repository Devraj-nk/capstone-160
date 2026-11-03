"""Loads what the analytics need from MongoDB and stores daily reports."""
from __future__ import annotations

import time
from typing import Any

from ..db import (
    DAILY_REPORTS,
    ROUTING_TICKETS,
    SITUATIONS,
    TWEETS,
    find_documents,
    find_one_document,
    get_collection,
)
from . import metrics

# Big fields the analytics never read.
_TWEET_FIELDS = {"embedding": 0, "text_raw": 0, "metadata": 0}
_SITUATION_FIELDS = {"evidence_posts": 0, "representative": 0, "signals": 0, "tweet_ids": 0}
_HEATMAP_WINDOW = 7 * metrics.DAY


async def _situations() -> list[dict[str, Any]]:
    return await find_documents(SITUATIONS, {}, limit=50_000, projection=_SITUATION_FIELDS)


async def _tickets() -> list[dict[str, Any]]:
    return await find_documents(ROUTING_TICKETS, {}, limit=100_000)


async def _tweets_since(since: float) -> list[dict[str, Any]]:
    return await find_documents(TWEETS, {"created_at": {"$gt": since}}, limit=500_000, projection=_TWEET_FIELDS)


async def simulation_clock() -> float:
    """Newest post time (so replayed data behaves like live data); now if no posts."""
    docs = await get_collection(TWEETS).find({}, {"created_at": 1}).sort("created_at", -1).limit(1).to_list(1)
    latest = docs[0].get("created_at") if docs else None
    return float(latest) if isinstance(latest, (int, float)) else time.time()


async def response(now: float | None = None) -> dict[str, Any]:
    return metrics.response_metrics(await _tickets(), await _situations(), time.time() if now is None else now)


async def trends() -> dict[str, Any]:
    clock = await simulation_clock()
    return metrics.trends(await _situations(), await _tweets_since(clock - metrics.DAY), clock)


async def heatmaps() -> dict[str, Any]:
    clock = await simulation_clock()
    return {**metrics.heatmaps(await _tweets_since(clock - _HEATMAP_WINDOW)), "window_days": 7, "clock": clock}


async def build_daily_report(day: str) -> dict[str, Any]:
    """Build and store (replace) the report for `day` (YYYY-MM-DD, local)."""
    report = metrics.daily_report(day, await _situations(), await _tickets(), generated_at=time.time())
    await get_collection(DAILY_REPORTS).replace_one({"id": day}, report, upsert=True)
    report.pop("_id", None)
    return report


async def get_daily_report(day: str) -> dict[str, Any]:
    stored = await find_one_document(DAILY_REPORTS, {"id": day})
    if stored is None:
        return await build_daily_report(day)
    stored.pop("_id", None)
    return stored


async def list_daily_reports() -> list[dict[str, Any]]:
    docs = await find_documents(DAILY_REPORTS, {}, limit=1000, projection={"id": 1, "generated_at": 1, "header": 1})
    return sorted(({k: v for k, v in d.items() if k != "_id"} for d in docs), key=lambda d: d["id"], reverse=True)


async def ensure_previous_day_report(now: float | None = None) -> str | None:
    """End-of-day generation: once a day has ended, store its report if it
    isn't stored yet. Cheap enough to call on every worker tick; returns the
    day it generated, if any."""
    yesterday = metrics.local_date((time.time() if now is None else now) - metrics.DAY)
    if await find_one_document(DAILY_REPORTS, {"id": yesterday}) is not None:
        return None
    await build_daily_report(yesterday)
    return yesterday
