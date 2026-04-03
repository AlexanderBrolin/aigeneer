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
