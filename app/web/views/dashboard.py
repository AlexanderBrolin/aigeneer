"""Dashboard view — incident-centric with live polling."""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.config import settings as env_settings
from app.db.models import SshKey
from app.db.session import get_session
from app.services.settings import SettingsService
from app.web.auth import login_required

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/dashboard")
@login_required
async def dashboard(request: Request):
    # Config alerts (server-side, not polled)
    alerts = []
    svc = SettingsService(secret_key=env_settings.secret_key)

    async with get_session() as session:
        app_settings = await svc.get_cached(session)

        if not app_settings.get("aitunnel_api_key") and not env_settings.aitunnel_api_key:
            alerts.append({"msg": "API ключ LLM не задан", "link": "/settings#llm"})

        if not app_settings.get("tg_bot_token") and not env_settings.tg_bot_token:
            alerts.append({"msg": "Telegram бот не настроен", "link": "/settings#telegram"})

        ssh_key_count = (await session.execute(select(func.count(SshKey.id)))).scalar() or 0
        if ssh_key_count == 0:
            alerts.append({"msg": "Нет SSH ключей", "link": "/settings#ssh"})

    return templates.TemplateResponse(
        request, "dashboard.html", {"alerts": alerts, "active_page": "dashboard"}
    )
