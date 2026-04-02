import pytest
from sqlalchemy import select

from app.db.models import AdminUser, CheckRun, Incident, Server, ServerCheck


@pytest.mark.asyncio
async def test_create_server(db_session):
    server = Server(name="web-01", host="web-01.example.com", ssh_user="deploy")
    db_session.add(server)
    await db_session.flush()

    assert server.id is not None
    assert server.name == "web-01"
    assert server.enabled is True
    assert server.ssh_port == 22


@pytest.mark.asyncio
async def test_server_with_checks(db_session):
    server = Server(name="db-01", host="db-01.example.com", ssh_user="root")
    db_session.add(server)
    await db_session.flush()

    check = ServerCheck(
        server_id=server.id,
        check_name="disk_space",
        params={"threshold_warning": 80, "threshold_critical": 90, "paths": ["/", "/var"]},
    )
    db_session.add(check)
    await db_session.flush()

    assert check.id is not None
    assert check.server_id == server.id
    assert check.params["threshold_warning"] == 80


@pytest.mark.asyncio
async def test_check_run_and_incident(db_session):
    server = Server(name="web-02", host="web-02.example.com")
    db_session.add(server)
    await db_session.flush()

    run = CheckRun(server_id=server.id, host="web-02.example.com", check_name="disk_space")
    db_session.add(run)
    await db_session.flush()

    assert run.status == "running"

    incident = Incident(
        check_run_id=run.id,
        host="web-02.example.com",
        severity="critical",
        problem_type="disk_full",
        evidence="Диск / заполнен на 95%",
    )
    db_session.add(incident)
    await db_session.flush()

    assert incident.id is not None
    assert incident.status == "new"
    assert incident.severity == "critical"


@pytest.mark.asyncio
async def test_admin_user(db_session):
    admin = AdminUser(username="admin", password_hash="hashed_password")
    db_session.add(admin)
    await db_session.flush()

    result = await db_session.execute(select(AdminUser).where(AdminUser.username == "admin"))
    fetched = result.scalar_one()
    assert fetched.is_active is True


@pytest.mark.asyncio
async def test_incident_enums(db_session):
    server = Server(name="web-03", host="web-03.example.com")
    db_session.add(server)
    await db_session.flush()

    run = CheckRun(server_id=server.id, host="web-03.example.com", check_name="services")
    db_session.add(run)
    await db_session.flush()

    for severity in ["critical", "warning", "info"]:
        inc = Incident(
            check_run_id=run.id,
            host="web-03.example.com",
            severity=severity,
            problem_type="test",
            evidence=f"Test {severity}",
        )
        db_session.add(inc)

    await db_session.flush()

    result = await db_session.execute(select(Incident).where(Incident.host == "web-03.example.com"))
    incidents = result.scalars().all()
    assert len(incidents) == 3
