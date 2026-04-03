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
