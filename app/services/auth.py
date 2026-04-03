"""Password hashing and DB-backed user verification."""

import bcrypt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminUser


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


async def verify_credentials_db(session: AsyncSession, username: str, password: str) -> bool:
    """Check username/password against admin_users table."""
    result = await session.execute(
        select(AdminUser).where(AdminUser.username == username, AdminUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return False
    return verify_password(password, user.password_hash)
