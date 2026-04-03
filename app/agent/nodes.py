"""LLM factory functions for the ops-agent graphs."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import settings


def _get_llm_settings() -> dict[str, str]:
    """Read LLM settings from DB (cached), fallback to .env."""
    try:
        import asyncio
        from app.services.settings import SettingsService
        from app.db.session import get_session

        svc = SettingsService(secret_key=settings.secret_key)

        async def _load():
            async with get_session() as session:
                return await svc.get_cached(session)

        # Try to get running loop (aiogram/FastAPI context)
        try:
            loop = asyncio.get_running_loop()
            # Can't await in sync context with running loop — use cache directly
            if svc._cache:
                return svc._cache
        except RuntimeError:
            pass

        # No running loop (Celery context) — safe to asyncio.run
        try:
            return asyncio.run(_load())
        except RuntimeError:
            pass
    except Exception:
        pass

    return {}


def get_llm() -> ChatOpenAI:
    """Return the main (high-quality) LLM instance."""
    db = _get_llm_settings()
    return ChatOpenAI(
        base_url=db.get("aitunnel_base_url") or settings.aitunnel_base_url,
        api_key=db.get("aitunnel_api_key") or settings.aitunnel_api_key,
        model=db.get("model_main") or settings.model_main,
        temperature=0,
    )


def get_fast_llm() -> ChatOpenAI:
    """Return the fast (cheaper) LLM instance."""
    db = _get_llm_settings()
    return ChatOpenAI(
        base_url=db.get("aitunnel_base_url") or settings.aitunnel_base_url,
        api_key=db.get("aitunnel_api_key") or settings.aitunnel_api_key,
        model=db.get("model_fast") or settings.model_fast,
        temperature=0,
    )
