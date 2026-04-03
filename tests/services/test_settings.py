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
