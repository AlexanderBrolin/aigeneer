import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app):
    """Start Aiogram bot polling alongside FastAPI."""
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
from app.web.api import router as api_router  # noqa: E402

app.include_router(web_router)
app.include_router(dashboard_router)
app.include_router(servers_router)
app.include_router(incidents_router)
app.include_router(check_runs_router)
app.include_router(recommendations_router)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
