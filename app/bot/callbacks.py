"""Inline keyboard generation and callback handlers for incident actions."""

from __future__ import annotations

import json
import logging

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from langgraph.types import Command
from redis.asyncio import Redis

from app.agent.graphs.analyze import resume_analyze_graph
from app.bot.router import router
from app.config import settings

logger = logging.getLogger(__name__)


def incident_keyboard(thread_id: str, incident: dict):
    """Generate inline keyboard from incident dangerous_actions.

    Each dangerous action gets a button. An "Ignore" button is always appended.

    Args:
        thread_id: LangGraph thread ID for resume.
        incident: Incident dict with dangerous_actions list.

    Returns:
        InlineKeyboardMarkup with one button per row.
    """
    builder = InlineKeyboardBuilder()
    for idx, action in enumerate(incident.get("dangerous_actions", [])):
        builder.button(
            text=action["label"],
            callback_data=f"action:{thread_id}:{idx}",
        )
    builder.button(
        text="Игнорировать",
        callback_data=f"ignore:{thread_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


async def _get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


@router.callback_query(F.data.startswith("action:"))
async def on_action(callback: CallbackQuery) -> None:
    """Handle action button press: resume the LangGraph with runbook info."""
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Неверный формат callback", show_alert=True)
        return

    _, thread_id, action_idx_str = parts
    try:
        action_idx = int(action_idx_str)
    except ValueError:
        await callback.answer("Неверный индекс действия", show_alert=True)
        return

    redis = await _get_redis()
    try:
        raw = await redis.get(f"tg_thread:{callback.message.message_id}")
        if not raw:
            await callback.answer("Данные инцидента истекли", show_alert=True)
            return

        data = json.loads(raw)
        incident = data["incident"]
        actions = incident.get("dangerous_actions", [])

        if action_idx >= len(actions):
            await callback.answer("Действие не найдено", show_alert=True)
            return

        action = actions[action_idx]
        await callback.answer("Выполняю...")

        # Remove keyboard from the message
        await callback.message.edit_reply_markup(reply_markup=None)

        # Resume the LangGraph
        await resume_analyze_graph(
            thread_id,
            Command(resume={"runbook": action["runbook"], "params": action.get("params", {})}),
        )

        await callback.message.reply(
            f"Runbook <b>{action['runbook']}</b> выполнен.",
        )
    finally:
        await redis.aclose()


@router.callback_query(F.data.startswith("ignore:"))
async def on_ignore(callback: CallbackQuery) -> None:
    """Handle ignore button press: resume graph with runbook=None."""
    parts = callback.data.split(":", 1)
    if len(parts) != 2:
        await callback.answer("Неверный формат callback", show_alert=True)
        return

    _, thread_id = parts

    await callback.answer("Проигнорировано")
    await callback.message.edit_reply_markup(reply_markup=None)

    redis = await _get_redis()
    try:
        # Resume graph indicating ignore
        await resume_analyze_graph(thread_id, Command(resume={"runbook": None}))

        await callback.message.reply("Проигнорировано.")
    finally:
        await redis.aclose()
