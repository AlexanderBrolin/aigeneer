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
