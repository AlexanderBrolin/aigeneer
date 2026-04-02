"""Tests for RestartReplicationRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.restart_replication import RestartReplicationRunbook
from tests.runbooks.conftest import MockTool, SequentialMockTool


SLAVE_STATUS_OK = """\
*************************** 1. row ***************************
             Slave_IO_Running: Yes
            Slave_SQL_Running: Yes
        Seconds_Behind_Master: 0
"""

SLAVE_STATUS_BROKEN = """\
*************************** 1. row ***************************
             Slave_IO_Running: No
            Slave_SQL_Running: No
        Seconds_Behind_Master: NULL
                   Last_Error: Could not execute Write_rows
"""


class TestRestartReplicationRunbook:
    """Tests for RestartReplicationRunbook."""

    def _make_runbook(self, responses: list[dict]) -> RestartReplicationRunbook:
        tool = SequentialMockTool("ssh_exec", responses)
        return RestartReplicationRunbook(tools=[tool])

    async def test_successful_restart(self):
        """STOP/START SLAVE succeeds and status shows IO=Yes, SQL=Yes."""
        runbook = self._make_runbook([
            # First call: STOP SLAVE; START SLAVE;
            {"stdout": "", "stderr": "", "exit_code": 0},
            # Second call: SHOW SLAVE STATUS
            {"stdout": SLAVE_STATUS_OK, "stderr": "", "exit_code": 0},
        ])
        result = await runbook.execute({
            "host": "db-01",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is True
        assert "replication" in result.message.lower() or "Репликация" in result.message

    async def test_failed_restart_command(self):
        """STOP/START SLAVE command itself fails."""
        runbook = self._make_runbook([
            {"stdout": "", "stderr": "ERROR 1045: Access denied", "exit_code": 1},
        ])
        result = await runbook.execute({
            "host": "db-01",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is False

    async def test_restart_ok_but_status_still_broken(self):
        """STOP/START succeeds but SHOW SLAVE STATUS still shows errors."""
        runbook = self._make_runbook([
            {"stdout": "", "stderr": "", "exit_code": 0},
            {"stdout": SLAVE_STATUS_BROKEN, "stderr": "", "exit_code": 0},
        ])
        result = await runbook.execute({
            "host": "db-01",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is False

    async def test_is_dangerous(self):
        tool = MockTool("ssh_exec", {"stdout": "", "stderr": "", "exit_code": 0})
        runbook = RestartReplicationRunbook(tools=[tool])
        assert runbook.is_dangerous is True

    async def test_name(self):
        tool = MockTool("ssh_exec", {"stdout": "", "stderr": "", "exit_code": 0})
        runbook = RestartReplicationRunbook(tools=[tool])
        assert runbook.name == "restart_replication"
