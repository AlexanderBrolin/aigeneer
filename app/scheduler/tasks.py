"""Celery tasks for scheduled infrastructure checks."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.graphs.analyze import AnalyzeState, run_analyze_graph
from app.agent.tool_provider import get_read_tools
from app.bot.handlers import notify_incident
from app.bot.router import get_bot
from app.checks import CHECK_REGISTRY
from app.config import settings
from app.db.models import CheckRun, Server
from app.db.session import get_session
from app.scheduler.worker import celery_app
from app.services.incident import find_active_incident, save_incident, update_incident_status

logger = logging.getLogger(__name__)


async def _notify_tg(incident: dict, thread_id: str, host: str, host_config: dict | None = None) -> None:
    """Send incident notification to Telegram."""
    from app.services.settings import SettingsService

    svc = SettingsService(secret_key=settings.secret_key)
    async with get_session() as session:
        app_settings = await svc.get_cached(session)

    chat_id = app_settings.get("tg_chat_id") or settings.tg_chat_id
    bot_token = app_settings.get("tg_bot_token") or settings.tg_bot_token

    if not chat_id or not bot_token:
        logger.warning("TG not configured, skipping notification")
        return
    bot = get_bot()
    await notify_incident(
        bot=bot,
        chat_id=chat_id,
        thread_id=thread_id,
        interrupt_data={"incident": incident, "host": host, "host_config": host_config or {}},
    )


@celery_app.task(name="app.scheduler.tasks.run_all_checks")
def run_all_checks() -> dict:
    """Query all enabled servers and dispatch collect_task for each."""
    return asyncio.run(_run_all_checks_async())


async def _run_all_checks_async() -> dict:
    async with get_session() as session:
        result = await session.execute(
            select(Server)
            .where(Server.enabled.is_(True))
            .options(selectinload(Server.checks))
        )
        servers = result.scalars().all()

    dispatched = []
    for server in servers:
        enabled_checks = [c for c in server.checks if c.enabled]
        if not enabled_checks:
            logger.info("Server %s has no enabled checks, skipping", server.name)
            continue
        collect_task.delay(server.id)
        dispatched.append(server.name)

    logger.info("Dispatched collect_task for %d servers: %s", len(dispatched), dispatched)
    return {"dispatched": dispatched}


@celery_app.task(name="app.scheduler.tasks.collect_task", bind=True, max_retries=1)
def collect_task(self, server_id: int) -> dict:
    """Run all enabled checks for a server, analyze signals, create incidents."""
    try:
        return asyncio.run(_collect_task_async(server_id))
    except Exception as exc:
        logger.exception("collect_task failed for server_id=%s", server_id)
        raise self.retry(exc=exc, countdown=30)


async def _collect_task_async(server_id: int) -> dict:
    # Load server with checks
    async with get_session() as session:
        result = await session.execute(
            select(Server)
            .where(Server.id == server_id)
            .options(selectinload(Server.checks))
        )
        server = result.scalar_one_or_none()
        if server is None:
            logger.error("Server id=%s not found", server_id)
            return {"error": f"Server {server_id} not found"}

        # Snapshot server data before leaving the session
        server_name = server.name
        server_host = server.host
        from app.agent.tool_provider import resolve_ssh_config
        host_config = await resolve_ssh_config(session, server, settings.secret_key)
        enabled_checks = [
            {"check_name": c.check_name, "params": dict(c.params) if c.params else {}}
            for c in server.checks
            if c.enabled
        ]

        # Update last_check_at
        server.last_check_at = datetime.now(timezone.utc)

    if not enabled_checks:
        logger.info("Server %s has no enabled checks", server_name)
        return {"server": server_name, "status": "no_checks"}

    # Create CheckRun row for this collection pass
    async with get_session() as session:
        check_run = CheckRun(
            server_id=server_id,
            host=server_host,
            check_name="all",
            status="running",
            signal_count=0,
        )
        session.add(check_run)
        await session.flush()
        check_run_id = check_run.id

    # Collect signals from all enabled checks
    all_signals: list[dict] = []
    tools = get_read_tools(host_config)

    for check_info in enabled_checks:
        check_cls = CHECK_REGISTRY.get(check_info["check_name"])
        if check_cls is None:
            logger.warning("Unknown check %s for server %s", check_info["check_name"], server_name)
            continue

        try:
            ssh_user = host_config.get("ssh_user", "root")
            check_instance = check_cls(
                host=server_host,
                config=check_info["params"],
                tools=tools,
                use_sudo=ssh_user != "root",
            )
            signals = await check_instance.run()
            for sig in signals:
                all_signals.append({
                    "host": sig.host,
                    "severity": sig.severity,
                    "problem_type": sig.problem_type,
                    "evidence": sig.evidence,
                    "raw_data": sig.raw_data,
                })
        except Exception:
            logger.exception("Check %s failed on server %s", check_info["check_name"], server_name)

    # Update CheckRun with signal count
    final_status = "ok"

    if all_signals:
        final_status = "incident"

        # Invoke analyze graph
        try:
            thread_id = f"check-{check_run_id}-{uuid.uuid4().hex[:8]}"
            config = {"configurable": {"thread_id": thread_id}}

            state = AnalyzeState(
                host=server_host,
                signals=all_signals,
                check_run_id=check_run_id,
                host_config=host_config,
            )

            graph_result = await run_analyze_graph(state, config)

            # Save incidents and send TG notifications
            if isinstance(graph_result, dict):
                incidents = graph_result.get("incidents", [])
            else:
                incidents = getattr(graph_result, "incidents", [])

            for inc in incidents:
                if not isinstance(inc, dict):
                    continue

                problem_type = inc.get("problem_type", "unknown")

                # Deduplication: skip if an open incident already exists.
                # Re-notify only if it was previously actioned (fix was attempted).
                existing = await find_active_incident(server_host, problem_type)
                if existing is not None:
                    logger.info(
                        "Skipping duplicate incident %s on %s (existing id=%s status=%s)",
                        problem_type, server_host, existing.id, existing.status,
                    )
                    continue

                db_id = await save_incident(
                    check_run_id=check_run_id,
                    thread_id=thread_id,
                    host=server_host,
                    severity=inc.get("severity", "warning"),
                    problem_type=problem_type,
                    evidence=inc.get("evidence", ""),
                )
                inc["db_id"] = db_id

                # Send TG notification (best-effort)
                tg_sent = False
                try:
                    await _notify_tg(inc, thread_id, server_host, host_config)
                    tg_sent = True
                except Exception:
                    logger.exception("Failed to send TG notification for incident %s", db_id)

                # Mark as notified in separate try so a DB hiccup doesn't look like a TG failure
                if tg_sent:
                    try:
                        await update_incident_status(db_id, "notified")
                    except Exception:
                        logger.warning(
                            "Could not mark incident %s as notified (non-fatal)", db_id
                        )

        except Exception:
            logger.exception("Analyze graph failed for server %s", server_name)
            final_status = "error"

    # Finalize CheckRun
    async with get_session() as session:
        result = await session.execute(
            select(CheckRun).where(CheckRun.id == check_run_id)
        )
        run = result.scalar_one()
        run.status = final_status
        run.signal_count = len(all_signals)
        run.finished_at = datetime.now(timezone.utc)

    logger.info(
        "collect_task done for %s: %d signals, status=%s",
        server_name, len(all_signals), final_status,
    )
    return {
        "server": server_name,
        "signal_count": len(all_signals),
        "status": final_status,
    }
