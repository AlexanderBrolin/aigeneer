from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models import Incident
from app.db.session import get_session

# How long (minutes) before a non-actioned incident expires and re-notification is allowed.
RE_NOTIFY_MINUTES: dict[str, int] = {
    "critical": 30,
    "warning": 60,
    "info": 120,
}
# How far back (hours) to look for a recent actioned incident when deciding to bypass dedup.
_ACTIONED_LOOKBACK_HOURS = 1


async def find_active_incident(host: str, problem_type: str) -> Incident | None:
    """Return an open (new/notified) incident if it should still suppress notifications.

    Returns None (allow new notification) when:
    - No open incident exists
    - A recent (< 1 h) actioned incident exists: fix was attempted → notify every cycle
    - The existing open incident is older than RE_NOTIFY_MINUTES[severity]: time-based re-notify
    """
    async with get_session() as session:
        # 1. If a fix was attempted recently → bypass dedup entirely (notify every cycle)
        cutoff_actioned = datetime.utcnow() - timedelta(hours=_ACTIONED_LOOKBACK_HOURS)
        actioned_result = await session.execute(
            select(Incident)
            .where(
                Incident.host == host,
                Incident.problem_type == problem_type,
                Incident.status == "actioned",
                Incident.created_at > cutoff_actioned,
            )
            .limit(1)
        )
        if actioned_result.scalar_one_or_none() is not None:
            return None

        # 2. Find newest open incident (new / notified)
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
        existing = result.scalar_one_or_none()
        if existing is None:
            return None

        # 3. Time-based expiry: if incident is older than TTL → allow re-notify
        ttl_minutes = RE_NOTIFY_MINUTES.get(existing.severity, 30)
        age_minutes = (datetime.utcnow() - existing.created_at).total_seconds() / 60
        if age_minutes > ttl_minutes:
            return None

        return existing


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
