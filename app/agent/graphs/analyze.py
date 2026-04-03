"""LangGraph: signals -> incidents -> interrupt/resume -> runbook execution."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent.nodes import get_llm
from app.agent.prompts import NORMALIZE_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class AnalyzeState:
    host: str = ""
    signals: list[dict] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)
    pending_action: dict | None = None
    check_run_id: int | None = None
    host_config: dict = field(default_factory=dict)
    runbook_result: dict | None = None


async def normalize_node(state: AnalyzeState) -> dict:
    """LLM normalizes signals into incident cards."""
    if not state.signals:
        return {"incidents": []}

    llm = get_llm()
    response = await llm.ainvoke([
        SystemMessage(content=NORMALIZE_PROMPT),
        HumanMessage(content=f"Сигналы с хоста {state.host}:\n{json.dumps(state.signals, ensure_ascii=False, indent=2)}"),
    ])

    try:
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        incidents = json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse LLM response: %s", response.content[:200])
        return {"incidents": []}

    # Inject host_config into incident action params for SSH access
    ssh_params = {
        k: v for k, v in state.host_config.items()
        if k in ("ssh_user", "ssh_key_content", "ssh_port")
    }
    for incident in incidents:
        for action in incident.get("dangerous_actions", []):
            action["params"].update(ssh_params)
        for action in incident.get("safe_actions", []):
            action["params"].update(ssh_params)

    return {"incidents": incidents}


def route_incidents(state: AnalyzeState) -> Literal["notify_node", "__end__"]:
    if state.incidents:
        return "notify_node"
    return END


async def notify_node(state: AnalyzeState) -> Command:
    """For each incident with dangerous_actions: interrupt for TG confirmation."""
    incidents = state.incidents
    if not incidents:
        return Command(goto=END)

    for incident in incidents:
        if incident.get("dangerous_actions"):
            decision = interrupt({
                "incident": incident,
                "host": state.host,
            })
            return Command(
                goto="execute_node",
                update={"pending_action": {
                    "runbook": decision["runbook"],
                    "params": decision.get("params", {}),
                    "incident_id": incident.get("db_id"),
                }},
            )

    return Command(goto=END)


async def execute_node(state: AnalyzeState) -> dict:
    """Execute confirmed runbook."""
    from app.runbooks import run_runbook
    from app.agent.tool_provider import get_write_tools

    action = state.pending_action
    if not action or not action.get("runbook"):
        return {"incidents": state.incidents}

    tools = get_write_tools(state.host_config)
    result = await run_runbook(action["runbook"], action["params"], tools)
    logger.info("Runbook %s result: %s", action["runbook"], result.message)

    return {
        "incidents": state.incidents,
        "runbook_result": {
            "runbook": action["runbook"],
            "success": result.success,
            "message": result.message,
            "details": result.details or "",
        },
    }


# Build the graph
builder = StateGraph(AnalyzeState)
builder.add_node("normalize", normalize_node)
builder.add_node("notify_node", notify_node)
builder.add_node("execute_node", execute_node)
builder.add_edge(START, "normalize")
builder.add_conditional_edges("normalize", route_incidents)
builder.add_edge("execute_node", END)


async def resume_analyze_graph(thread_id: str, command) -> dict:
    """Resume an interrupted analyze graph thread (e.g. from a TG button callback).

    Uses a fresh Redis connection scoped to this call so it works in both
    the aiogram event loop (persistent) and Celery tasks (new loop per task).
    """
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver
    from app.config import settings

    async with AsyncRedisSaver.from_conn_string(
        settings.redis_url, ttl={"default_ttl": 1440}
    ) as checkpointer:
        await checkpointer.asetup()
        graph = builder.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        return await graph.ainvoke(command, config=config)


async def run_analyze_graph(state: AnalyzeState, config: dict) -> dict:
    """Run the analyze graph with a fresh Redis checkpointer scoped to this call.

    Each Celery task calls asyncio.run(), creating a new event loop.
    We must open and close the Redis connection *within* that loop to avoid
    'Buffer is closed' errors from stale connections of a previous loop.
    """
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver
    from app.config import settings

    async with AsyncRedisSaver.from_conn_string(
        settings.redis_url, ttl={"default_ttl": 1440}
    ) as checkpointer:
        await checkpointer.asetup()
        graph = builder.compile(checkpointer=checkpointer)
        return await graph.ainvoke(state, config=config)
