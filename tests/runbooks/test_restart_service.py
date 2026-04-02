"""Tests for RestartServiceRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.restart_service import RestartServiceRunbook
from tests.runbooks.conftest import MockTool


class TestRestartServiceRunbook:
    """Tests for RestartServiceRunbook."""

    def _make_runbook(self, exit_code: int, stdout: str = "", stderr: str = "") -> RestartServiceRunbook:
        tool = MockTool(
            "ssh_systemctl_restart",
            {"stdout": stdout, "stderr": stderr, "exit_code": exit_code},
        )
        return RestartServiceRunbook(tools=[tool])

    async def test_success_restart(self):
        runbook = self._make_runbook(exit_code=0, stdout="")
        result = await runbook.execute({
            "host": "web-01",
            "service": "apache2",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is True
        assert "apache2" in result.message

    async def test_failure_restart(self):
        runbook = self._make_runbook(
            exit_code=1,
            stderr="Failed to restart apache2.service: Unit not found.",
        )
        result = await runbook.execute({
            "host": "web-01",
            "service": "apache2",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "apache2" in result.message

    async def test_is_dangerous(self):
        runbook = self._make_runbook(exit_code=0)
        assert runbook.is_dangerous is True

    async def test_name(self):
        runbook = self._make_runbook(exit_code=0)
        assert runbook.name == "restart_service"

    async def test_stderr_in_details_on_failure(self):
        error_msg = "Failed to restart mariadb.service: Connection timed out"
        runbook = self._make_runbook(exit_code=1, stderr=error_msg)
        result = await runbook.execute({
            "host": "db-01",
            "service": "mariadb",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert result.success is False
        assert error_msg in result.details
