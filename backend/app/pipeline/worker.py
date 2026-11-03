from __future__ import annotations

import asyncio
import logging
import time

from ..analytics import service as analytics_service
from ..config import ESCALATION_CHECK_SECONDS
from ..routers.queue import dequeue_item
from .escalation import escalate_overdue
from .orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


async def _periodic_checks(orchestrator: PipelineOrchestrator) -> None:
    try:
        escalated = await escalate_overdue()
        orchestrator.stats["auto_routed"] += len(escalated)
    except Exception:  # noqa: BLE001 — a DB hiccup must not stop the worker
        logger.exception("Escalation check failed")
    try:
        # store yesterday's daily report once the day has ended
        day = await analytics_service.ensure_previous_day_report()
        if day:
            logger.info("Stored daily report for %s", day)
    except Exception:  # noqa: BLE001
        logger.exception("Daily report generation failed")


async def _run(orchestrator: PipelineOrchestrator, poll_interval: float, escalation_every: float) -> None:
    logger.info("Pipeline worker started (poll every %.2fs)", poll_interval)
    last_check = 0.0
    while True:
        # Urgent situations nobody reviewed get routed, even when no posts arrive.
        if time.monotonic() - last_check >= escalation_every:
            last_check = time.monotonic()
            await _periodic_checks(orchestrator)
        item = dequeue_item()
        if item is None:
            await asyncio.sleep(poll_interval)
            continue
        await orchestrator.process_event(item.payload)


def start(
    orchestrator: PipelineOrchestrator, poll_interval: float, escalation_every: float = ESCALATION_CHECK_SECONDS
) -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run(orchestrator, poll_interval, escalation_every), name="pipeline-worker")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


def is_running() -> bool:
    return _task is not None and not _task.done()
