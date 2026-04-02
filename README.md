# ops-agent

Проактивный агент мониторинга инфраструктуры. Сам ходит по серверам, собирает сигналы, нормализует в инциденты через LLM, уведомляет через Telegram с контекстными кнопками, выполняет runbooks по подтверждению.

## Возможности

- **Автоматический мониторинг** — Celery Beat запускает проверки по расписанию
- **LLM-нормализация** — сигналы → инциденты через LangGraph + AITUNNEL (Claude/GPT)
- **Telegram-бот** — уведомления с кнопками подтверждения действий + текстовые команды
- **Runbooks** — детерминированное выполнение действий через SSH
- **Веб-панель** — управление серверами, просмотр инцидентов, история проверок
- **AI-рекомендации** — LLM анализирует историю инцидентов и предлагает улучшения мониторинга

## Что мониторится

- Дисковое пространство (`df -h`)
- Systemd сервисы (`apache2`, `mariadb` и др.)
- MariaDB репликация (`SHOW SLAVE STATUS`)
- MariaDB медленные запросы
- Apache ошибки (`error.log`)

Все проверки и параметры настраиваются через веб-панель — без редактирования файлов.

## Стек

| Компонент | Технология |
|-----------|-----------|
| Агент | LangGraph + langchain-openai (AITUNNEL) |
| SSH | asyncssh (единственный транспорт — и system, и MySQL) |
| Планировщик | Celery + Celery Beat |
| Очередь / Checkpoints | Redis (redis-stack) |
| БД | MariaDB + SQLAlchemy async + Alembic |
| Telegram | Aiogram 3.x (polling) |
| Веб | FastAPI + Jinja2 + Tailwind CSS + Alpine.js |

## Быстрый старт

```bash
cp .env.example .env
# Заполнить .env (см. раздел Конфигурация)

docker compose up --build -d

# Первый запуск — применить миграции
docker compose exec app alembic upgrade head
```

Веб-панель: [http://localhost:8000](http://localhost:8000)

## Конфигурация (.env)

```env
# LLM — AITUNNEL (OpenAI-compatible proxy для Claude/GPT)
AITUNNEL_BASE_URL=https://api.aitunnel.ru/v1/
AITUNNEL_API_KEY=sk-aitunnel-xxx
MODEL_MAIN=claude-sonnet-4-6       # основная модель (нормализация, команды)
MODEL_FAST=claude-haiku-4-5        # быстрая модель (классификация интента)

# Telegram
TG_BOT_TOKEN=...
TG_ALLOWED_USERS=123456789         # comma-separated telegram user IDs
TG_CHAT_ID=...                     # куда отправлять уведомления об инцидентах

# База данных
DATABASE_URL=mysql+aiomysql://opsagent:changeme@db:3306/opsagent
DB_ROOT_PASSWORD=rootchangeme
DB_NAME=opsagent
DB_USER=opsagent
DB_PASSWORD=changeme

# Redis
REDIS_URL=redis://redis:6379/0

# Веб-панель
SECRET_KEY=...                     # random string для сессий
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# SSH (дефолты; переопределяются per-server в веб-панели)
SSH_DEFAULT_KEY_PATH=/root/.ssh/id_rsa
SSH_DEFAULT_USER=deploy

# Расписание
CHECK_INTERVAL_MINUTES=5
```

### SSH-ключи

Ключи монтируются в контейнер через Docker volume `ssh-keys`. Добавить ключ:

```bash
docker compose cp ~/.ssh/id_rsa app:/root/.ssh/id_rsa
docker compose exec app chmod 600 /root/.ssh/id_rsa
```

Или через volume на хосте:
```yaml
# docker-compose.yml — заменить volume на bind mount:
volumes:
  - ~/.ssh:/root/.ssh:ro
```

## Nginx (внешний прокси)

Веб-панель и API — один FastAPI сервис на порту 8000:

```nginx
server {
    listen 443 ssl;
    server_name ops.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Telegram-бот работает в режиме **polling** — дополнительного nginx-маршрута не требует.

## Добавление сервера

1. Открыть веб-панель → **Серверы** → **Добавить сервер**
2. Заполнить хост, SSH-пользователя, путь к ключу
3. Перейти в **Проверки** → включить нужные checks, настроить параметры
4. Сервер появится в расписании Celery Beat на следующем цикле

## Структура проекта

```
app/
├── agent/
│   ├── graphs/
│   │   ├── analyze.py     # сигналы → LLM → инциденты → interrupt/resume
│   │   └── command.py     # TG текст → intent → read/write → confirm
│   ├── ssh_tools.py       # asyncssh обёрнутый как LangChain BaseTool
│   └── prompts.py
├── bot/                   # Aiogram 3: уведомления + кнопки + текстовые команды
├── checks/                # Signal collectors: disk, services, mariadb, apache
├── runbooks/              # Детерминированные скрипты действий через SSH
├── scheduler/             # Celery Beat: периодический запуск checks
├── services/
│   ├── incident.py
│   └── recommendations.py # LLM-анализ паттернов инцидентов
└── web/
    ├── views/             # Dashboard, Servers CRUD, Incidents, Check Runs, AI Recs
    └── templates/         # Jinja2 + Tailwind CSS
```

## Разработка

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Тесты (125 тестов, без реального SSH/LLM)
pytest tests/

# Линтер
ruff check app/ tests/
```

## Добавить новую проверку

Создать файл в `app/checks/`, унаследоваться от `Check`, зарегистрировать в `app/checks/__init__.py`:

```python
class MyCheck(Check):
    async def run(self) -> list[Signal]:
        tool = self._get_tool("ssh_exec")
        output = await tool.arun({"command": "...", "host": self.host, ...})
        # parse output, return [Signal(...)]
```

## Добавить новый runbook

Создать файл в `app/runbooks/`, унаследоваться от `Runbook`, добавить в `RUNBOOK_REGISTRY`:

```python
class MyRunbook(Runbook):
    name = "my_runbook"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")
        result = await tool.arun({...})
        return RunbookResult(success=True, message="Done")
```
