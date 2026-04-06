"""Tests for scheduler tasks: run_all_checks and collect_task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.checks.base import Signal
from app.db.models import CheckRun, Server, ServerCheck


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_server(session: AsyncSession, *, enabled: bool = True, checks: list[dict] | None = None) -> int:
    """Insert a Server with optional ServerCheck rows. Return server.id."""
    server = Server(
        name="test-server",
        host="10.0.0.1",
        ssh_user="deploy",
        ssh_port=22,
        enabled=enabled,
    )
    session.add(server)
    await session.flush()

    for chk in checks or []:
        session.add(
            ServerCheck(
                server_id=server.id,
                check_name=chk.get("check_name", "disk_space"),
                params=chk.get("params", {}),
                enabled=chk.get("enabled", True),
            )
        )
    await session.flush()
    return server.id


# ---------------------------------------------------------------------------
# run_all_checks
# ---------------------------------------------------------------------------


class TestRunAllChecks:
    """Tests for the run_all_checks dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatches_for_enabled_servers(self, db_session: AsyncSession):
        """run_all_checks should dispatch collect_task for each enabled server with checks."""
        server_id = await _seed_server(
            db_session,
            checks=[{"check_name": "disk_space", "params": {"threshold_warning": 80}}],
        )
        await db_session.commit()

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.collect_task") as mock_collect,
        ):
            # Make get_session return our test session
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _run_all_checks_async

            result = await _run_all_checks_async()

        assert "test-server" in result["dispatched"]
        mock_collect.delay.assert_called_once_with(server_id)

    @pytest.mark.asyncio
    async def test_skips_servers_without_enabled_checks(self, db_session: AsyncSession):
        """Servers with no enabled checks should be skipped."""
        await _seed_server(
            db_session,
            checks=[{"check_name": "disk_space", "enabled": False}],
        )
        await db_session.commit()

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.collect_task") as mock_collect,
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _run_all_checks_async

            result = await _run_all_checks_async()

        assert result["dispatched"] == []
        mock_collect.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_disabled_servers(self, db_session: AsyncSession):
        """Disabled servers should not be dispatched."""
        await _seed_server(
            db_session,
            enabled=False,
            checks=[{"check_name": "disk_space"}],
        )
        await db_session.commit()

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.collect_task") as mock_collect,
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _run_all_checks_async

            result = await _run_all_checks_async()

        assert result["dispatched"] == []
        mock_collect.delay.assert_not_called()


# ---------------------------------------------------------------------------
# collect_task
# ---------------------------------------------------------------------------


