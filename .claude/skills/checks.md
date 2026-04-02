# Skill: Check система (сбор сигналов)

## Базовые классы
```python
# app/checks/base.py
from dataclasses import dataclass, field
from typing import Literal
from abc import ABC, abstractmethod

@dataclass
class Signal:
    """Один найденный сигнал проблемы."""
    host: str
    severity: Literal["critical", "warning", "info"]
    problem_type: str
    evidence: str
    raw_data: dict = field(default_factory=dict)

class Check(ABC):
    """Базовый класс проверки."""
    name: str

    def __init__(self, host: str, config: dict, tools: list):
        self.host = host
        self.config = config
        self.tools  = tools   # LangChain MCP tools

    @abstractmethod
    async def run(self) -> list[Signal]:
        """Выполнить проверку, вернуть список сигналов."""
        ...
```

## Пример: проверка диска
```python
# app/checks/disk.py
import json
from app.checks.base import Check, Signal

class DiskSpaceCheck(Check):
    name = "disk_space"

    async def run(self) -> list[Signal]:
        tool = self._get_tool("ssh_exec")
        result = await tool.ainvoke({
            "host": self.host,
            "command": "df -h --output=source,pcent,target | tail -n +2",
        })

        signals = []
        for line in result.strip().splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            device, used_pct, mount = parts[0], parts[1].rstrip("%"), parts[2]

            threshold_warn = self.config.get("threshold_warning", 80)
            threshold_crit = self.config.get("threshold_critical", 90)
            paths = self.config.get("paths", ["/"])

            if mount not in paths:
                continue

            pct = int(used_pct)
            if pct >= threshold_crit:
                signals.append(Signal(
                    host=self.host,
                    severity="critical",
                    problem_type="disk_full",
                    evidence=f"Диск {mount} ({device}) заполнен на {pct}%",
                    raw_data={"mount": mount, "used_pct": pct},
                ))
            elif pct >= threshold_warn:
                signals.append(Signal(
                    host=self.host,
                    severity="warning",
                    problem_type="disk_space_low",
                    evidence=f"Диск {mount} ({device}) заполнен на {pct}%",
                    raw_data={"mount": mount, "used_pct": pct},
                ))

        return signals

    def _get_tool(self, name: str):
        return next(t for t in self.tools if t.name == name)
```

## Пример: репликация MariaDB
```python
# app/checks/mariadb.py
from app.checks.base import Check, Signal

class ReplicationCheck(Check):
    name = "mariadb_replication"

    async def run(self) -> list[Signal]:
        tool = self._get_tool("mysql_show")
        result = await tool.ainvoke({"command": "SLAVE STATUS"})

        # result — dict от MCP сервера
        if not result or result.get("Slave_IO_Running") is None:
            return []  # репликация не настроена

        signals = []
        io_running  = result.get("Slave_IO_Running") == "Yes"
        sql_running = result.get("Slave_SQL_Running") == "Yes"
        lag         = int(result.get("Seconds_Behind_Master") or 0)

        if not io_running or not sql_running:
            signals.append(Signal(
                host=self.host,
                severity="critical",
                problem_type="replication_down",
                evidence=(
                    f"Репликация остановлена: "
                    f"IO={'Yes' if io_running else 'No'}, "
                    f"SQL={'Yes' if sql_running else 'No'}\n"
                    f"Ошибка: {result.get('Last_Error', 'неизвестна')}"
                ),
                raw_data=result,
            ))
        elif lag > self.config.get("critical_lag_seconds", 300):
            signals.append(Signal(
                host=self.host,
                severity="critical",
                problem_type="replication_lag",
                evidence=f"Отставание репликации: {lag}s",
                raw_data={"lag": lag},
            ))
        elif lag > self.config.get("warning_lag_seconds", 30):
            signals.append(Signal(
                host=self.host,
                severity="warning",
                problem_type="replication_lag",
                evidence=f"Отставание репликации: {lag}s",
                raw_data={"lag": lag},
            ))

        return signals
```

## Реестр checks
```python
# app/checks/__init__.py
from app.checks.disk import DiskSpaceCheck
from app.checks.services import SystemdServiceCheck
from app.checks.mariadb import ReplicationCheck, SlowQueryCheck
from app.checks.apache import ApacheHealthCheck

CHECK_REGISTRY = {
    "disk_space":          DiskSpaceCheck,
    "systemd_services":    SystemdServiceCheck,
    "mariadb_replication": ReplicationCheck,
    "slow_query":          SlowQueryCheck,
    "apache_errors":       ApacheHealthCheck,
}
```

## Как добавить новую проверку

1. Создать файл `app/checks/my_check.py`
2. Унаследовать от `Check`, задать `name`, реализовать `run()`
3. Зарегистрировать в `CHECK_REGISTRY`
4. Добавить в `hosts.yaml` для нужных хостов

## Правила

- Check возвращает `list[Signal]` — никогда не бросает исключение наружу
- При ошибке инструмента — логировать и возвращать `[]`
- `raw_data` — полный ответ от MCP для отладки
- Check не знает о LangGraph, TG, runbooks — только собирает данные
- Пороговые значения — в конфиге, не в коде