"""Tests for ClearOldLogsRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.clear_old_logs import ClearOldLogsRunbook
from tests.runbooks.conftest import MockTool


class TestClearOldLogsRunbook:
    """Tests for ClearOldLogsRunbook."""

    def _make_runbook(self, exit_code: int, stdout: str = "", stderr: str = "") -> ClearOldLogsRunbook:
        tool = MockTool(
            "ssh_exec",
            {"stdout": stdout, "stderr": stderr, "exit_code": exit_code},
        )
        return ClearOldLogsRunbook(tools=[tool])

    async def test_success_clear(self):
        runbook = self._make_runbook(exit_code=0)
        result = await runbook.execute({
            "host": "web-01",
            "log_path": "/var/log/apache2",
            "older_than_days": 30,
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is True

    async def test_failure_clear(self):
        runbook = self._make_runbook(
            exit_code=1,
            stderr="find: '/var/log/apache2': Permission denied",
        )
        result = await runbook.execute({
            "host": "web-01",
            "log_path": "/var/log/apache2",
            "older_than_days": 30,
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "Permission denied" in result.details

    async def test_is_dangerous(self):
        runbook = self._make_runbook(exit_code=0)
        assert runbook.is_dangerous is True

    async def test_name(self):
        runbook = self._make_runbook(exit_code=0)
        assert runbook.name == "clear_old_logs"
