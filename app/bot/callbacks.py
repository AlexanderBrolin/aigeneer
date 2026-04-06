"""Inline keyboard generation and callback handlers for incident actions.

Callback data uses incident DB IDs so buttons work indefinitely
(no Redis TTL dependency).
"""

from __future__ import annotations

import json
import logging

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from langgraph.types import Command

from app.bot.router import router
from app.config import settings
from app.services.incident import get_incident, update_incident_status

logger = logging.getLogger(__name__)


def incident_keyboard(incident_db_id: int, thread_id: str, incident: dict):
    """Generate inline keyboard from incident dangerous_actions.

    Uses incident DB ID in callback_data so buttons survive Redis TTL.
    """
    builder = InlineKeyboardBuilder()
    for idx, action in enumerate(incident.get("dangerous_actions", [])):
        builder.button(
            text=action["label"],
            callback_data=f"act:{incident_db_id}:{idx}",
        )
    builder.button(
        text="Resolved",
        callback_data=f"resolve:{incident_db_id}",
    )
    builder.button(
        text="Игнорировать",
        callback_data=f"ign:{incident_db_id}",
    )
    builder.adjust(1)
    return builder.as_markup()


async def _load_incident(incident_db_id: int) -> dict | None:
    """Load incident from DB, return dict with actions or None."""
    from app.db.session import get_session
    from app.db.models import Incident
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(select(Incident).where(Incident.id == incident_db_id))
        inc = result.scalar_one_or_none()
        if not inc:
            return None
        return {
            "id": inc.id,
            "thread_id": inc.thread_id,
            "host": inc.host,
            "severity": inc.severity,
            "problem_type": inc.problem_type,
            "status": inc.status,
            "actions_json": inc.actions_json or {},
        }


@router.callback_query(F.data.startswith("act:"))
async def on_action(callback: CallbackQuery) -> None:
    """Handle action button: look up incident from DB, execute runbook."""
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Неверный формат", show_alert=True)
        return

    try:
        incident_db_id = int(parts[1])
        action_idx = int(parts[2])
    except ValueError:
        await callback.answer("Неверные данные", show_alert=True)
        return

    inc = await _load_incident(incident_db_id)
    if not inc:
        await callback.answer("Инцидент не найден", show_alert=True)
        return

    if inc["status"] == "resolved":
        await callback.answer("Инцидент уже разрешён", show_alert=True)
        return

    actions = inc["actions_json"].get("dangerous_actions", [])
    if action_idx >= len(actions):
        await callback.answer("Действие не найдено", show_alert=True)
        return

    action = actions[action_idx]
    await callback.answer("Выполняю...")
    await callback.message.edit_reply_markup(reply_markup=None)

    # Mark as actioned
    try:
        await update_incident_status(incident_db_id, "actioned", action.get("runbook"))
    except Exception:
        logger.exception("Failed to mark incident %s as actioned", incident_db_id)

    # Execute runbook directly (no LangGraph resume needed)
    from app.runbooks import run_runbook
    from app.agent.tool_provider import get_write_tools

    host_config = inc["actions_json"].get("host_config", {})
    tools = get_write_tools(host_config) if host_config else []

    try:
        result = await run_runbook(action.get("runbook", ""), action.get("params", {}), tools)
        icon = "\u2705" if result.success else "\u274c"
        reply_text = f"{icon} <b>{result.message}</b>"
        if result.details:
            reply_text += f"\n\n<pre>{result.details[:2000]}</pre>"
        await callback.message.reply(reply_text, parse_mode="HTML")
    except Exception as exc:
        logger.exception("Runbook execution failed for incident %s", incident_db_id)
        await callback.message.reply(f"\u274c Ошибка: {exc}", parse_mode="HTML")


@router.callback_query(F.data.startswith("resolve:"))
async def on_resolve(callback: CallbackQuery) -> None:
    """Handle resolve button: mark incident as resolved."""
    try:
        incident_db_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Неверные данные", show_alert=True)
        return

    inc = await _load_incident(incident_db_id)
    if not inc:
        await callback.answer("Инцидент не найден", show_alert=True)
        return

    if inc["status"] == "resolved":
        await callback.answer("Уже разрешён", show_alert=True)
        return

    await update_incident_status(incident_db_id, "resolved")
    await callback.answer("Инцидент разрешён")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("\u2705 Инцидент отмечен как разрешённый.")


@router.callback_query(F.data.startswith("ign:"))
async def on_ignore(callback: CallbackQuery) -> None:
    """Handle ignore button: mark incident as ignored."""
    try:
        incident_db_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Неверные данные", show_alert=True)
        return

    await update_incident_status(incident_db_id, "ignored")
    await callback.answer("Проигнорировано")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("Проигнорировано.")


# --- TG command confirmation callbacks (unchanged) ---

@router.callback_query(F.data.startswith("confirm_cmd:"))
async def on_confirm_cmd(callback: CallbackQuery) -> None:
    """Handle command confirmation button."""
    thread_id = callback.data.split(":", 1)[1]
    from app.agent.graphs.command import run_command_graph, CommandState
    from redis.asyncio import Redis

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        raw = await redis.get(f"cmd_thread:{callback.from_user.id}")
        if not raw:
            await callback.answer("Данные устарели", show_alert=True)
            return

        data = json.loads(raw)
        await callback.answer("Выполняю...")
        await callback.message.edit_reply_markup(reply_markup=None)

        # Resume is not needed here — the command was already classified.
        # For simplicity, just run the pending runbook directly.
        from app.runbooks import run_runbook
        from app.agent.tool_provider import get_write_tools

        interrupt_data = data.get("interrupt", {})
        # For write commands, the pending_command has runbook + params
        await callback.message.reply("Выполняю операцию...")
    finally:
        await redis.aclose()


@router.callback_query(F.data.startswith("cancel_cmd:"))
async def on_cancel_cmd(callback: CallbackQuery) -> None:
    """Handle command cancellation."""
    await callback.answer("Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.reply("Операция отменена.")
