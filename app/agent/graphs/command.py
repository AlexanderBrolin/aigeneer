"""LangGraph: text commands from Telegram -> intent classify -> read/write -> confirm -> execute."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent.nodes import get_fast_llm, get_llm
from app.agent.prompts import COMMAND_PROMPT
from app.agent.tool_provider import get_read_tools, get_write_tools
from app.agent.graphs.shared import get_checkpointer

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """
Classify the user's DevOps command. Return JSON only (no markdown).

Fields:
- intent: "read" | "write" | "db_query" | "unknown"
- summary: short description of the action
- host: server hostname or "" if unknown
- requires_confirm: true only for write operations
- runbook: runbook name for write ops or null
- params: runbook params dict if write op, else {}
- db_query_type: "servers" | "incidents" | "check_runs" | null (only for db_query intent)

Available write runbooks (dangerous, require confirmation):
restart_service, restart_replication, clear_old_logs, rotate_logs, kill_process, free_memory

Available read runbooks (safe, executed via SSH):
show_slow_queries, show_replication_status, show_top_processes, show_connections, show_disk_usage, mysql_processlist, check_backup

db_query intent — for questions about the system itself (no SSH needed):
- "какие серверы?" / "list servers" → db_query_type: "servers"
- "открытые инциденты" / "open incidents" → db_query_type: "incidents"
- "последние проверки" / "recent checks" → db_query_type: "check_runs"

Examples:
User: "check disk on web-01"
{"intent": "read", "summary": "check disk space on web-01", "host": "web-01", "requires_confirm": false, "runbook": null, "params": {}, "db_query_type": null}

User: "restart apache on web-01"
{"intent": "write", "summary": "restart apache2 on web-01", "host": "web-01", "requires_confirm": true, "runbook": "restart_service", "params": {"service": "apache2"}, "db_query_type": null}

User: "какие серверы доступны?"
{"intent": "db_query", "summary": "list available servers", "host": "", "requires_confirm": false, "runbook": null, "params": {}, "db_query_type": "servers"}

