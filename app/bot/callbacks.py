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
from app.services.incident import update_incident_status

logger = logging.getLogger(__name__)

# When a runbook fails, offer these alternatives in addition to "retry".
# Each entry is {"label": str, "runbook": str, "params": dict}.
RUNBOOK_FALLBACKS: dict[str, list[dict]] = {
    "restart_replication": [
        {
            "label": "📋 Показать статус репликации",
            "runbook": "show_replication_status",
            "params": {},
        },
    ],
    "restart_service": [],
}


def incident_keyboard(thread_id: str, incident: dict):
    """Generate inline keyboard from incident dangerous_actions.

    Each dangerous action gets a button. An "Ignore" button is always appended.
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


def _failure_keyboard(msg_id: int, runbook_name: str):
    """Build retry + alternatives keyboard after a runbook failure."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 Попробовать снова",
        callback_data=f"retry:{msg_id}",
    )
    for alt in RUNBOOK_FALLBACKS.get(runbook_name, []):
        builder.button(
            text=alt["label"],
            callback_data=f"retry:{msg_id}:alt:{alt['runbook']}",
        )
    builder.adjust(1)
    return builder.as_markup()


async def _get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def _run_and_reply(
    callback: CallbackQuery,
    runbook_name: str,
    params: dict,
    host_config: dict,
    redis: Redis,
    incident_db_id: int | None = None,
) -> None:
    """Execute a runbook and send the result as a reply, with retry keyboard on failure."""
    from app.runbooks import run_runbook
    from app.agent.tool_provider import get_write_tools

    tools = get_write_tools(host_config)
    result = await run_runbook(runbook_name, params, tools)

    icon = "✅" if result.success else "❌"
    reply_text = f"{icon} <b>{result.message}</b>"
    if result.details:
        reply_text += f"\n\n<pre>{result.details[:2000]}</pre>"

    if result.success:
        await callback.message.reply(reply_text, parse_mode="HTML")
    else:
        # Store retry context keyed by the reply message we're about to send.
        # We don't know the message_id yet — store under a temp key and update after send.
        retry_data = json.dumps(
            {"runbook": runbook_name, "params": params, "host_config": host_config,
             "incident_db_id": incident_db_id},
            ensure_ascii=False,
        )
        # Key by current (trigger) message id; the retry handler reads it by this key.
        retry_key = f"retry_ctx:{callback.message.message_id}"
        await redis.setex(retry_key, 3600, retry_data)

        keyboard = _failure_keyboard(callback.message.message_id, runbook_name)
        await callback.message.reply(reply_text, parse_mode="HTML", reply_markup=keyboard)


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
        incident_db_id = incident.get("db_id")
        await callback.answer("Выполняю...")

        # Remove keyboard from the message
        await callback.message.edit_reply_markup(reply_markup=None)

        # Mark incident as actioned so next check cycle can re-notify if needed
        if incident_db_id:
            try:
                await update_incident_status(incident_db_id, "actioned", action["runbook"])
            except Exception:
                logger.exception("Failed to mark incident %s as actioned", incident_db_id)

        # Resume the LangGraph — execute_node runs the runbook and stores result in state
        final_state = await resume_analyze_graph(
            thread_id,
            Command(resume={"runbook": action["runbook"], "params": action.get("params", {})}),
        )

        rb_result = final_state.get("runbook_result") if isinstance(final_state, dict) else None
        host_config = final_state.get("host_config", {}) if isinstance(final_state, dict) else {}

        if rb_result:
            icon = "✅" if rb_result["success"] else "❌"
            reply_text = f"{icon} <b>{rb_result['message']}</b>"
            if rb_result.get("details"):
                reply_text += f"\n\n<pre>{rb_result['details'][:2000]}</pre>"

            if rb_result["success"]:
                await callback.message.reply(reply_text, parse_mode="HTML")
            else:
                # Offer retry and alternatives
                retry_data = json.dumps(
                    {
                        "runbook": action["runbook"],
                        "params": action.get("params", {}),
                        "host_config": host_config,
                        "incident_db_id": incident_db_id,
                    },
                    ensure_ascii=False,
                )
                retry_key = f"retry_ctx:{callback.message.message_id}"
                await redis.setex(retry_key, 3600, retry_data)

                keyboard = _failure_keyboard(callback.message.message_id, action["runbook"])
                await callback.message.reply(reply_text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await callback.message.reply(
                f"Runbook <b>{action['runbook']}</b> выполнен.", parse_mode="HTML"
            )
    finally:
        await redis.aclose()


@router.callback_query(F.data.startswith("retry:"))
async def on_retry(callback: CallbackQuery) -> None:
    """Handle retry/alternative button after runbook failure."""
    # Two forms:
    #   retry:{orig_msg_id}              → retry same runbook
    #   retry:{orig_msg_id}:alt:{name}   → run alternative runbook
    parts = callback.data.split(":", 3)
    orig_msg_id = parts[1]
    alt_runbook: str | None = parts[3] if len(parts) == 4 else None

    redis = await _get_redis()
    try:
        retry_ctx_raw = await redis.get(f"retry_ctx:{orig_msg_id}")
        if not retry_ctx_raw:
            await callback.answer("Данные устарели", show_alert=True)
            return

        ctx = json.loads(retry_ctx_raw)
        runbook_name = alt_runbook if alt_runbook else ctx["runbook"]
        params = ctx["params"] if not alt_runbook else {}
        host_config = ctx["host_config"]

        await callback.answer("Выполняю...")
        await callback.message.edit_reply_markup(reply_markup=None)

        # Keep incident marked as actioned so dedup bypass stays active
        incident_db_id = ctx.get("incident_db_id")
        if incident_db_id:
            try:
                await update_incident_status(incident_db_id, "actioned", runbook_name)
            except Exception:
                logger.exception("Failed to mark incident %s as actioned in retry", incident_db_id)

        await _run_and_reply(callback, runbook_name, params, host_config, redis)
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
        raw = await redis.get(f"tg_thread:{callback.message.message_id}")
        if raw:
            data = json.loads(raw)
            incident_db_id = data.get("incident", {}).get("db_id")
            if incident_db_id:
                await update_incident_status(incident_db_id, "ignored")

        # Resume graph indicating ignore
        await resume_analyze_graph(thread_id, Command(resume={"runbook": None}))

        await callback.message.reply("Проигнорировано.")
    finally:
        await redis.aclose()
