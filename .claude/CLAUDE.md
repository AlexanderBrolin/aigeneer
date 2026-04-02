# ops-agent — Proactive Infrastructure Monitoring Agent

## Назначение

Агент проактивного мониторинга инфраструктуры. Сам ходит по серверам,
собирает сигналы, нормализует в инциденты, согласует действия через Telegram.

Два режима:
1. **Мониторинг по расписанию** — Celery Beat → сбор сигналов → инцидент → TG
2. **Команды от человека** — Telegram → агент → ответ / подтверждение

Zabbix не используется. Агент сам является системой мониторинга.

## Что мониторим (первый кейс)

Debian-серверы с Apache2 / MariaDB:

**Системные метрики:**
- Свободное место на дисках (`df -h`)
- Загрузка CPU / памяти (`top`, `/proc/meminfo`)
- Состояние systemd сервисов: `apache2`, `mariadb`

**MariaDB:**
- Статус репликации (`SHOW SLAVE STATUS`)
- Медленные запросы (`slow_query.log`) — по запросу
- Базовый health (`SHOW STATUS`, `SHOW PROCESSLIST`)

**Apache2:**
- Статус (`systemctl status apache2`)
- Последние ошибки в `/var/log/apache2/error.log`
- Число активных соединений

**Что именно проверять** задаётся в `app/checks/` — набор check-функций,
каждая возвращает список сигналов. Инструкции по новым проверкам — в `checks/README.md`.

## Карточка инцидента (ключевая структура)
```python
@dataclass
class Incident:
    host: str
    severity: Literal["critical", "warning", "info"]
    problem_type: str          # "disk_full", "replication_lag", "service_down", ...
    evidence: str              # что именно найдено (человекочитаемо)
    safe_actions: list[Action] # можно без confirm
    dangerous_actions: list[Action]  # требуют кнопки в TG

@dataclass
class Action:
    label: str           # текст кнопки в TG
    runbook: str         # имя runbook из app/runbooks/
    params: dict         # параметры для runbook
```

Карточка — контракт между сбором сигналов и реакцией.
LLM участвует в анализе и формировании карточки, но не в исполнении.

## Runbooks

Детерминированные скрипты исполнения. **Не LLM.** Каждый runbook — функция
которая знает что именно делать через SSH/MCP.
```
app/runbooks/
├── restart_service.py     # systemctl restart <service>
├── restart_replication.py # STOP/START SLAVE
├── clear_old_logs.py      # find + rm старых логов
├── show_slow_queries.py   # tail slow_query.log (read-only)
└── README.md              # как добавить runbook
```

## Архитектура
```
Celery Beat (расписание)
    → collect_task(host, check_list)
        → MCP/SSH: сбор сигналов
        → LangGraph: analyze_graph
            → LLM: нормализация в Incident карточки
            → safe_actions: выполнить автоматически (опционально)
            → dangerous_actions: interrupt() → TG уведомление + кнопки
                → инженер: [кнопка] → resume → runbook → результат

TG Bot (команды)
    → command_graph
        → LLM: понять намерение
        → MCP/SSH: собрать данные / выполнить (с confirm)
```

## MCP инструменты (SSH-based)

Все взаимодействия с серверами — через SSH MCP сервер.

**Read-only (сбор сигналов):**
- `ssh_exec` — выполнить команду, вернуть stdout/stderr
- `ssh_read_file` — прочитать файл (логи, конфиги)
- `ssh_systemctl_status` — статус сервиса

**Write (только после confirm):**
- `ssh_systemctl_restart` — рестарт сервиса
- `ssh_exec_privileged` — выполнить команду с sudo

Отдельно: MCP для MariaDB (уже есть `mcp-mysql.p4i.ru`).

## Стек

- **Python 3.12-slim**
- **LangGraph** — два графа: `analyze_graph`, `command_graph`
- **langchain-mcp-adapters** — SSH MCP + MySQL MCP как LangChain tools
- **langchain-openai** — LLM через AITUNNEL
- **langgraph-checkpoint-redis** — персистентность interrupt
- **Celery + Celery Beat** — расписание проверок
- **Redis** — broker + LangGraph checkpoints (redis-stack)
- **FastAPI** — healthcheck endpoint, опционально webhook
- **Aiogram 3.x** — Telegram бот
- **SQLAlchemy 2.x async + Alembic** — хранение инцидентов
- **MariaDB** (в compose) — БД агента

