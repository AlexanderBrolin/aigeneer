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