class TestCollectTask:
    """Tests for the collect_task runner."""

    @pytest.mark.asyncio
    async def test_creates_check_run_and_runs_checks(self, db_session: AsyncSession):
        """collect_task should create a CheckRun and execute each check."""
        server_id = await _seed_server(
            db_session,
            checks=[{"check_name": "disk_space", "params": {"threshold_warning": 80}}],
        )
        await db_session.commit()

        mock_check_instance = AsyncMock()
        mock_check_instance.run = AsyncMock(return_value=[])  # no signals

        mock_check_cls = MagicMock(return_value=mock_check_instance)

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.CHECK_REGISTRY", {"disk_space": mock_check_cls}),
            patch("app.scheduler.tasks.get_read_tools", return_value=[MagicMock()]),
        ):
            # Return the test session every time get_session is called
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _collect_task_async

            result = await _collect_task_async(server_id)

        assert result["status"] == "ok"
        assert result["signal_count"] == 0
        mock_check_cls.assert_called_once()
        mock_check_instance.run.assert_awaited_once()

        # Verify CheckRun was created and finalized
        check_runs = (await db_session.execute(select(CheckRun))).scalars().all()
        assert len(check_runs) == 1
        assert check_runs[0].status == "ok"
        assert check_runs[0].signal_count == 0
        assert check_runs[0].finished_at is not None

    @pytest.mark.asyncio
    async def test_signals_trigger_graph_invocation(self, db_session: AsyncSession):
        """When signals are found, the analyze graph should be invoked."""
        server_id = await _seed_server(
            db_session,
            checks=[{"check_name": "disk_space", "params": {}}],
        )
        await db_session.commit()

        test_signal = Signal(
            host="10.0.0.1",
            severity="warning",
            problem_type="disk_full",
            evidence="/var is 85% full",
        )

        mock_check_instance = AsyncMock()
        mock_check_instance.run = AsyncMock(return_value=[test_signal])
        mock_check_cls = MagicMock(return_value=mock_check_instance)

        # Mock the analyze graph
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "incidents": [
                {
                    "severity": "warning",
                    "problem_type": "disk_full",
                    "evidence": "/var is 85% full",
                    "dangerous_actions": [],
                    "safe_actions": [],
                }
            ]
        })

        mock_save = AsyncMock(return_value=42)

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.CHECK_REGISTRY", {"disk_space": mock_check_cls}),
            patch("app.agent.tool_provider.resolve_ssh_config", AsyncMock(return_value={"host": "10.0.0.1", "ssh_user": "root", "ssh_port": 22, "ssh_key_content": None})),
            patch("app.scheduler.tasks.get_read_tools", return_value=[MagicMock()]),
            patch("app.scheduler.tasks.run_analyze_graph", mock_graph.ainvoke),
            patch("app.scheduler.tasks.save_incident", mock_save),
            patch("app.scheduler.tasks.find_active_incident", AsyncMock(return_value=None)),
            patch("app.scheduler.tasks.update_incident_status", AsyncMock()),
            patch("app.scheduler.tasks._notify_tg", AsyncMock()),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _collect_task_async

            result = await _collect_task_async(server_id)

        assert result["status"] == "incident"
        assert result["signal_count"] == 1
        mock_graph.ainvoke.assert_awaited_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_check_is_skipped(self, db_session: AsyncSession):
        """An unknown check_name should be skipped without error."""
        server_id = await _seed_server(
            db_session,
            checks=[{"check_name": "nonexistent_check", "params": {}}],
        )
        await db_session.commit()

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.CHECK_REGISTRY", {}),
            patch("app.scheduler.tasks.get_read_tools", return_value=[]),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _collect_task_async

            result = await _collect_task_async(server_id)

        assert result["status"] == "ok"
        assert result["signal_count"] == 0

    @pytest.mark.asyncio
    async def test_server_not_found_returns_error(self, db_session: AsyncSession):
        """collect_task with a missing server_id should return an error dict."""
        with patch("app.scheduler.tasks.get_session") as mock_get_session:
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _collect_task_async

            result = await _collect_task_async(9999)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_check_exception_is_caught(self, db_session: AsyncSession):
        """A failing check should not crash the entire task."""
        server_id = await _seed_server(
            db_session,
            checks=[{"check_name": "disk_space", "params": {}}],
        )
        await db_session.commit()

        mock_check_instance = AsyncMock()
        mock_check_instance.run = AsyncMock(side_effect=RuntimeError("SSH timeout"))
        mock_check_cls = MagicMock(return_value=mock_check_instance)

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.CHECK_REGISTRY", {"disk_space": mock_check_cls}),
            patch("app.scheduler.tasks.get_read_tools", return_value=[MagicMock()]),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _collect_task_async

            result = await _collect_task_async(server_id)

        # Despite the error in the check, the task should complete
        assert result["status"] == "ok"
        assert result["signal_count"] == 0

    @pytest.mark.asyncio
    async def test_graph_failure_sets_error_status(self, db_session: AsyncSession):
        """If the analyze graph raises, the CheckRun should be marked as error."""
        server_id = await _seed_server(
            db_session,
            checks=[{"check_name": "disk_space", "params": {}}],
        )
        await db_session.commit()

        test_signal = Signal(
            host="10.0.0.1",
            severity="critical",
            problem_type="disk_full",
            evidence="/ is 95% full",
        )

        mock_check_instance = AsyncMock()
        mock_check_instance.run = AsyncMock(return_value=[test_signal])
        mock_check_cls = MagicMock(return_value=mock_check_instance)

        with (
            patch("app.scheduler.tasks.get_session") as mock_get_session,
            patch("app.scheduler.tasks.CHECK_REGISTRY", {"disk_space": mock_check_cls}),
            patch("app.scheduler.tasks.get_read_tools", return_value=[MagicMock()]),
            patch("app.agent.tool_provider.resolve_ssh_config", AsyncMock(return_value={"host": "10.0.0.1", "ssh_user": "root", "ssh_port": 22, "ssh_key_content": None})),
            patch(
                "app.scheduler.tasks.run_analyze_graph",
                AsyncMock(side_effect=RuntimeError("Redis down")),
            ),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=db_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_get_session.return_value = ctx

            from app.scheduler.tasks import _collect_task_async

            result = await _collect_task_async(server_id)

        assert result["status"] == "error"
        assert result["signal_count"] == 1

        # CheckRun in DB should be "error" too
        check_runs = (await db_session.execute(select(CheckRun))).scalars().all()
        assert len(check_runs) == 1
        assert check_runs[0].status == "error"


class TestCeleryWorkerConfig:
    """Tests for the Celery app configuration."""

    def test_beat_schedule_is_configured(self):
        from app.scheduler.worker import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "run-all-checks" in schedule
        assert schedule["run-all-checks"]["task"] == "app.scheduler.tasks.run_all_checks"

    def test_task_serializer_is_json(self):
        from app.scheduler.worker import celery_app

        assert celery_app.conf.task_serializer == "json"
