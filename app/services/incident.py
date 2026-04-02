from datetime import datetime

from sqlalchemy import select

from app.db.models import Incident
from app.db.session import get_session


async def find_active_incident(host: str, problem_type: str) -> Incident | None:
    """Return an open incident for this (host, problem_type), or None.

    Statuses 'new' and 'notified' mean the problem is already being tracked.
    Status 'actioned' means a fix was attempted — if the problem is back, we
    should notify again.
    """
    async with get_session() as session:
        result = await session.execute(
            select(Incident)
            .where(
                Incident.host == host,
                Incident.problem_type == problem_type,
                Incident.status.in_(["new", "notified"]),
            )
            .order_by(Incident.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def save_incident(
    check_run_id: int | None,
    thread_id: str | None,
    host: str,
    severity: str,
    problem_type: str,
    evidence: str,
) -> int:
    async with get_session() as session:
        incident = Incident(
            check_run_id=check_run_id,
            thread_id=thread_id,
            host=host,
            severity=severity,
            problem_type=problem_type,
            evidence=evidence,
        )
        session.add(incident)
        await session.flush()
        return incident.id


async def update_incident_status(incident_id: int, status: str, action_taken: str | None = None) -> None:
    async with get_session() as session:
        result = await session.execute(select(Incident).where(Incident.id == incident_id))
        incident = result.scalar_one_or_none()
        if incident:
            incident.status = status
            if action_taken:
                incident.action_taken = action_taken
            if status == "resolved":
                incident.resolved_at = datetime.utcnow()


async def get_incident(incident_id: int) -> Incident | None:
    async with get_session() as session:
        result = await session.execute(select(Incident).where(Incident.id == incident_id))
        return result.scalar_one_or_none()
