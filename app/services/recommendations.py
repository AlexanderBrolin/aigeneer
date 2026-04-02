"""AI-powered monitoring recommendations based on incident history."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select

from app.agent.nodes import get_llm
from app.agent.prompts import RECOMMENDATION_PROMPT
from app.db.models import Incident, Server, ServerCheck
from app.db.session import get_session

logger = logging.getLogger(__name__)


async def get_incident_stats(days: int = 7) -> list[dict]:
    """Fetch incident history for the specified period."""
    since = datetime.utcnow() - timedelta(days=days)

    async with get_session() as session:
        result = await session.execute(
            select(Incident)
            .where(Incident.created_at >= since)
            .order_by(Incident.created_at.desc())
            .limit(200)
        )
        incidents = result.scalars().all()

    return [
        {
            "host": inc.host,
            "severity": inc.severity,
            "problem_type": inc.problem_type,
            "evidence": inc.evidence[:200],
            "created_at": inc.created_at.isoformat(),
        }
        for inc in incidents
    ]


async def generate_recommendations(days: int = 7) -> list[dict]:
    """Ask LLM to analyze incident patterns and suggest monitoring improvements."""
    incidents = await get_incident_stats(days)

    if not incidents:
        return []

    llm = get_llm()
    payload = json.dumps(incidents, ensure_ascii=False, indent=2)

    try:
        response = await llm.ainvoke([
            SystemMessage(content=RECOMMENDATION_PROMPT),
            HumanMessage(content=f"Инциденты за последние {days} дней:\n{payload}"),
        ])
        recs = json.loads(response.content)
        if not isinstance(recs, list):
            recs = []
    except (json.JSONDecodeError, Exception) as exc:
        logger.error("generate_recommendations failed: %s", exc)
        return []

    return recs


async def apply_recommendation(server_id: int, check_name: str, params: dict) -> bool:
    """Apply a recommendation by adding/updating a ServerCheck."""
    from app.checks import CHECK_REGISTRY

    if check_name not in CHECK_REGISTRY and check_name != "new":
        return False

    async with get_session() as session:
        server = await session.get(Server, server_id)
        if not server:
            return False

        # Check if already exists
        from sqlalchemy import and_
        result = await session.execute(
            select(ServerCheck).where(
                and_(
                    ServerCheck.server_id == server_id,
                    ServerCheck.check_name == check_name,
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.params = params
            existing.enabled = True
        else:
            sc = ServerCheck(
                server_id=server_id,
                check_name=check_name,
                params=params,
                enabled=True,
            )
            session.add(sc)

    return True