## Структура проекта
```
ops-agent/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── alembic/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db/
│   │   ├── models.py        # Incident, Action, CheckRun
│   │   └── session.py
│   ├── checks/
│   │   ├── README.md        # как добавить проверку
│   │   ├── base.py          # базовый класс Check, Signal
│   │   ├── disk.py          # DiskSpaceCheck
│   │   ├── services.py      # SystemdServiceCheck
│   │   ├── mariadb.py       # ReplicationCheck, SlowQueryCheck
│   │   └── apache.py        # ApacheHealthCheck
│   ├── runbooks/
│   │   ├── README.md        # как добавить runbook
│   │   ├── base.py          # базовый класс Runbook
│   │   ├── restart_service.py
│   │   ├── restart_replication.py
│   │   ├── clear_old_logs.py
│   │   └── show_slow_queries.py
│   ├── agent/
│   │   ├── graphs/
│   │   │   ├── analyze.py   # LangGraph: сигналы → инциденты → interrupt
│   │   │   └── command.py   # LangGraph: команды от человека
│   │   ├── mcp_client.py
│   │   ├── nodes.py
│   │   └── prompts.py
│   ├── bot/
│   │   ├── router.py
│   │   ├── handlers.py
│   │   └── callbacks.py     # кнопки → runbook → resume
│   ├── scheduler/
│   │   ├── worker.py        # Celery app
│   │   └── tasks.py         # scheduled check tasks
│   └── services/
│       └── incident.py
├── docker/
│   └── Dockerfile
└── tests/
```

## Схема БД
```sql
-- Запуски проверок
CREATE TABLE check_runs (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    host       VARCHAR(255) NOT NULL,
    check_name VARCHAR(128) NOT NULL,
    started_at DATETIME DEFAULT NOW(),
    finished_at DATETIME,
    status     ENUM('running','ok','incident','error') DEFAULT 'running',
    signal_count INT DEFAULT 0
);

-- Инциденты
CREATE TABLE incidents (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    check_run_id BIGINT,
    thread_id    VARCHAR(255),           -- LangGraph thread для resume
    host         VARCHAR(255) NOT NULL,
    severity     ENUM('critical','warning','info') NOT NULL,
    problem_type VARCHAR(128) NOT NULL,
    evidence     TEXT NOT NULL,
    status       ENUM('new','notified','actioned','ignored','resolved') DEFAULT 'new',
    action_taken VARCHAR(128),
    confirmed_by BIGINT,
    created_at   DATETIME DEFAULT NOW(),
    resolved_at  DATETIME,
    INDEX idx_host_status (host, status),
    INDEX idx_thread (thread_id)
);
```

## Конфигурация проверок (hosts.yaml)
```yaml
hosts:
  - name: web-01
    host: web-01.example.com
    ssh_user: deploy
    checks:
      - disk_space:
          threshold_warning: 80    # %
          threshold_critical: 90
          paths: ["/", "/var"]
      - systemd_services:
          services: [apache2, mariadb]
      - apache_errors:
          log_path: /var/log/apache2/error.log
          lookback_minutes: 30
      - mariadb_replication:
          warning_lag_seconds: 30
          critical_lag_seconds: 300

schedule:
  interval_minutes: 5       # как часто гонять все checks
  slow_query_on_demand: true # только по запросу
```

## .env.example
```env
# LLM
AITUNNEL_BASE_URL=https://api.aitunnel.ru/v1/
AITUNNEL_API_KEY=sk-aitunnel-xxx
MODEL_MAIN=claude-sonnet-4-6
MODEL_FAST=claude-haiku-4-5

# MCP серверы
MCP_SSH_URL=https://mcp-ssh.p4i.ru/mcp
MCP_SSH_TOKEN=...
MCP_MYSQL_URL=https://mcp-mysql.p4i.ru/ro2/mcp
MCP_MYSQL_TOKEN=...

# Telegram
TG_BOT_TOKEN=...
TG_ALLOWED_USERS=123456789
TG_CHAT_ID=...

# БД
DATABASE_URL=mysql+aiomysql://opsagent:...@db:3306/opsagent
DB_ROOT_PASSWORD=...
DB_NAME=opsagent
DB_USER=opsagent
DB_PASSWORD=...

# Redis
REDIS_URL=redis://redis:6379/0

# Конфиг хостов
HOSTS_CONFIG_PATH=/app/config/hosts.yaml
```

## Приоритет разработки

1. Docker Compose + Dockerfile
2. БД модели + Alembic (check_runs, incidents)
3. Check система — base.py + первые checks (disk, services, replication)
4. MCP клиент — SSH + MySQL
5. Runbooks — base.py + первые runbooks
6. analyze_graph — LangGraph: сигналы → Incident карточки → interrupt
7. TG Bot — уведомление с контекстными кнопками + resume → runbook
8. Celery Beat — расписание запуска checks
9. command_graph — команды от человека
10. hosts.yaml — конфигурация хостов и параметров проверок