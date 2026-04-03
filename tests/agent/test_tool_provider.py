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
