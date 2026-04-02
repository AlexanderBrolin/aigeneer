"""Tests for runbook registry and run_runbook function."""

import pytest

from app.runbooks import RUNBOOK_REGISTRY, run_runbook
from app.runbooks.base import RunbookResult
from app.runbooks.restart_service import RestartServiceRunbook
from app.runbooks.restart_replication import RestartReplicationRunbook
from app.runbooks.clear_old_logs import ClearOldLogsRunbook
from app.runbooks.show_slow_queries import ShowSlowQueriesRunbook
from tests.runbooks.conftest import MockTool


class TestRunbookRegistry:
    """Tests for RUNBOOK_REGISTRY."""

    def test_all_runbooks_registered(self):
        assert "restart_service" in RUNBOOK_REGISTRY
        assert "restart_replication" in RUNBOOK_REGISTRY
        assert "clear_old_logs" in RUNBOOK_REGISTRY
        assert "show_slow_queries" in RUNBOOK_REGISTRY

    def test_registry_maps_to_correct_classes(self):
        assert RUNBOOK_REGISTRY["restart_service"] is RestartServiceRunbook
        assert RUNBOOK_REGISTRY["restart_replication"] is RestartReplicationRunbook
        assert RUNBOOK_REGISTRY["clear_old_logs"] is ClearOldLogsRunbook
        assert RUNBOOK_REGISTRY["show_slow_queries"] is ShowSlowQueriesRunbook


class TestRunRunbook:
    """Tests for run_runbook() helper."""

    async def test_unknown_runbook_returns_failure(self):
        result = await run_runbook("nonexistent_runbook", {}, [])
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "nonexistent_runbook" in result.message

    async def test_run_known_runbook(self):
        tool = MockTool(
            "ssh_systemctl_restart",
            {"stdout": "", "stderr": "", "exit_code": 0},
        )
        result = await run_runbook(
            "restart_service",
            {
                "host": "web-01",
                "service": "apache2",
                "ssh_user": "deploy",
                "ssh_key_path": "/home/deploy/.ssh/id_rsa",
                "ssh_port": 22,
            },
            [tool],
        )
        assert isinstance(result, RunbookResult)
        assert result.success is True
