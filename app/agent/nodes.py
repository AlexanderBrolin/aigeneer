"""LLM factory functions for the ops-agent graphs."""

from __future__ import annotations

import time

from langchain_openai import ChatOpenAI

from app.config import settings

# Module-level cache for LLM settings from DB
_llm_cache: dict[str, str] = {}
_llm_cache_ts: float = 0
_LLM_CACHE_TTL = 60


async def _refresh_llm_cache() -> dict[str, str]:
    """Load LLM settings from DB into module cache."""
    global _llm_cache, _llm_cache_ts
    now = time.time()
    if _llm_cache and now - _llm_cache_ts < _LLM_CACHE_TTL:
        return _llm_cache
    try:
        from app.services.settings import SettingsService
        from app.db.session import get_session

        svc = SettingsService(secret_key=settings.secret_key)
        async with get_session() as session:
            _llm_cache = await svc.get_all(session)
        _llm_cache_ts = now
    except Exception:
        pass
    return _llm_cache


async def get_llm() -> ChatOpenAI:
    """Return the main (high-quality) LLM instance with settings from DB."""
    db = await _refresh_llm_cache()
    return ChatOpenAI(
        base_url=db.get("aitunnel_base_url") or settings.aitunnel_base_url,
        api_key=db.get("aitunnel_api_key") or settings.aitunnel_api_key,
        model=db.get("model_main") or settings.model_main,
        temperature=0,
    )


async def get_fast_llm() -> ChatOpenAI:
    """Return the fast (cheaper) LLM instance with settings from DB."""
    db = await _refresh_llm_cache()
    return ChatOpenAI(
        base_url=db.get("aitunnel_base_url") or settings.aitunnel_base_url,
        api_key=db.get("aitunnel_api_key") or settings.aitunnel_api_key,
        model=db.get("model_fast") or settings.model_fast,
        temperature=0,
    )
