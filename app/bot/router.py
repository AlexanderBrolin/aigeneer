"""Bot instance, Dispatcher, and Router for Aiogram 3.x."""

from aiogram import Bot, Dispatcher, Router

from app.config import settings

router = Router()
dp = Dispatcher()
dp.include_router(router)

_bot: Bot | None = None


def get_bot() -> Bot:
    """Return the singleton Bot instance, creating it on first call."""
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.tg_bot_token, parse_mode="HTML")
    return _bot
