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
