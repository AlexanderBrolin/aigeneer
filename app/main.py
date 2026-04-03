import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app):
    """Seed DB on first start, then start Aiogram bot polling."""
    # Seed settings and admin user from .env on first startup
    from app.db.session import get_session
    from app.services.seed import seed_admin_user, seed_settings

    async with get_session() as session:
        env_values = {
            "aitunnel_base_url": settings.aitunnel_base_url,
            "aitunnel_api_key": settings.aitunnel_api_key,
            "model_main": settings.model_main,
            "model_fast": settings.model_fast,
            "tg_bot_token": settings.tg_bot_token,
            "tg_chat_id": settings.tg_chat_id,
            "tg_allowed_users": settings.tg_allowed_users,
            "ssh_default_user": settings.ssh_default_user,
            "check_interval_minutes": str(settings.check_interval_minutes),
        }
        await seed_settings(session, secret_key=settings.secret_key, env_values=env_values)
        await seed_admin_user(session, username=settings.admin_username, password=settings.admin_password)

    # Start TG bot
    task = None
    if settings.tg_bot_token:
        from app.bot.router import dp, get_bot

        import app.bot.callbacks  # noqa: F401
        import app.bot.handlers  # noqa: F401

        bot = get_bot()
        task = asyncio.create_task(dp.start_polling(bot))

    yield

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ops-agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Web panel routes
from app.web import router as web_router  # noqa: E402
from app.web.views.dashboard import router as dashboard_router  # noqa: E402
from app.web.views.servers import router as servers_router  # noqa: E402
from app.web.views.incidents import router as incidents_router  # noqa: E402
from app.web.views.check_runs import router as check_runs_router  # noqa: E402
from app.web.views.recommendations import router as recommendations_router  # noqa: E402
from app.web.views.settings import router as settings_router  # noqa: E402
from app.web.api import router as api_router  # noqa: E402

app.include_router(web_router)
app.include_router(dashboard_router)
app.include_router(servers_router)
app.include_router(incidents_router)
app.include_router(check_runs_router)
app.include_router(recommendations_router)
app.include_router(settings_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