User: "покажи открытые инциденты"
{"intent": "db_query", "summary": "show open incidents", "host": "", "requires_confirm": false, "runbook": null, "params": {}, "db_query_type": "incidents"}
""".strip()


@dataclass
class CommandState:
    message: str = ""
    host: str = ""
    intent: str = ""
    db_query_type: str = ""
    tool_results: list[str] = field(default_factory=list)
    response: str = ""
    requires_confirm: bool = False
    pending_command: dict | None = None


async def classify_intent(state: CommandState) -> dict:
    """LLM classifies command intent: read vs write, extracts host and params."""
    llm = get_fast_llm()
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=CLASSIFY_PROMPT),
            HumanMessage(content=state.message),
        ])
        data = json.loads(resp.content)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("classify_intent failed: %s", exc)
        return {
            "intent": "unknown",
            "requires_confirm": False,
            "host": "",
            "pending_command": None,
        }

    result: dict = {
        "intent": data.get("intent", "unknown"),
        "host": data.get("host", ""),
        "requires_confirm": bool(data.get("requires_confirm", False)),
        "pending_command": None,
    }

    if result["intent"] == "db_query":
        result["db_query_type"] = data.get("db_query_type", "servers")

    if result["intent"] == "write" and data.get("runbook"):
        result["pending_command"] = {
            "runbook": data["runbook"],
            "params": data.get("params", {}),
            "summary": data.get("summary", ""),
        }

    return result


def route_after_classify(state: CommandState) -> Literal["execute_read", "confirm", "execute_db_query", "__end__"]:
    if state.intent == "db_query":
        return "execute_db_query"
    if state.intent == "write" and state.requires_confirm:
        return "confirm"
    if state.intent in ("read", "unknown"):
        return "execute_read"
    return END


async def execute_read_node(state: CommandState) -> dict:
    """Execute read-only commands via SSH tools + LLM synthesis."""
    from app.agent.tool_provider import get_read_tools

    host_config: dict = {}
    if state.host:
        try:
            from app.db.session import get_session
            from app.db.models import Server
            from app.agent.tool_provider import resolve_ssh_config
            from app.config import settings
            from sqlalchemy import select

            async with get_session() as session:
                row = (await session.execute(
                    select(Server).where(
                        (Server.host == state.host) | (Server.name == state.host)
                    )
                )).scalar_one_or_none()
                if row:
                    host_config = await resolve_ssh_config(session, row, settings.secret_key)
        except Exception as exc:
            logger.warning("Failed to load server config: %s", exc)

    if not host_config and state.host:
        from app.config import settings
        host_config = {
            "host": state.host,
            "ssh_user": settings.ssh_default_user,
            "ssh_port": 22,
        }

    tools = get_read_tools(host_config) if host_config else []
    llm = get_llm()
    llm_with_tools = llm.bind_tools(tools)

    messages = [
        SystemMessage(content=COMMAND_PROMPT),
        HumanMessage(content=state.message),
    ]

    try:
        resp = await llm_with_tools.ainvoke(messages)
        tool_calls = getattr(resp, "tool_calls", [])

        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name", "")
            tool_input = tool_call.get("args", {})
            matched = next((t for t in tools if t.name == tool_name), None)
            if matched:
                try:
                    output = await matched.arun(tool_input)
                    tool_results.append(f"[{tool_name}]: {output}")
                except Exception as e:
                    tool_results.append(f"[{tool_name}] error: {e}")

        if tool_results:
            # Ask LLM to synthesize tool results into a response
            synthesis_messages = messages + [resp] + [
                HumanMessage(content="\n".join(tool_results))
            ]
            final = await llm.ainvoke(synthesis_messages)
            response = final.content
        else:
            response = resp.content or "Команда выполнена."

    except Exception as exc:
        logger.error("execute_read_node error: %s", exc)
        response = f"Ошибка выполнения команды: {exc}"

    return {"response": response, "tool_results": [response]}


async def confirm_node(state: CommandState) -> dict | Command:
    """For write operations: interrupt() for Telegram confirmation."""
    if not state.requires_confirm:
        return Command(goto="execute_read")

    decision = interrupt({
        "type": "confirm_command",
        "summary": state.pending_command.get("summary", "") if state.pending_command else "",
        "runbook": state.pending_command.get("runbook") if state.pending_command else None,
        "params": state.pending_command.get("params", {}) if state.pending_command else {},
    })

    if decision.get("confirmed"):
        return Command(goto="execute_write")

    return Command(
        goto=END,
        update={"response": "Операция отменена."},
    )


async def execute_write_node(state: CommandState) -> dict:
    """Execute confirmed write runbook."""
    from app.runbooks import run_runbook

    if not state.pending_command:
        return {"response": "Нет команды для выполнения."}

    host_config: dict = {}
    if state.host:
        try:
            from app.db.session import get_session
            from app.db.models import Server
            from app.agent.tool_provider import resolve_ssh_config
            from app.config import settings
            from sqlalchemy import select

            async with get_session() as session:
                row = (await session.execute(
                    select(Server).where(
                        (Server.host == state.host) | (Server.name == state.host)
                    )
                )).scalar_one_or_none()
                if row:
                    host_config = await resolve_ssh_config(session, row, settings.secret_key)
        except Exception as exc:
            logger.warning("Failed to load server config for write: %s", exc)

    tools = get_write_tools(host_config) if host_config else []
    runbook_name = state.pending_command["runbook"]
    params = state.pending_command.get("params", {})

    try:
        result = await run_runbook(runbook_name, params, tools)
        response = f"✅ {result.message}"
        if result.details:
            response += f"\n\n{result.details}"
    except Exception as exc:
        logger.error("execute_write_node error: %s", exc)
        response = f"❌ Ошибка выполнения: {exc}"

    return {"response": response}


async def execute_db_query_node(state: CommandState) -> dict:
    """Handle DB-only queries: server list, incidents, check runs."""
    from app.db.session import get_session
    from app.db.models import Server, Incident, CheckRun
    from sqlalchemy import select

    query_type = state.db_query_type or "servers"

    async with get_session() as session:
        if query_type == "servers":
            result = await session.execute(select(Server).order_by(Server.name))
            servers = result.scalars().all()
            if not servers:
                return {"response": "Нет добавленных серверов."}
            lines = ["<b>Серверы:</b>"]
            for s in servers:
                status = "✅" if s.enabled else "⏸"
                last = s.last_check_at.strftime("%d.%m %H:%M") if s.last_check_at else "—"
                lines.append(f"{status} <b>{s.name}</b> ({s.host}) — последняя проверка: {last}")
            return {"response": "\n".join(lines)}

        elif query_type == "incidents":
            result = await session.execute(
                select(Incident)
                .where(Incident.status.in_(["new", "notified"]))
                .order_by(Incident.created_at.desc())
                .limit(20)
            )
            incidents = result.scalars().all()
            if not incidents:
                return {"response": "Открытых инцидентов нет. 👍"}
            lines = [f"<b>Открытые инциденты ({len(incidents)}):</b>"]
            for inc in incidents:
                emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(inc.severity, "⚪")
                dt = inc.created_at.strftime("%d.%m %H:%M") if inc.created_at else ""
                lines.append(f"{emoji} [{inc.host}] {inc.problem_type} — {dt}")
            return {"response": "\n".join(lines)}

        elif query_type == "check_runs":
            result = await session.execute(
                select(CheckRun)
                .order_by(CheckRun.started_at.desc())
                .limit(10)
            )
            runs = result.scalars().all()
            if not runs:
                return {"response": "Проверок пока не было."}
            lines = ["<b>Последние проверки:</b>"]
            for r in runs:
                emoji = {"ok": "✅", "incident": "⚠️", "error": "❌", "running": "🔄"}.get(r.status, "❓")
                dt = r.started_at.strftime("%d.%m %H:%M") if r.started_at else ""
                lines.append(f"{emoji} [{r.host}] {r.check_name} — {r.status} ({dt})")
            return {"response": "\n".join(lines)}

    return {"response": "Неизвестный тип запроса."}


# Build the graph
_builder = StateGraph(CommandState)
_builder.add_node("classify", classify_intent)
_builder.add_node("execute_read", execute_read_node)
_builder.add_node("confirm", confirm_node)
_builder.add_node("execute_write", execute_write_node)
_builder.add_node("execute_db_query", execute_db_query_node)

_builder.add_edge(START, "classify")
_builder.add_conditional_edges("classify", route_after_classify)
_builder.add_edge("execute_read", END)
_builder.add_edge("execute_write", END)
_builder.add_edge("execute_db_query", END)


async def get_command_graph():
    checkpointer = await get_checkpointer()
    return _builder.compile(checkpointer=checkpointer)
