"""
FastAPI router for fire-and-forget ingestion of PM interaction events.

The gateway middleware POSTs every tool-call event to ``POST /ingest`` on this
service.  We return 202 Accepted immediately and write the row to TimescaleDB
asynchronously — this keeps the critical path latency of the gateway near-zero.

All writes go to the ``pm_interactions`` hypertable defined in
``cognitive_server/db/schema.sql``.
"""

from __future__ import annotations

import json
import asyncio
import structlog

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from cognitive_server.ingest.models import InteractionEvent
from cognitive_server.db.connection import acquire

log = structlog.get_logger("cognitive.ingest")

router = APIRouter(prefix="/ingest", tags=["ingest"])

# ---------------------------------------------------------------------------
# INSERT statement
# ---------------------------------------------------------------------------

_INSERT_SQL = """
INSERT INTO pm_interactions (
    timestamp,
    session_id,
    pm_sub,
    pm_desk,
    tool_name,
    tool_server,
    arguments,
    result_summary,
    preceding_tool,
    preceding_interval_ms
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
"""


async def _write_event(event: InteractionEvent) -> None:
    """Write a single interaction event to TimescaleDB.

    Runs in the background so the HTTP response is not delayed.
    Errors are logged but not re-raised — a failed write must never bring
    down the gateway ingestion path.
    """
    try:
        async with acquire() as conn:
            desk_list = [event.desk] if event.desk else None
            await conn.execute(
                _INSERT_SQL,
                event.timestamp,
                event.session_id,
                event.pm_sub,
                desk_list,
                event.tool_name,
                event.tool_server,
                json.dumps(event.arguments),
                event.result_summary,
                event.preceding_tool,
                event.preceding_interval_ms,
            )
        log.debug(
            "interaction_written",
            pm_sub=event.pm_sub,
            tool=event.tool_name,
            session=event.session_id,
        )
    except Exception:
        log.exception(
            "interaction_write_failed",
            pm_sub=event.pm_sub,
            tool=event.tool_name,
        )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    event: InteractionEvent,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Accept a PM interaction event from the gateway middleware.

    The request body must be a JSON-serialised ``InteractionEvent``.  The
    endpoint returns ``202 Accepted`` immediately and schedules the database
    write as a FastAPI background task so the gateway's hot path is never
    blocked on database I/O.

    Returns:
        ``{"status": "accepted"}`` on success.

    Raises:
        422 if the request body fails Pydantic validation.
    """
    log.info(
        "interaction_received",
        pm_sub=event.pm_sub,
        tool=event.tool_name,
        session=event.session_id,
    )
    background_tasks.add_task(_write_event, event)
    return {"status": "accepted"}


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(
    events: list[InteractionEvent],
    background_tasks: BackgroundTasks,
) -> dict[str, str | int]:
    """
    Accept a batch of PM interaction events.

    Useful when the gateway replays events after a transient failure.  Each
    event is scheduled as a separate background write so partial failures do
    not block the rest of the batch.

    Returns:
        ``{"status": "accepted", "count": N}``
    """
    if len(events) > 500:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Batch size must not exceed 500 events.",
        )
    for event in events:
        background_tasks.add_task(_write_event, event)
    log.info("batch_received", count=len(events))
    return {"status": "accepted", "count": len(events)}
