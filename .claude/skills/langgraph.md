# Skill: LangGraph (два графа)

## analyze_graph — мониторинг
```python
# app/agent/graphs/analyze.py
from dataclasses import dataclass, field
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langchain_core.messages import HumanMessage, SystemMessage

@dataclass
class AnalyzeState:
    host: str
    signals: list[dict] = field(default_factory=list)   # Signal → dict
    incidents: list[dict] = field(default_factory=list)  # Incident → dict
    pending_action: dict | None = None   # {runbook, params, label}
    check_run_id: int | None = None

async def normalize_node(state: AnalyzeState) -> dict:
    """LLM нормализует сигналы в карточки инцидентов."""
    from app.agent.prompts import NORMALIZE_PROMPT
    from app.agent.nodes import get_llm
    import json

    if not state.signals:
        return {"incidents": []}

    llm = get_llm()
    response = await llm.ainvoke([
        SystemMessage(NORMALIZE_PROMPT),
        HumanMessage(f"Сигналы с хоста {state.host}:\n{json.dumps(state.signals, ensure_ascii=False, indent=2)}"),
    ])

    # Ожидаем JSON массив Incident карточек
    incidents = json.loads(response.content)
    return {"incidents": incidents}

def route_incidents(state: AnalyzeState) -> Literal["notify_node", END]:
    if state.incidents:
        return "notify_node"
    return END

async def notify_node(state: AnalyzeState) -> Command:
    """Для каждого инцидента: safe_actions сразу, dangerous — interrupt."""
    incidents = state.incidents
    if not incidents:
        return Command(goto=END)

    # Берём первый необработанный инцидент с dangerous_actions
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
    """Выполнить подтверждённый runbook."""
    from app.runbooks import run_runbook
    from app.agent.mcp_client import get_write_tools

    action = state.pending_action
    tools  = await get_write_tools()
    result = await run_runbook(action["runbook"], action["params"], tools)

    return {"incidents": state.incidents}  # результат через TG уйдёт из bot callback

builder = StateGraph(AnalyzeState)
builder.add_node("normalize", normalize_node)
builder.add_node("notify", notify_node)
builder.add_node("execute", execute_node)
builder.add_edge(START, "normalize")
builder.add_conditional_edges("normalize", route_incidents)
builder.add_edge("execute", END)

async def get_analyze_graph():
    from app.agent.graphs.shared import get_checkpointer
    checkpointer = await get_checkpointer()
    return builder.compile(checkpointer=checkpointer)
```

## Формат Incident карточки (для LLM промпта)

LLM должен вернуть JSON массив:
```json
[
  {
    "host": "web-01",
    "severity": "critical",
    "problem_type": "replication_down",
    "evidence": "Репликация остановлена: IO=No, SQL=Yes\nОшибка: ...",
    "safe_actions": [],
    "dangerous_actions": [
      {
        "label": "🔄 Перезапустить репликацию",
        "runbook": "restart_replication",
        "params": {"host": "web-01"}
      }
    ]
  }
]
```

## Shared checkpointer
```python
# app/agent/graphs/shared.py
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from app.config import settings

_checkpointer = None

async def get_checkpointer() -> AsyncRedisSaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = AsyncRedisSaver.from_conn_string(
            settings.REDIS_URL,
            ttl={"default_ttl": 1440},
        )
        await _checkpointer.asetup()
    return _checkpointer
```

## command_graph — команды от человека

Отдельный граф, аналогичный предыдущей версии:
- intent_node → classify (read/write/unclear)
- read: tool_node → ответить
- write: interrupt → confirm → execute_node

## Правила

- Redis-stack (RedisJSON + RediSearch) обязателен для checkpointer
- `thread_id` — UUID per check_run, хранить в БД incidents.thread_id
- Interrupt payload должен быть JSON-serializable
- Один shared checkpointer instance на весь процесс
- analyze_graph и command_graph — разные графы, разные thread_id namespace