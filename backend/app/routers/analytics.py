from __future__ import annotations

import time
from datetime import date

from fastapi import APIRouter, HTTPException

from ..analytics import metrics, service

router = APIRouter(tags=["analytics"])


def _valid_day(day: str) -> str:
    try:
        date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
    return day


@router.get("/analytics/response")
async def response_metrics() -> dict:
    """Time to acknowledge / resolve per band and department, reviewer wait, open load."""
    return await service.response()


@router.get("/analytics/trends")
async def trends() -> dict:
    """Live board, Growing / Stable / Fading per active situation, posts per hour (24 h)."""
    return await service.trends()


@router.get("/analytics/heatmaps")
async def heatmaps() -> dict:
    """Department x hour of day and need x language (last 7 days of posts)."""
    return await service.heatmaps()


@router.get("/reports/daily")
async def list_daily_reports() -> list[dict]:
    return await service.list_daily_reports()


@router.get("/reports/daily/today")
async def today() -> dict:
    """Today's report so far (rebuilt on every call)."""
    return await service.build_daily_report(metrics.local_date(time.time()))


@router.get("/reports/daily/{day}")
async def get_daily_report(day: str) -> dict:
    """The stored report for that day (built and stored on first request)."""
    return await service.get_daily_report(_valid_day(day))


@router.post("/reports/daily/{day}")
async def rebuild_daily_report(day: str) -> dict:
    return await service.build_daily_report(_valid_day(day))
