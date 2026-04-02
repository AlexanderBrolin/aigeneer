# Skill: Runbooks (детерминированное исполнение)

Runbook — детерминированная функция. Не LLM. Знает что именно делать.
Получает параметры из карточки инцидента, выполняет через MCP/SSH.

## Базовый класс
```python
# app/runbooks/base.py
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Literal

@dataclass
class RunbookResult:
    success: bool
    message: str              # для TG — что было сделано
    details: str = ""         # полный вывод команд

class Runbook(ABC):
    name: str
    is_dangerous: bool = False   # требует confirm в TG

    def __init__(self, tools: list):
        self.tools = tools

    @abstractmethod
    async def execute(self, params: dict) -> RunbookResult:
        ...

    def _get_tool(self, name: str):
        return next(t for t in self.tools if t.name == name)
```

## Пример: рестарт сервиса
```python
# app/runbooks/restart_service.py
from app.runbooks.base import Runbook, RunbookResult

class RestartServiceRunbook(Runbook):
    name = "restart_service"
    is_dangerous = True  # требует confirm

    async def execute(self, params: dict) -> RunbookResult:
        host    = params["host"]
        service = params["service"]
        tool    = self._get_tool("ssh_systemctl_restart")

        result = await tool.ainvoke({"host": host, "service": service})

        if result.get("exit_code") == 0:
            return RunbookResult(
                success=True,
                message=f"✅ Сервис `{service}` на `{host}` перезапущен",
                details=result.get("stdout", ""),
            )
        return RunbookResult(
            success=False,
            message=f"❌ Не удалось перезапустить `{service}` на `{host}`",
            details=result.get("stderr", ""),
        )
```

## Пример: рестарт репликации
```python
# app/runbooks/restart_replication.py
from app.runbooks.base import Runbook, RunbookResult

class RestartReplicationRunbook(Runbook):
    name = "restart_replication"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        host = params["host"]
        stop_tool  = self._get_tool("mysql_replication")
        start_tool = self._get_tool("mysql_replication")

        await stop_tool.ainvoke({"host": host, "action": "stop"})
        result = await start_tool.ainvoke({"host": host, "action": "start"})

        # Проверяем статус после старта
        show_tool = self._get_tool("mysql_show")
        status = await show_tool.ainvoke({"command": "SLAVE STATUS"})

        io_ok  = status.get("Slave_IO_Running") == "Yes"
        sql_ok = status.get("Slave_SQL_Running") == "Yes"

        if io_ok and sql_ok:
            return RunbookResult(
                success=True,
                message=f"✅ Репликация на `{host}` перезапущена успешно",
                details=f"IO: Yes, SQL: Yes",
            )
        return RunbookResult(
            success=False,
            message=f"❌ Репликация не восстановилась на `{host}`",
            details=f"IO: {'Yes' if io_ok else 'No'}, SQL: {'Yes' if sql_ok else 'No'}\n"
                    f"Last error: {status.get('Last_Error', '')}",
        )
```

## Пример: показать slow queries (read-only, без confirm)
```python
# app/runbooks/show_slow_queries.py
from app.runbooks.base import Runbook, RunbookResult

class ShowSlowQueriesRunbook(Runbook):
    name = "show_slow_queries"
    is_dangerous = False  # можно без confirm

    async def execute(self, params: dict) -> RunbookResult:
        host     = params["host"]
        lines    = params.get("lines", 50)
        log_path = params.get("log_path", "/var/log/mysql/slow.log")
        tool     = self._get_tool("ssh_read_file")

        result = await tool.ainvoke({
            "host": host,
            "path": log_path,
            "tail_lines": lines,
        })

        return RunbookResult(
            success=True,
            message=f"📋 Последние {lines} строк slow query log на `{host}`",
            details=result.get("content", "Файл пуст или недоступен"),
        )
```

## Реестр runbooks
```python
# app/runbooks/__init__.py
from app.runbooks.restart_service import RestartServiceRunbook
from app.runbooks.restart_replication import RestartReplicationRunbook
from app.runbooks.clear_old_logs import ClearOldLogsRunbook
from app.runbooks.show_slow_queries import ShowSlowQueriesRunbook

RUNBOOK_REGISTRY = {
    "restart_service":     RestartServiceRunbook,
    "restart_replication": RestartReplicationRunbook,
    "clear_old_logs":      ClearOldLogsRunbook,
    "show_slow_queries":   ShowSlowQueriesRunbook,
}

async def run_runbook(name: str, params: dict, tools: list) -> RunbookResult:
    cls = RUNBOOK_REGISTRY.get(name)
    if not cls:
        return RunbookResult(success=False, message=f"Runbook `{name}` не найден")
    return await cls(tools).execute(params)
```

## Правила

- Runbook — не LLM, детерминированный код
- `is_dangerous=True` → кнопка в TG, подтверждение через interrupt
- `is_dangerous=False` → можно выполнить автоматически или по запросу
- Runbook не знает о LangGraph и TG — только params → RunbookResult
- Всегда проверять результат после выполнения (не доверять exit_code)
- Логировать полный output в `details` для диагностики