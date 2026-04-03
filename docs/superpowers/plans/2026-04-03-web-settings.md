# Web Settings & SSH Key Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all `.env` configuration into a web-based Settings page with encrypted secrets, DB-stored SSH keys, and multi-admin user management.

**Architecture:** Key-value `settings` table + `ssh_keys` table + Fernet encryption. `SettingsService` with 60s TTL cache reads from DB, falls back to `.env`. Web UI with tabbed settings page. Auth moves from config-only to DB-backed `admin_users`.

**Tech Stack:** SQLAlchemy 2.x async, Alembic, FastAPI, Jinja2/Tailwind/Alpine.js, cryptography (Fernet), passlib[bcrypt], asyncssh

---

## File Structure

**New files:**
- `app/services/crypto.py` — Fernet encrypt/decrypt helpers
- `app/services/settings.py` — SettingsService (CRUD + cache)
- `app/services/auth.py` — password hashing, user verification
- `app/services/seed.py` — first-startup seed logic
- `app/web/views/settings.py` — Settings page routes (all tabs)
- `app/web/templates/settings.html` — Settings page template
- `tests/services/test_crypto.py` — encryption tests
- `tests/services/test_settings.py` — SettingsService tests
- `tests/services/test_auth.py` — auth service tests
- `tests/services/test_seed.py` — seed logic tests
- `tests/web/test_settings_views.py` — settings page route tests
- `alembic/versions/xxxx_add_settings_ssh_keys.py` — migration

**Modified files:**
- `app/db/models.py` — add Setting, SshKey models; modify Server (ssh_key_id)
- `app/config.py` — keep as-is for `.env` fallback
- `app/web/auth.py` — use DB-backed auth with `.env` fallback
- `app/web/__init__.py` — update login to use new auth
- `app/web/templates/base.html` — add Settings nav item
- `app/web/templates/server_edit.html` — replace ssh_key_path/password with dropdown
- `app/web/views/servers.py` — use ssh_key_id instead of ssh_key_path/ssh_password
- `app/web/views/dashboard.py` — add missing-config alerts
- `app/web/templates/dashboard.html` — render alerts
- `app/agent/ssh_tools.py` — accept key content (not just path)
- `app/agent/tool_provider.py` — resolve SSH key from DB
- `app/scheduler/tasks.py` — use SettingsService for tg_chat_id etc.
- `app/main.py` — call seed on startup, register settings router
- `app/db/session.py` — no changes (reads DATABASE_URL from .env, stays)
- `pyproject.toml` — add cryptography, passlib[bcrypt], aiosqlite (dev)
- `tests/conftest.py` — no changes needed (sqlite in-memory works)
- `tests/db/test_models.py` — add tests for new models

---

### Task 1: Dependencies & Crypto Service

**Files:**
- Modify: `pyproject.toml:6-40`
- Create: `app/services/crypto.py`
- Create: `tests/services/test_crypto.py`

- [ ] **Step 1: Write failing test for encrypt/decrypt round-trip**

Create `tests/services/test_crypto.py`:

```python
from app.services.crypto import decrypt_value, encrypt_value


def test_encrypt_decrypt_round_trip():
    secret_key = "test-secret-key-for-fernet-32!!"
    plain = "sk-aitunnel-very-secret-key"
    encrypted = encrypt_value(plain, secret_key)
    assert encrypted != plain
    decrypted = decrypt_value(encrypted, secret_key)
    assert decrypted == plain


def test_encrypt_produces_different_ciphertext():
    secret_key = "test-secret-key-for-fernet-32!!"
    plain = "my-secret"
    e1 = encrypt_value(plain, secret_key)
    e2 = encrypt_value(plain, secret_key)
    # Fernet uses random IV, so ciphertexts differ
    assert e1 != e2


def test_decrypt_with_wrong_key_raises():
    import pytest
    encrypted = encrypt_value("secret", "key-one-for-fernet-testing-32!!")
    with pytest.raises(Exception):
        decrypt_value(encrypted, "key-two-for-fernet-testing-32!!")


def test_encrypt_empty_string():
    secret_key = "test-secret-key-for-fernet-32!!"
    encrypted = encrypt_value("", secret_key)
    assert decrypt_value(encrypted, secret_key) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.crypto'`

- [ ] **Step 3: Add dependencies to pyproject.toml**

In `pyproject.toml`, add to `dependencies` list:

```
    "cryptography>=44.0",
    "passlib[bcrypt]>=1.7",
```

Add to `dev` optional-dependencies:

```
    "aiosqlite>=0.20",
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 4: Implement crypto module**

Create `app/services/crypto.py`:

```python
"""Fernet-based encryption for secrets stored in the database."""

import base64
import hashlib

from cryptography.fernet import Fernet


