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
- intent: "read" | "write" | "unknown"
- summary: short description of the action
- host: server hostname or "" if unknown
- requires_confirm: true only for write operations
- runbook: runbook name if write op (restart_service|restart_replication|clear_old_logs|show_slow_queries) or null
- params: runbook params dict if write op, else {}

Examples:
User: "check disk on web-01"
{"intent": "read", "summary": "check disk space on web-01", "host": "web-01", "requires_confirm": false, "runbook": null, "params": {}}

User: "restart apache on web-01"
{"intent": "write", "summary": "restart apache2 on web-01", "host": "web-01", "requires_confirm": true, "runbook": "restart_service", "params": {"service": "apache2", "host": "web-01"}}
""".strip()


@dataclass
class CommandState:
    message: str = ""
    host: str = ""
    intent: str = ""
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

    if result["intent"] == "write" and data.get("runbook"):
        result["pending_command"] = {
            "runbook": data["runbook"],
            "params": data.get("params", {}),
            "summary": data.get("summary", ""),
        }

    return result


def route_after_classify(state: CommandState) -> Literal["execute_read", "confirm", "__end__"]:
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
        # Try to load SSH config from DB
        try:
            from app.db.session import get_session
            from app.db.models import Server
            from sqlalchemy import select

            async with get_session() as session:
                row = (await session.execute(
                    select(Server).where(Server.host == state.host)
                )).scalar_one_or_none()
                if row:
                    host_config = {
                        "host": row.host,
                        "ssh_user": row.ssh_user or "deploy",
                        "ssh_key_path": row.ssh_key_path or "",
                        "ssh_port": row.ssh_port or 22,
                    }
        except Exception as exc:
            logger.warning("Failed to load server config: %s", exc)

    if not host_config and state.host:
        from app.config import settings
        host_config = {
            "host": state.host,
            "ssh_user": settings.ssh_default_user,
            "ssh_key_path": settings.ssh_default_key_path,
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
            from sqlalchemy import select

            async with get_session() as session:
                row = (await session.execute(
                    select(Server).where(Server.host == state.host)
                )).scalar_one_or_none()
                if row:
                    host_config = {
                        "host": row.host,
                        "ssh_user": row.ssh_user or "deploy",
                        "ssh_key_path": row.ssh_key_path or "",
                        "ssh_port": row.ssh_port or 22,
                    }
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


# Build the graph
_builder = StateGraph(CommandState)
_builder.add_node("classify", classify_intent)
_builder.add_node("execute_read", execute_read_node)
_builder.add_node("confirm", confirm_node)
_builder.add_node("execute_write", execute_write_node)

_builder.add_edge(START, "classify")
_builder.add_conditional_edges("classify", route_after_classify)
_builder.add_edge("execute_read", END)
_builder.add_edge("execute_write", END)


async def get_command_graph():
    checkpointer = await get_checkpointer()
    return _builder.compile(checkpointer=checkpointer)
