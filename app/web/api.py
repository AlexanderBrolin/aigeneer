"""JSON API endpoints for chart data."""

from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db.models import Incident
from app.db.session import get_session

router = APIRouter(prefix="/api")


@router.get("/chart/incidents-timeline")
async def incidents_timeline():
    """Incidents per day for the last 7 days."""
    now = datetime.utcnow()
    labels = []
    values = []

    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        async with get_session() as session:
            count = (
                await session.execute(
                    select(func.count(Incident.id)).where(
                        Incident.created_at >= day_start,
                        Incident.created_at < day_end,
                    )
                )
            ).scalar() or 0

        labels.append(day_start.strftime("%d.%m"))
        values.append(count)

    return {"labels": labels, "values": values}


@router.get("/chart/incidents-severity")
async def incidents_severity():
    """Incidents by severity for the last 7 days."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    result = {"critical": 0, "warning": 0, "info": 0}

    async with get_session() as session:
        for severity in result:
            count = (
                await session.execute(
                    select(func.count(Incident.id)).where(
                        Incident.created_at >= week_ago,
                        Incident.severity == severity,
                    )
                )
            ).scalar() or 0
            result[severity] = count

    return {
        "labels": ["Critical", "Warning", "Info"],
        "values": [result["critical"], result["warning"], result["info"]],
    }