def _derive_key(secret_key: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret."""
    digest = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_value(plain: str, secret_key: str) -> str:
    """Encrypt a plaintext string, return base64-encoded ciphertext."""
    f = Fernet(_derive_key(secret_key))
    return f.encrypt(plain.encode()).decode()


def decrypt_value(cipher: str, secret_key: str) -> str:
    """Decrypt a base64-encoded ciphertext back to plaintext."""
    f = Fernet(_derive_key(secret_key))
    return f.decrypt(cipher.encode()).decode()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_crypto.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app/services/crypto.py tests/services/test_crypto.py
git commit -m "feat: add Fernet crypto service for settings encryption"
```

---

### Task 2: DB Models — Setting, SshKey, Server.ssh_key_id

**Files:**
- Modify: `app/db/models.py:1-98`
- Create: `tests/db/test_settings_models.py`

- [ ] **Step 1: Write failing tests for new models**

Create `tests/db/test_settings_models.py`:

```python
import pytest
from sqlalchemy import select

from app.db.models import Server, Setting, SshKey


@pytest.mark.asyncio
async def test_create_setting(db_session):
    s = Setting(key="model_main", value="claude-sonnet-4.6", category="llm")
    db_session.add(s)
    await db_session.flush()

    result = await db_session.execute(select(Setting).where(Setting.key == "model_main"))
    fetched = result.scalar_one()
    assert fetched.value == "claude-sonnet-4.6"
    assert fetched.category == "llm"
    assert fetched.is_secret is False
    assert fetched.requires_restart is False


@pytest.mark.asyncio
async def test_setting_secret_flag(db_session):
    s = Setting(
        key="aitunnel_api_key",
        value="encrypted-blob",
        category="llm",
        is_secret=True,
        requires_restart=True,
    )
    db_session.add(s)
    await db_session.flush()

    result = await db_session.execute(select(Setting).where(Setting.key == "aitunnel_api_key"))
    fetched = result.scalar_one()
    assert fetched.is_secret is True
    assert fetched.requires_restart is True


@pytest.mark.asyncio
async def test_create_ssh_key(db_session):
    key = SshKey(name="production-default", private_key="encrypted-key-data", is_default=True)
    db_session.add(key)
    await db_session.flush()

    assert key.id is not None
    assert key.is_default is True


@pytest.mark.asyncio
async def test_ssh_key_unique_name(db_session):
    k1 = SshKey(name="my-key", private_key="data1")
    db_session.add(k1)
    await db_session.flush()

    k2 = SshKey(name="my-key", private_key="data2")
    db_session.add(k2)
    with pytest.raises(Exception):  # IntegrityError
        await db_session.flush()


@pytest.mark.asyncio
async def test_server_ssh_key_relation(db_session):
    key = SshKey(name="web-key", private_key="data")
    db_session.add(key)
    await db_session.flush()

    server = Server(name="web-01", host="web-01.example.com", ssh_key_id=key.id)
    db_session.add(server)
    await db_session.flush()

    assert server.ssh_key_id == key.id


@pytest.mark.asyncio
async def test_server_ssh_key_nullable(db_session):
    server = Server(name="web-02", host="web-02.example.com")
    db_session.add(server)
    await db_session.flush()

    assert server.ssh_key_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/db/test_settings_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Setting' from 'app.db.models'`

- [ ] **Step 3: Add Setting and SshKey models, modify Server**

In `app/db/models.py`, add after `AdminUser` class:

```python
class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_restart: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SshKey(Base):
    __tablename__ = "ssh_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    private_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
```

In `Server` class, replace `ssh_key_path` and `ssh_password` with:

```python
    ssh_key_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("ssh_keys.id"), nullable=True)
```

Remove:
```python
    ssh_key_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ssh_password: Mapped[str | None] = mapped_column(String(256), nullable=True)
```

Add relationship:
```python
    ssh_key: Mapped["SshKey | None"] = relationship()
```

- [ ] **Step 4: Fix existing test_models.py**

In `tests/db/test_models.py`, update `test_create_server` — it no longer has `ssh_key_path`/`ssh_password`, those lines are gone and `Server(name=..., host=..., ssh_user=...)` still works.

Also update imports in `tests/db/test_models.py` top line — ensure no reference to removed fields.

- [ ] **Step 5: Run all tests to verify they pass**

Run: `python -m pytest tests/db/ -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/db/models.py tests/db/test_settings_models.py tests/db/test_models.py
git commit -m "feat: add Setting, SshKey models; replace ssh_key_path with ssh_key_id FK"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `alembic/versions/xxxx_add_settings_ssh_keys.py`

- [ ] **Step 1: Generate migration**

Run: `alembic revision --autogenerate -m "add settings ssh_keys tables and server ssh_key_id"`

- [ ] **Step 2: Review generated migration**

Open the generated file in `alembic/versions/`. Verify it contains:
1. `create_table('settings', ...)` with correct columns
2. `create_table('ssh_keys', ...)` with correct columns
3. `add_column('servers', Column('ssh_key_id', Integer, ForeignKey('ssh_keys.id')))`
4. `drop_column('servers', 'ssh_key_path')`
5. `drop_column('servers', 'ssh_password')`

If autogenerate missed anything, add manually.

- [ ] **Step 3: Test migration against Docker DB (if running)**

Run: `docker compose up -d db && alembic upgrade head`

If Docker is not running, skip — migration will be tested with `docker compose up` later.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: alembic migration for settings/ssh_keys tables"
```

---

### Task 4: Auth Service (bcrypt + DB-backed users)

**Files:**
- Create: `app/services/auth.py`
- Create: `tests/services/test_auth.py`
- Modify: `app/web/auth.py:1-29`
- Modify: `app/web/__init__.py:1-46`

- [ ] **Step 1: Write failing tests for auth service**

Create `tests/services/test_auth.py`:

```python
import pytest
from sqlalchemy import select

from app.db.models import AdminUser
from app.services.auth import hash_password, verify_password


def test_hash_and_verify():
    hashed = hash_password("my-secret-password")
    assert hashed != "my-secret-password"
    assert verify_password("my-secret-password", hashed) is True


def test_wrong_password():
    hashed = hash_password("correct")
    assert verify_password("wrong", hashed) is False


def test_different_hashes_for_same_password():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # bcrypt salts differ


@pytest.mark.asyncio
async def test_verify_credentials_db(db_session):
    from app.services.auth import verify_credentials_db

    user = AdminUser(username="admin", password_hash=hash_password("admin123"))
    db_session.add(user)
    await db_session.flush()

    assert await verify_credentials_db(db_session, "admin", "admin123") is True
    assert await verify_credentials_db(db_session, "admin", "wrong") is False
    assert await verify_credentials_db(db_session, "nobody", "admin123") is False


@pytest.mark.asyncio
async def test_verify_inactive_user_rejected(db_session):
    from app.services.auth import verify_credentials_db

    user = AdminUser(
        username="disabled",
        password_hash=hash_password("pass"),
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()

    assert await verify_credentials_db(db_session, "disabled", "pass") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.auth'`

- [ ] **Step 3: Implement auth service**

Create `app/services/auth.py`:

```python
"""Password hashing and DB-backed user verification."""

from passlib.hash import bcrypt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminUser


def hash_password(plain: str) -> str:
    return bcrypt.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.verify(plain, hashed)


async def verify_credentials_db(session: AsyncSession, username: str, password: str) -> bool:
    """Check username/password against admin_users table."""
    result = await session.execute(
        select(AdminUser).where(AdminUser.username == username, AdminUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return False
    return verify_password(password, user.password_hash)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_auth.py -v`
Expected: 5 passed

- [ ] **Step 5: Update web auth to use DB with .env fallback**

Replace `app/web/auth.py`:

```python
"""Authentication for the web panel."""

from functools import wraps

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db.session import get_session
from app.services.auth import verify_credentials_db


def login_required(func):
    """Decorator that redirects to /login if not authenticated."""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("logged_in"):
            return RedirectResponse("/login", status_code=302)
        return await func(request, *args, **kwargs)

    return wrapper


async def verify_credentials(username: str, password: str) -> bool:
    """Check credentials: DB first, then .env fallback."""
    async with get_session() as session:
        if await verify_credentials_db(session, username, password):
            return True
    # Fallback to .env (emergency access when no DB users exist)
    return username == settings.admin_username and password == settings.admin_password
```

- [ ] **Step 6: Update login handler to await verify_credentials**

In `app/web/__init__.py`, `login_submit` function — `verify_credentials` is now async, so change:

```python
    if verify_credentials(username, password):
```
to:
```python
    if await verify_credentials(username, password):
```

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -q --tb=short`
Expected: all pass (some tests may need adjustments if they import verify_credentials)

- [ ] **Step 8: Commit**

```bash
git add app/services/auth.py tests/services/test_auth.py app/web/auth.py app/web/__init__.py
git commit -m "feat: DB-backed auth with bcrypt, .env fallback"
```

---

### Task 5: SettingsService (CRUD + cache + fallback)

**Files:**
- Create: `app/services/settings.py`
- Create: `tests/services/test_settings.py`

- [ ] **Step 1: Write failing tests for SettingsService**

Create `tests/services/test_settings.py`:

```python
import pytest
from sqlalchemy import select

from app.db.models import Setting
from app.services.settings import SettingsService


@pytest.fixture
def svc():
    return SettingsService(secret_key="test-secret-key-for-fernet-32!!")


@pytest.mark.asyncio
async def test_get_setting_from_db(db_session, svc):
    db_session.add(Setting(key="model_main", value="gpt-4", category="llm"))
    await db_session.flush()

    val = await svc.get_value(db_session, "model_main")
    assert val == "gpt-4"


@pytest.mark.asyncio
async def test_get_secret_setting_decrypted(db_session, svc):
    from app.services.crypto import encrypt_value

    encrypted = encrypt_value("real-api-key", svc.secret_key)
    db_session.add(
        Setting(key="aitunnel_api_key", value=encrypted, category="llm", is_secret=True)
    )
    await db_session.flush()

    val = await svc.get_value(db_session, "aitunnel_api_key")
    assert val == "real-api-key"


@pytest.mark.asyncio
async def test_get_missing_setting_returns_none(db_session, svc):
    val = await svc.get_value(db_session, "nonexistent")
    assert val is None


@pytest.mark.asyncio
async def test_set_plain_value(db_session, svc):
    await svc.set_value(db_session, "model_fast", "claude-haiku", category="llm")
    await db_session.flush()

    result = await db_session.execute(select(Setting).where(Setting.key == "model_fast"))
    row = result.scalar_one()
    assert row.value == "claude-haiku"


@pytest.mark.asyncio
async def test_set_secret_value_encrypted(db_session, svc):
    await svc.set_value(
        db_session, "tg_bot_token", "123:ABC", category="telegram", is_secret=True
    )
    await db_session.flush()

    result = await db_session.execute(select(Setting).where(Setting.key == "tg_bot_token"))
    row = result.scalar_one()
    # Stored value is not plaintext
    assert row.value != "123:ABC"
    assert row.is_secret is True


@pytest.mark.asyncio
async def test_update_existing_value(db_session, svc):
    db_session.add(Setting(key="model_main", value="old", category="llm"))
    await db_session.flush()

    await svc.set_value(db_session, "model_main", "new", category="llm")
    await db_session.flush()

    val = await svc.get_value(db_session, "model_main")
    assert val == "new"


@pytest.mark.asyncio
async def test_get_all_by_category(db_session, svc):
    db_session.add(Setting(key="model_main", value="gpt-4", category="llm"))
    db_session.add(Setting(key="model_fast", value="gpt-mini", category="llm"))
    db_session.add(Setting(key="tg_chat_id", value="123", category="telegram"))
    await db_session.flush()

    llm_settings = await svc.get_by_category(db_session, "llm")
    assert len(llm_settings) == 2
    assert "model_main" in llm_settings
    assert "model_fast" in llm_settings


@pytest.mark.asyncio
async def test_bulk_update_returns_restart_flag(db_session, svc):
    db_session.add(
        Setting(key="aitunnel_api_key", value="old", category="llm", is_secret=True, requires_restart=True)
    )
    db_session.add(Setting(key="model_main", value="old", category="llm"))
    await db_session.flush()

    needs_restart = await svc.bulk_update(
        db_session, {"aitunnel_api_key": "new-key", "model_main": "new-model"}
    )
    assert needs_restart is True


@pytest.mark.asyncio
async def test_bulk_update_no_restart(db_session, svc):
    db_session.add(Setting(key="model_main", value="old", category="llm"))
    await db_session.flush()

    needs_restart = await svc.bulk_update(db_session, {"model_main": "new"})
    assert needs_restart is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.settings'`

- [ ] **Step 3: Implement SettingsService**

Create `app/services/settings.py`:

```python
"""Service for reading/writing app settings from the database."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting
from app.services.crypto import decrypt_value, encrypt_value

# Settings definitions: key -> (category, is_secret, requires_restart)
SETTINGS_DEFS: dict[str, tuple[str, bool, bool]] = {
    "aitunnel_base_url": ("llm", False, True),
    "aitunnel_api_key": ("llm", True, True),
    "model_main": ("llm", False, False),
    "model_fast": ("llm", False, False),
    "tg_bot_token": ("telegram", True, True),
    "tg_chat_id": ("telegram", False, False),
    "tg_allowed_users": ("telegram", False, False),
    "ssh_default_user": ("ssh", False, False),
    "check_interval_minutes": ("schedule", False, False),
}


class SettingsService:
    """Read/write settings with encryption and caching."""

    def __init__(self, secret_key: str, cache_ttl: int = 60):
        self.secret_key = secret_key
        self.cache_ttl = cache_ttl
        self._cache: dict[str, str] = {}
        self._cache_ts: float = 0

    async def get_value(self, session: AsyncSession, key: str) -> str | None:
        """Get a single setting value, decrypting if needed."""
        result = await session.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if row.is_secret and row.value:
            return decrypt_value(row.value, self.secret_key)
        return row.value

    async def set_value(
        self,
        session: AsyncSession,
        key: str,
        value: str,
        category: str | None = None,
        is_secret: bool | None = None,
        requires_restart: bool | None = None,
    ) -> None:
        """Set a setting value, encrypting if is_secret."""
        result = await session.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()

        # Resolve metadata from defs if not provided
        if category is None or is_secret is None or requires_restart is None:
            defs = SETTINGS_DEFS.get(key, ("general", False, False))
            category = category or defs[0]
            is_secret = is_secret if is_secret is not None else defs[1]
            requires_restart = requires_restart if requires_restart is not None else defs[2]

        stored_value = encrypt_value(value, self.secret_key) if is_secret else value

        if row is None:
            row = Setting(
                key=key,
                value=stored_value,
                category=category,
                is_secret=is_secret,
                requires_restart=requires_restart,
            )
            session.add(row)
        else:
            row.value = stored_value
            row.is_secret = is_secret
            row.requires_restart = requires_restart

        self._invalidate_cache()

    async def get_by_category(self, session: AsyncSession, category: str) -> dict[str, str]:
        """Get all settings for a category as {key: decrypted_value}."""
        result = await session.execute(
            select(Setting).where(Setting.category == category)
        )
        settings = {}
        for row in result.scalars().all():
            if row.is_secret and row.value:
                settings[row.key] = decrypt_value(row.value, self.secret_key)
            else:
                settings[row.key] = row.value
        return settings

    async def get_all(self, session: AsyncSession) -> dict[str, str]:
        """Get all settings as {key: decrypted_value}."""
        result = await session.execute(select(Setting))
        settings = {}
        for row in result.scalars().all():
            if row.is_secret and row.value:
                settings[row.key] = decrypt_value(row.value, self.secret_key)
            else:
                settings[row.key] = row.value
        return settings

    async def bulk_update(self, session: AsyncSession, updates: dict[str, str]) -> bool:
        """Update multiple settings. Returns True if any requires restart."""
        needs_restart = False
        for key, value in updates.items():
            result = await session.execute(select(Setting).where(Setting.key == key))
            row = result.scalar_one_or_none()
            if row is None:
                continue
            if row.requires_restart:
                needs_restart = True
            stored_value = encrypt_value(value, self.secret_key) if row.is_secret else value
            row.value = stored_value
        self._invalidate_cache()
        return needs_restart

    async def get_cached(self, session: AsyncSession) -> dict[str, str]:
        """Get all settings with TTL cache."""
        now = time.time()
        if now - self._cache_ts > self.cache_ttl:
            self._cache = await self.get_all(session)
            self._cache_ts = now
        return dict(self._cache)

    def _invalidate_cache(self) -> None:
        self._cache_ts = 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_settings.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/services/settings.py tests/services/test_settings.py
git commit -m "feat: SettingsService with encryption, caching, bulk update"
```

---

### Task 6: Seed Service (first-startup bootstrap)

**Files:**
- Create: `app/services/seed.py`
- Create: `tests/services/test_seed.py`

- [ ] **Step 1: Write failing tests for seed**

Create `tests/services/test_seed.py`:

```python
import pytest
from sqlalchemy import select

from app.db.models import AdminUser, Setting
from app.services.auth import verify_password


@pytest.mark.asyncio
async def test_seed_settings_into_empty_db(db_session):
    from app.services.seed import seed_settings

    await seed_settings(db_session, secret_key="test-key-for-fernet-testing-32!!", env_values={
        "aitunnel_base_url": "https://api.example.com/v1/",
        "model_main": "claude-sonnet",
    })
    await db_session.flush()

    result = await db_session.execute(select(Setting))
    rows = {r.key: r for r in result.scalars().all()}
    assert "aitunnel_base_url" in rows
    assert rows["aitunnel_base_url"].value == "https://api.example.com/v1/"
    assert "model_main" in rows


@pytest.mark.asyncio
async def test_seed_skips_if_settings_exist(db_session):
    db_session.add(Setting(key="model_main", value="existing", category="llm"))
    await db_session.flush()

    from app.services.seed import seed_settings

    await seed_settings(db_session, secret_key="test-key-for-fernet-testing-32!!", env_values={
        "model_main": "from-env",
    })
    await db_session.flush()

    result = await db_session.execute(select(Setting).where(Setting.key == "model_main"))
    row = result.scalar_one()
    assert row.value == "existing"  # not overwritten


@pytest.mark.asyncio
async def test_seed_admin_user(db_session):
    from app.services.seed import seed_admin_user

    await seed_admin_user(db_session, username="admin", password="secret123")
    await db_session.flush()

    result = await db_session.execute(select(AdminUser))
    user = result.scalar_one()
    assert user.username == "admin"
    assert verify_password("secret123", user.password_hash) is True


@pytest.mark.asyncio
async def test_seed_admin_skips_if_users_exist(db_session):
    from app.services.auth import hash_password
    db_session.add(AdminUser(username="existing", password_hash=hash_password("pass")))
    await db_session.flush()

    from app.services.seed import seed_admin_user

    await seed_admin_user(db_session, username="newadmin", password="newpass")
    await db_session.flush()

    result = await db_session.execute(select(AdminUser))
    users = result.scalars().all()
    assert len(users) == 1
    assert users[0].username == "existing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/services/test_seed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.seed'`

- [ ] **Step 3: Implement seed service**

Create `app/services/seed.py`:

```python
"""First-startup seed logic: populate settings and admin user from .env."""

from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminUser, Setting
from app.services.auth import hash_password
from app.services.crypto import encrypt_value
from app.services.settings import SETTINGS_DEFS

logger = structlog.get_logger()


async def seed_settings(
    session: AsyncSession,
    secret_key: str,
    env_values: dict[str, str],
) -> None:
    """Insert default settings from env_values if table is empty for each key."""
    for key, (category, is_secret, requires_restart) in SETTINGS_DEFS.items():
        result = await session.execute(select(Setting).where(Setting.key == key))
        if result.scalar_one_or_none() is not None:
            continue

        raw_value = env_values.get(key, "")
        stored = encrypt_value(raw_value, secret_key) if is_secret and raw_value else raw_value

        session.add(Setting(
            key=key,
            value=stored,
            category=category,
            is_secret=is_secret,
            requires_restart=requires_restart,
        ))
        logger.info("seeded_setting", key=key, category=category)


async def seed_admin_user(
    session: AsyncSession,
    username: str,
    password: str,
) -> None:
    """Create the first admin user if no users exist."""
    count = (await session.execute(select(func.count(AdminUser.id)))).scalar() or 0
    if count > 0:
        logger.info("admin_users_exist", count=count)
        return

    session.add(AdminUser(
        username=username,
        password_hash=hash_password(password),
    ))
    logger.info("seeded_admin_user", username=username)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_seed.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/seed.py tests/services/test_seed.py
git commit -m "feat: seed service for first-startup settings and admin user"
```

---

### Task 7: Integrate Seed into App Startup

**Files:**
- Modify: `app/main.py:1-57`

- [ ] **Step 1: Add seed call to lifespan**

In `app/main.py`, add seed calls inside the `lifespan` function, before the bot startup:

```python
@asynccontextmanager
async def lifespan(app):
    """Seed DB on first start, then start Aiogram bot polling."""
    # Seed settings and admin user from .env on first startup
    from app.db.session import get_session
    from app.services.seed import seed_admin_user, seed_settings

    async with get_session() as session:
        env_values = {
            "aitunnel_base_url": settings.aitunnel_base_url,
            "aitunnel_api_key": settings.aitunnel_api_key,
            "model_main": settings.model_main,
            "model_fast": settings.model_fast,
            "tg_bot_token": settings.tg_bot_token,
            "tg_chat_id": settings.tg_chat_id,
            "tg_allowed_users": settings.tg_allowed_users,
            "ssh_default_user": settings.ssh_default_user,
            "check_interval_minutes": str(settings.check_interval_minutes),
        }
        await seed_settings(session, secret_key=settings.secret_key, env_values=env_values)
        await seed_admin_user(session, username=settings.admin_username, password=settings.admin_password)

    # Start TG bot
    task = None
    if settings.tg_bot_token:
        from app.bot.router import dp, get_bot

        import app.bot.callbacks  # noqa: F401
        import app.bot.handlers  # noqa: F401

        bot = get_bot()
        task = asyncio.create_task(dp.start_polling(bot))

    yield

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 2: Run quick smoke test**

Run: `python -c "from app.main import app; print('main ok')"`
Expected: `main ok`

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: call seed on app startup for settings and admin user"
```

---

### Task 8: SSH Tools — Accept Key Content Instead of Path

**Files:**
- Modify: `app/agent/ssh_tools.py:25-55`
- Modify: `app/agent/tool_provider.py:1-83`
- Create: `tests/agent/test_tool_provider.py`

- [ ] **Step 1: Write failing test for tool_provider resolving SSH key from DB**

Create `tests/agent/test_tool_provider.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.tool_provider import resolve_ssh_config


@pytest.mark.asyncio
async def test_resolve_ssh_config_with_key_id(db_session):
    from app.db.models import Server, SshKey
    from app.services.crypto import encrypt_value

    secret_key = "test-secret-key-for-fernet-32!!"
    key_content = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
    encrypted = encrypt_value(key_content, secret_key)

    ssh_key = SshKey(name="test-key", private_key=encrypted, is_default=False)
    db_session.add(ssh_key)
    await db_session.flush()

    server = Server(name="web-01", host="1.2.3.4", ssh_key_id=ssh_key.id)
    db_session.add(server)
    await db_session.flush()

    config = await resolve_ssh_config(db_session, server, secret_key)
    assert config["host"] == "1.2.3.4"
    assert config["ssh_user"] == "deploy"
    assert config["ssh_key_content"] == key_content
    assert "ssh_key_path" not in config


@pytest.mark.asyncio
async def test_resolve_ssh_config_default_key(db_session):
    from app.db.models import Server, SshKey
    from app.services.crypto import encrypt_value

    secret_key = "test-secret-key-for-fernet-32!!"
    key_content = "-----BEGIN RSA PRIVATE KEY-----\ndefault\n-----END RSA PRIVATE KEY-----"
    encrypted = encrypt_value(key_content, secret_key)

    ssh_key = SshKey(name="default-key", private_key=encrypted, is_default=True)
    db_session.add(ssh_key)
    await db_session.flush()

    server = Server(name="web-02", host="5.6.7.8")  # no ssh_key_id
    db_session.add(server)
    await db_session.flush()

    config = await resolve_ssh_config(db_session, server, secret_key)
    assert config["ssh_key_content"] == key_content


@pytest.mark.asyncio
async def test_resolve_ssh_config_no_key_at_all(db_session):
    from app.db.models import Server

    server = Server(name="web-03", host="9.10.11.12")
    db_session.add(server)
    await db_session.flush()

    config = await resolve_ssh_config(db_session, server, "test-secret-key-for-fernet-32!!")
    assert config.get("ssh_key_content") is None
    assert config.get("ssh_key_path") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agent/test_tool_provider.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_ssh_config'`

- [ ] **Step 3: Modify ssh_tools.py to accept key content**

In `app/agent/ssh_tools.py`, update `_ssh_run` to accept optional `ssh_key_content`:

```python
async def _ssh_run(
    host: str,
    command: str,
    ssh_user: str = "deploy",
    ssh_key_path: str | None = None,
    ssh_key_content: str | None = None,
    ssh_port: int = 22,
) -> dict[str, Any]:
    """Execute a command on a remote host via asyncssh."""
    try:
        connect_kwargs: dict[str, Any] = {
            "host": host,
            "port": ssh_port,
            "username": ssh_user,
            "known_hosts": None,
        }

        if ssh_key_content:
            # Import key directly from string content
            import_key = asyncssh.import_private_key(ssh_key_content)
            connect_kwargs["client_keys"] = [import_key]
        elif ssh_key_path:
            key_path = os.path.expanduser(ssh_key_path)
            connect_kwargs["client_keys"] = [key_path]

        async with asyncssh.connect(**connect_kwargs) as conn:
            result = await conn.run(command)
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_status,
            }
    except Exception as exc:
        logger.error("ssh_run_failed", host=host, command=command, error=str(exc))
        return {"stdout": "", "stderr": str(exc), "exit_code": -1, "error": str(exc)}
```

- [ ] **Step 4: Add resolve_ssh_config to tool_provider.py and update get_read_tools/get_write_tools**

In `app/agent/tool_provider.py`, add:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Server, SshKey
from app.services.crypto import decrypt_value


async def resolve_ssh_config(
    session: AsyncSession, server: Server, secret_key: str
) -> dict:
    """Resolve SSH config for a server, decrypting key from DB."""
    config = {
        "host": server.host,
        "ssh_user": server.ssh_user or settings.ssh_default_user,
        "ssh_port": server.ssh_port or 22,
    }

    ssh_key: SshKey | None = None
    if server.ssh_key_id:
        ssh_key = await session.get(SshKey, server.ssh_key_id)
    if ssh_key is None:
        # Try default key
        result = await session.execute(
            select(SshKey).where(SshKey.is_default.is_(True)).limit(1)
        )
        ssh_key = result.scalar_one_or_none()

    if ssh_key:
        config["ssh_key_content"] = decrypt_value(ssh_key.private_key, secret_key)
    else:
        config["ssh_key_content"] = None
        config["ssh_key_path"] = None

    return config
```

Update `get_read_tools` and `get_write_tools` to use `ssh_key_content`:

```python
def get_read_tools(host_config: dict) -> list:
    host = host_config["host"]
    ssh_user = host_config.get("ssh_user") or settings.ssh_default_user
    ssh_key_content = host_config.get("ssh_key_content")
    ssh_key_path = host_config.get("ssh_key_path")
    ssh_port = int(host_config.get("ssh_port") or 22)

    @tool
    async def ssh_exec(command: str) -> str:
        """Execute a shell command on the remote host via SSH. Returns stdout."""
        result = await _ssh_run(host, command, ssh_user, ssh_key_path, ssh_key_content, ssh_port)
        return result["stdout"]

    # ... same pattern for other tools ...
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/agent/test_tool_provider.py tests/agent/test_ssh_tools.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/agent/ssh_tools.py app/agent/tool_provider.py tests/agent/test_tool_provider.py
git commit -m "feat: SSH tools accept key content from DB, resolve_ssh_config"
```

---

### Task 9: Settings Web Views — Routes & Template

**Files:**
- Create: `app/web/views/settings.py`
- Create: `app/web/templates/settings.html`
- Modify: `app/web/templates/base.html:24-45` (sidebar nav)
- Modify: `app/main.py` (register router)

- [ ] **Step 1: Create settings view routes**

Create `app/web/views/settings.py`:

```python
"""Settings views — tabbed page for LLM, Telegram, SSH, Schedule, Users."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.config import settings as env_settings
from app.db.models import AdminUser, Setting, SshKey
from app.db.session import get_session
from app.services.auth import hash_password
from app.services.crypto import decrypt_value, encrypt_value
from app.services.settings import SETTINGS_DEFS, SettingsService
from app.web.auth import login_required

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="app/web/templates")


def _get_svc() -> SettingsService:
    return SettingsService(secret_key=env_settings.secret_key)


def _mask_secret(value: str) -> str:
    """Mask a secret value for display: show first 4 and last 3 chars."""
    if not value or len(value) <= 10:
        return "***"
    return value[:4] + "***" + value[-3:]


@router.get("", response_class=HTMLResponse)
@login_required
async def settings_page(request: Request):
    svc = _get_svc()
    async with get_session() as session:
        all_settings = await svc.get_all(session)

        # SSH keys
        result = await session.execute(select(SshKey).order_by(SshKey.name))
        ssh_keys = result.scalars().all()

        # Users
        result = await session.execute(select(AdminUser).order_by(AdminUser.username))
        users = result.scalars().all()

    # Build masked view for secrets
    masked = {}
    for key, value in all_settings.items():
        cat, is_secret, _ = SETTINGS_DEFS.get(key, ("general", False, False))
        masked[key] = _mask_secret(value) if is_secret and value else value

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "settings": all_settings,
            "masked": masked,
            "ssh_keys": ssh_keys,
            "users": users,
            "defs": SETTINGS_DEFS,
        },
    )


@router.post("", response_class=HTMLResponse)
@login_required
async def settings_save(request: Request):
    form = await request.form()
    category = form.get("category", "")
    svc = _get_svc()

    updates = {}
    for key, (cat, is_secret, _) in SETTINGS_DEFS.items():
        if cat != category:
            continue
        form_value = form.get(key)
        if form_value is None:
            continue
        # Don't overwrite secrets with mask placeholder
        if is_secret and form_value.startswith("***"):
            continue
        if is_secret and form_value == "":
            continue
        updates[key] = form_value.strip()

    needs_restart = False
    if updates:
        async with get_session() as session:
            needs_restart = await svc.bulk_update(session, updates)

    msg = "Настройки сохранены"
    if needs_restart:
        msg += ". Требуется перезапуск сервиса для применения: " + ", ".join(
            k for k in updates if SETTINGS_DEFS.get(k, ("", False, False))[2]
        )

    return RedirectResponse(f"/settings?msg={msg}#{category}", status_code=302)


# --- SSH Keys ---

@router.get("/ssh-keys")
@login_required
async def ssh_keys_list(request: Request):
    async with get_session() as session:
        result = await session.execute(select(SshKey).order_by(SshKey.name))
        keys = [{"id": k.id, "name": k.name, "is_default": k.is_default} for k in result.scalars().all()]
    return keys


@router.post("/ssh-keys")
@login_required
async def ssh_key_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    private_key_text = (form.get("private_key") or "").strip()

    if not name or not private_key_text:
        return RedirectResponse("/settings?msg=Имя и ключ обязательны#ssh", status_code=302)

    is_default = form.get("is_default") == "on"
    encrypted = encrypt_value(private_key_text, env_settings.secret_key)

    async with get_session() as session:
        if is_default:
            # Unset other defaults
            result = await session.execute(select(SshKey).where(SshKey.is_default.is_(True)))
            for existing in result.scalars().all():
                existing.is_default = False

        session.add(SshKey(name=name, private_key=encrypted, is_default=is_default))

    return RedirectResponse("/settings?msg=SSH ключ добавлен#ssh", status_code=302)


@router.post("/ssh-keys/{key_id}")
@login_required
async def ssh_key_update(request: Request, key_id: int):
    form = await request.form()
    name = (form.get("name") or "").strip()
    is_default = form.get("is_default") == "on"

    async with get_session() as session:
        ssh_key = await session.get(SshKey, key_id)
        if not ssh_key:
            return RedirectResponse("/settings?msg=Ключ не найден#ssh", status_code=302)

        if name:
            ssh_key.name = name
        ssh_key.is_default = is_default

        if is_default:
            result = await session.execute(
                select(SshKey).where(SshKey.is_default.is_(True), SshKey.id != key_id)
            )
            for other in result.scalars().all():
                other.is_default = False

        # Update key content if provided
        private_key_text = (form.get("private_key") or "").strip()
        if private_key_text:
            ssh_key.private_key = encrypt_value(private_key_text, env_settings.secret_key)

    return RedirectResponse("/settings?msg=SSH ключ обновлён#ssh", status_code=302)


@router.post("/ssh-keys/{key_id}/delete")
@login_required
async def ssh_key_delete(request: Request, key_id: int):
    async with get_session() as session:
        ssh_key = await session.get(SshKey, key_id)
        if ssh_key:
            await session.delete(ssh_key)

    return RedirectResponse("/settings?msg=SSH ключ удалён#ssh", status_code=302)


# --- Users ---

@router.post("/users")
@login_required
async def user_create(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()

    if not username or not password:
        return RedirectResponse("/settings?msg=Имя и пароль обязательны#users", status_code=302)

    async with get_session() as session:
        session.add(AdminUser(username=username, password_hash=hash_password(password)))

    return RedirectResponse("/settings?msg=Пользователь создан#users", status_code=302)


@router.post("/users/{user_id}")
@login_required
async def user_update(request: Request, user_id: int):
    form = await request.form()

    async with get_session() as session:
        user = await session.get(AdminUser, user_id)
        if not user:
            return RedirectResponse("/settings?msg=Пользователь не найден#users", status_code=302)

        new_password = (form.get("password") or "").strip()
        if new_password:
            user.password_hash = hash_password(new_password)

        is_active = form.get("is_active")
        if is_active is not None:
            user.is_active = is_active == "on"

    return RedirectResponse("/settings?msg=Пользователь обновлён#users", status_code=302)


@router.post("/users/{user_id}/delete")
@login_required
async def user_delete(request: Request, user_id: int):
    async with get_session() as session:
        # Don't allow deleting last active user
        from sqlalchemy import func
        active_count = (
            await session.execute(
                select(func.count(AdminUser.id)).where(AdminUser.is_active.is_(True))
            )
        ).scalar() or 0

        if active_count <= 1:
            return RedirectResponse(
                "/settings?msg=Нельзя удалить последнего активного пользователя#users",
                status_code=302,
            )

        user = await session.get(AdminUser, user_id)
        # Don't delete yourself
        current_username = request.session.get("username")
        if user and user.username == current_username:
            return RedirectResponse(
                "/settings?msg=Нельзя удалить самого себя#users",
                status_code=302,
            )

        if user:
            await session.delete(user)

    return RedirectResponse("/settings?msg=Пользователь удалён#users", status_code=302)
```

- [ ] **Step 2: Create settings template**

Create `app/web/templates/settings.html` — a full Jinja2 template with Tailwind/Alpine tabs for LLM, Telegram, SSH, Schedule, Users. Each tab has a form with Save button. SSH tab includes key table + add modal. Users tab includes user table + add form.

The template extends `base.html`, uses `x-data="{ tab: 'llm' }"` Alpine.js for tab switching, and contains forms posting to `/settings` with hidden `category` field.

(Full template content will be provided in implementation — it's ~300 lines of HTML/Tailwind that should be written in one step.)

- [ ] **Step 3: Add Settings to sidebar in base.html**

In `app/web/templates/base.html`, add after the AI Советы nav item (line 44):

```html
                <a href="/settings" class="flex items-center px-4 py-3 text-blue-100 hover:bg-blue-700 hover:text-white {{ 'bg-blue-700' if active_page == 'settings' else '' }}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    <span class="ml-3" x-show="sidebarOpen">Настройки</span>
                </a>
```

- [ ] **Step 4: Register settings router in main.py**

In `app/main.py`, add:

```python
from app.web.views.settings import router as settings_router  # noqa: E402
app.include_router(settings_router)
```

- [ ] **Step 5: Run smoke test**

Run: `python -c "from app.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add app/web/views/settings.py app/web/templates/settings.html app/web/templates/base.html app/main.py
git commit -m "feat: Settings web page with tabs (LLM, TG, SSH keys, Schedule, Users)"
```

---

### Task 10: Update Server Edit — SSH Key Dropdown

**Files:**
- Modify: `app/web/views/servers.py`
- Modify: `app/web/templates/server_edit.html`

- [ ] **Step 1: Update server_create_form and server_edit_form to pass SSH keys**

In `app/web/views/servers.py`, add import:

```python
from app.db.models import Server, ServerCheck, SshKey
```

In `server_create_form`, `server_edit_form` — query ssh_keys and pass to template:

```python
async with get_session() as session:
    result = await session.execute(select(SshKey).order_by(SshKey.name))
    ssh_keys = result.scalars().all()
```

Pass `"ssh_keys": ssh_keys` to template context.

- [ ] **Step 2: Update server_create and server_edit to use ssh_key_id**

In `server_create` POST handler, replace `ssh_key_path`/`ssh_password` with:

```python
ssh_key_id_raw = form.get("ssh_key_id") or ""
server = Server(
    name=name,
    host=host,
    ssh_user=(form.get("ssh_user") or "deploy").strip(),
    ssh_key_id=int(ssh_key_id_raw) if ssh_key_id_raw else None,
    ssh_port=int(form.get("ssh_port") or 22),
    enabled=form.get("enabled") == "on",
)
```

Same for `server_edit` POST handler.

- [ ] **Step 3: Update server_edit.html template**

Replace the SSH Key Path and SSH Password fields with a dropdown:

```html
<!-- SSH Key -->
<div class="col-span-2">
    <label class="block text-xs font-medium text-gray-500 mb-1">SSH ключ</label>
    <select name="ssh_key_id"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
        <option value="">По умолчанию (глобальный)</option>
        {% for key in ssh_keys %}
        <option value="{{ key.id }}"
                {{ 'selected' if server and server.ssh_key_id == key.id else '' }}>
            {{ key.name }}{% if key.is_default %} (default){% endif %}
        </option>
        {% endfor %}
    </select>
    {% if not ssh_keys %}
    <p class="text-xs text-amber-600 mt-1">
        Нет SSH ключей. <a href="/settings#ssh" class="underline">Добавьте в Настройках</a>.
    </p>
    {% endif %}
</div>
```

Remove the SSH Key Path and SSH Password input blocks entirely.

- [ ] **Step 4: Run app and verify**

Run: `python -c "from app.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/web/views/servers.py app/web/templates/server_edit.html
git commit -m "feat: server edit uses SSH key dropdown instead of key path"
```

---

### Task 11: Update Scheduler — Use SettingsService for TG Config

**Files:**
- Modify: `app/scheduler/tasks.py:27-38`

- [ ] **Step 1: Update _notify_tg to read TG config from DB**

In `app/scheduler/tasks.py`, modify `_notify_tg` and `_collect_task_async` to use `SettingsService` for hot-reloadable settings:

```python
async def _notify_tg(incident: dict, thread_id: str, host: str) -> None:
    """Send incident notification to Telegram."""
    from app.services.settings import SettingsService
    from app.db.session import get_session

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
        interrupt_data={"incident": incident, "host": host},
    )
```

- [ ] **Step 2: Update _collect_task_async to resolve SSH key from DB**

In `_collect_task_async`, replace the `host_config` construction with `resolve_ssh_config`:

```python
from app.agent.tool_provider import resolve_ssh_config

async with get_session() as session:
    # ... load server ...
    host_config = await resolve_ssh_config(session, server, settings.secret_key)
```

- [ ] **Step 3: Run existing scheduler tests**

Run: `python -m pytest tests/scheduler/ -v --tb=short`
Expected: pass (may need minor fixture updates)

- [ ] **Step 4: Commit**

```bash
git add app/scheduler/tasks.py
git commit -m "feat: scheduler reads TG config + SSH keys from DB"
```

---

### Task 12: Dashboard Alerts for Missing Config

**Files:**
- Modify: `app/web/views/dashboard.py`
- Modify: `app/web/templates/dashboard.html`

- [ ] **Step 1: Add missing-config check to dashboard view**

In `app/web/views/dashboard.py`, add after stats computation:

```python
from app.db.models import CheckRun, Incident, Server, SshKey, Setting
from app.services.settings import SettingsService
from app.config import settings as env_settings

# Check for missing configuration
alerts = []
svc = SettingsService(secret_key=env_settings.secret_key)
async with get_session() as session:
    app_settings = await svc.get_cached(session)

    if not app_settings.get("aitunnel_api_key") and not env_settings.aitunnel_api_key:
        alerts.append({"msg": "API ключ LLM не задан", "link": "/settings#llm"})

    if not app_settings.get("tg_bot_token") and not env_settings.tg_bot_token:
        alerts.append({"msg": "Telegram бот не настроен", "link": "/settings#telegram"})

    ssh_key_count = (await session.execute(
        select(func.count(SshKey.id))
    )).scalar() or 0
    if ssh_key_count == 0:
        alerts.append({"msg": "Нет SSH ключей", "link": "/settings#ssh"})
```

Pass `"alerts": alerts` to template context.

- [ ] **Step 2: Add alert banner to dashboard.html**

In `app/web/templates/dashboard.html`, add before the stats cards section:

```html
{% if alerts %}
<div class="mb-6 space-y-2">
    {% for alert in alerts %}
    <div class="p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between">
        <span class="text-sm text-amber-800">{{ alert.msg }}</span>
        <a href="{{ alert.link }}" class="text-sm text-amber-600 underline hover:text-amber-800">Настроить</a>
    </div>
    {% endfor %}
</div>
{% endif %}
```

- [ ] **Step 3: Commit**

```bash
git add app/web/views/dashboard.py app/web/templates/dashboard.html
git commit -m "feat: dashboard shows alerts for missing config (API key, TG, SSH)"
```

---

### Task 13: Full Integration Smoke Test

**Files:** None (verification only)

- [ ] **Step 1: Run complete test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all pass

- [ ] **Step 2: Start Docker stack and test manually**

```bash
docker compose build
docker compose up -d
# Wait for DB to be ready
docker compose logs app --tail=20
```

- [ ] **Step 3: Verify seed ran**

Check logs for `seeded_setting` and `seeded_admin_user` messages.

- [ ] **Step 4: Test Settings page**

```bash
# Login
curl -s -c /tmp/cook.txt -X POST http://localhost:8000/login \
  -d "username=admin&password=changeme" -o /dev/null -w "%{http_code}"
# Should return 302

# Open settings page
curl -s -b /tmp/cook.txt http://localhost:8000/settings -o /tmp/settings.html -w "%{http_code}"
# Should return 200
```

- [ ] **Step 5: Test SSH key creation via UI**

Open `http://localhost:8000/settings#ssh` in browser, add a test key, verify it appears in the server edit dropdown.

- [ ] **Step 6: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: web settings complete — env to DB migration with SSH keys and multi-admin"
```
