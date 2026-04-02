"""LLM factory functions for the ops-agent graphs."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm() -> ChatOpenAI:
    """Return the main (high-quality) LLM instance."""
    return ChatOpenAI(
        base_url=settings.aitunnel_base_url,
        api_key=settings.aitunnel_api_key,
        model=settings.model_main,
        temperature=0,
    )


def get_fast_llm() -> ChatOpenAI:
    """Return the fast (cheaper) LLM instance."""
    return ChatOpenAI(
        base_url=settings.aitunnel_base_url,
        api_key=settings.aitunnel_api_key,
        model=settings.model_fast,
        temperature=0,
    )
