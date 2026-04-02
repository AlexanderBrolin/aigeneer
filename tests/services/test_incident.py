"""TDD tests for find_active_incident — time-based + actioned bypass logic."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.db.models import Incident
from app.services.incident import find_active_incident


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _mock_get_session(session):
    """Async ctx manager that yields the test session without auto-commit.
    Matches the interface of app.db.session.get_session.
    """
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@pytest.fixture
def patch_get_session(db_session):
    """Patch app.services.incident.get_session to use in-memory SQLite session."""
    with patch(
        "app.services.incident.get_session",
        lambda: _mock_get_session(db_session),
    ):
        yield db_session


async def _add_incident(
    session,
    *,
    host: str = "host-01",
    problem_type: str = "replication_down",
    severity: str = "critical",
    status: str = "notified",
    age_minutes: float = 0.0,
):
    """Insert an Incident with a controlled created_at age."""
    created_at = datetime.utcnow() - timedelta(minutes=age_minutes)
    inc = Incident(
        host=host,
        severity=severity,
        problem_type=problem_type,
        evidence="test evidence",
        status=status,
        created_at=created_at,
    )
    session.add(inc)
    await session.commit()
    await session.refresh(inc)
    return inc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_incident_allows(patch_get_session):
    """No existing incidents → always allow (return None)."""
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_recent_notified_blocks(patch_get_session):
    """notified incident younger than TTL → block (return incident)."""
    await _add_incident(patch_get_session, status="notified", severity="critical", age_minutes=5)
    result = await find_active_incident("host-01", "replication_down")
    assert result is not None


@pytest.mark.asyncio
async def test_old_notified_allows(patch_get_session):
    """notified incident older than TTL (30 min for critical) → allow (return None)."""
    await _add_incident(patch_get_session, status="notified", severity="critical", age_minutes=35)
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_old_new_status_allows(patch_get_session):
    """'new' status incident older than TTL → also expires (return None)."""
    await _add_incident(patch_get_session, status="new", severity="critical", age_minutes=31)
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_recent_actioned_bypasses_dedup(patch_get_session):
    """Recent actioned incident → fix was attempted, allow every-cycle re-notify (None)."""
    # An actioned incident (fix was attempted) + a fresh notified one for same host/problem
    await _add_incident(patch_get_session, status="actioned", age_minutes=3)
    await _add_incident(patch_get_session, status="notified", age_minutes=1)
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_old_actioned_does_not_bypass(patch_get_session):
    """Actioned incident older than 1 hour → does NOT bypass dedup."""
    await _add_incident(patch_get_session, status="actioned", age_minutes=70)
    await _add_incident(patch_get_session, status="notified", age_minutes=5)
    result = await find_active_incident("host-01", "replication_down")
    assert result is not None  # old actioned doesn't count → fresh notified blocks


@pytest.mark.asyncio
async def test_ignored_does_not_block(patch_get_session):
    """'ignored' status incident is not tracked → doesn't block re-notification."""
    await _add_incident(patch_get_session, status="ignored", age_minutes=2)
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_different_host_does_not_block(patch_get_session):
    """Incident on different host doesn't block other host."""
    await _add_incident(patch_get_session, host="host-02", status="notified", age_minutes=2)
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_different_problem_type_does_not_block(patch_get_session):
    """Incident with different problem_type doesn't block."""
    await _add_incident(patch_get_session, problem_type="disk_full", status="notified", age_minutes=2)
    result = await find_active_incident("host-01", "replication_down")
    assert result is None


@pytest.mark.asyncio
async def test_warning_severity_has_longer_ttl(patch_get_session):
    """warning incidents have 60 min TTL, not 30."""
    # 35 min old warning — should still block (60 min TTL)
    await _add_incident(
        patch_get_session, severity="warning", status="notified",
        problem_type="disk_full", age_minutes=35,
    )
    result = await find_active_incident("host-01", "disk_full")
    assert result is not None  # still within 60 min window


@pytest.mark.asyncio
async def test_warning_severity_expires_after_ttl(patch_get_session):
    """warning incident older than 60 min → expires."""
    await _add_incident(
        patch_get_session, severity="warning", status="notified",
        problem_type="disk_full", age_minutes=65,
    )
    result = await find_active_incident("host-01", "disk_full")
    assert result is None
