"""Notification and command handlers for the Telegram bot."""

from __future__ import annotations

import json
import logging

from aiogram import Bot
from aiogram.filters import CommandStart
from aiogram.types import Message
from redis.asyncio import Redis

from app.bot.callbacks import incident_keyboard
from app.bot.router import router
from app.config import settings

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {
    "critical": "\u2757\ufe0f",  # red exclamation
    "warning": "\u26a0\ufe0f",   # warning sign
    "info": "\u2139\ufe0f",      # info
}


async def _get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def notify_incident(
    bot: Bot,
    chat_id: int | str,
    thread_id: str,
    interrupt_data: dict,
) -> None:
    """Send an incident notification to Telegram with action buttons.

    Args:
        bot: Aiogram Bot instance.
        chat_id: Telegram chat ID to send the notification to.
        thread_id: LangGraph thread ID for resume.
        interrupt_data: Dict with 'incident' and 'host' keys from interrupt().
    """
    incident = interrupt_data["incident"]
    host = interrupt_data.get("host", "unknown")
    severity = incident.get("severity", "info")
    emoji = SEVERITY_EMOJI.get(severity, "\u2139\ufe0f")

    text = (
        f"{emoji} <b>Инцидент: {incident.get('problem_type', 'unknown')}</b>\n\n"
        f"<b>Хост:</b> {host}\n"
        f"<b>Severity:</b> {severity}\n"
        f"<b>Описание:</b>\n{incident.get('evidence', 'Нет данных')}"
    )

    keyboard = incident_keyboard(thread_id, incident)
    msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

    # Store mapping message_id -> {thread_id, incident} in Redis with TTL
    redis = await _get_redis()
    try:
        await redis.setex(
            f"tg_thread:{msg.message_id}",
            3600,
            json.dumps({"thread_id": thread_id, "incident": incident}, ensure_ascii=False),
        )
    finally:
        await redis.aclose()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer("ops-agent бот активен")


@router.message()
async def handle_text_command(message: Message) -> None:
    """Route free-text messages through command_graph."""
    from app.agent.graphs.command import get_command_graph, CommandState
    from langgraph.types import Command as LGCommand
    import uuid

    if message.from_user and str(message.from_user.id) not in settings.tg_allowed_user_ids:
        return

    thread_id = f"cmd-{message.from_user.id}-{uuid.uuid4().hex[:8]}"
    graph = await get_command_graph()

    state = CommandState(message=message.text or "")
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await graph.ainvoke(state, config=config)
        response_text = result.get("response") or "Команда обработана."
        await message.answer(response_text)

    except Exception as exc:
        # Check for interrupt (write op needs confirmation)
        from langgraph.errors import GraphInterrupt
        if isinstance(exc, GraphInterrupt):
            interrupt_data = exc.args[0][0].value if exc.args else {}
            summary = interrupt_data.get("summary", "действие")
            # Store pending thread for callback
            redis = await _get_redis()
            try:
                await redis.setex(
                    f"cmd_thread:{message.from_user.id}",
                    300,
                    json.dumps({"thread_id": thread_id, "interrupt": interrupt_data}),
                )
            finally:
                await redis.aclose()

            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_cmd:{thread_id}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_cmd:{thread_id}")],
            ])
            await message.answer(
                f"⚠️ Требуется подтверждение:\n<b>{summary}</b>",
                reply_markup=keyboard,
            )
        else:
            logger.error("command_graph error: %s", exc)
            await message.answer(f"Ошибка: {exc}")
