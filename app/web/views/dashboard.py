"""Dashboard view — stat cards + recent incidents."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.db.models import CheckRun, Incident, Server, SshKey
from app.db.session import get_session
from app.config import settings as env_settings
from app.services.settings import SettingsService
from app.web.auth import login_required

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/dashboard")
@login_required
async def dashboard(request: Request):
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    async with get_session() as session:
        # Servers
        servers_total = (await session.execute(select(func.count(Server.id)))).scalar() or 0
        servers_enabled = (
            await session.execute(select(func.count(Server.id)).where(Server.enabled.is_(True)))
        ).scalar() or 0

        # Incidents 24h
        incidents_24h = (
            await session.execute(
                select(func.count(Incident.id)).where(Incident.created_at >= day_ago)
            )
        ).scalar() or 0

        incidents_critical = (
            await session.execute(
                select(func.count(Incident.id)).where(
                    Incident.created_at >= day_ago, Incident.severity == "critical"
                )
            )
        ).scalar() or 0

        incidents_open = (
            await session.execute(
                select(func.count(Incident.id)).where(
                    Incident.status.in_(["new", "notified"])
                )
            )
        ).scalar() or 0

        # Check runs 24h
        checks_24h = (
            await session.execute(
                select(func.count(CheckRun.id)).where(CheckRun.started_at >= day_ago)
            )
        ).scalar() or 0

        checks_ok = (
            await session.execute(
                select(func.count(CheckRun.id)).where(
                    CheckRun.started_at >= day_ago, CheckRun.status == "ok"
                )
            )
        ).scalar() or 0

        checks_error = (
            await session.execute(
                select(func.count(CheckRun.id)).where(
                    CheckRun.started_at >= day_ago, CheckRun.status == "error"
                )
            )
        ).scalar() or 0

        # Recent incidents
        result = await session.execute(
            select(Incident).order_by(Incident.created_at.desc()).limit(10)
        )
        recent_incidents = result.scalars().all()

        # Check for missing configuration
        alerts = []
        svc = SettingsService(secret_key=env_settings.secret_key)
        app_settings = await svc.get_cached(session)

        if not app_settings.get("aitunnel_api_key") and not env_settings.aitunnel_api_key:
            alerts.append({"msg": "API ключ LLM не задан", "link": "/settings#llm"})

        if not app_settings.get("tg_bot_token") and not env_settings.tg_bot_token:
            alerts.append({"msg": "Telegram бот не настроен", "link": "/settings#telegram"})

        ssh_key_count = (await session.execute(
            select(func.count(SshKey.id))
        )).scalar() or 0
        if ssh_key_count == 0:
            alerts.append({"msg": "Нет SSH ключей", "link": "/settings#ssh"})

    stats = {
        "servers_total": servers_total,
        "servers_enabled": servers_enabled,
        "incidents_24h": incidents_24h,
        "incidents_critical": incidents_critical,
        "incidents_open": incidents_open,
        "checks_24h": checks_24h,
        "checks_ok": checks_ok,
        "checks_error": checks_error,
    }

    return templates.TemplateResponse(
        request, "dashboard.html", {"stats": stats, "recent_incidents": recent_incidents, "alerts": alerts}
    )
