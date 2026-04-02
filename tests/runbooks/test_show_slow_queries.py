"""Tests for ShowSlowQueriesRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.show_slow_queries import ShowSlowQueriesRunbook
from tests.runbooks.conftest import MockTool

SLOW_QUERY_OUTPUT = """\
# Time: 2026-04-01T10:23:45.000000Z
# User@Host: app[app] @ web-01 [10.0.0.5]
# Query_time: 12.345678  Lock_time: 0.000123 Rows_sent: 1  Rows_examined: 500000
SET timestamp=1711962225;
SELECT * FROM orders WHERE created_at > '2026-01-01';
"""


class TestShowSlowQueriesRunbook:
    """Tests for ShowSlowQueriesRunbook."""

    def _make_runbook(self, exit_code: int, stdout: str = "", stderr: str = "") -> ShowSlowQueriesRunbook:
        tool = MockTool(
            "ssh_exec",
            {"stdout": stdout, "stderr": stderr, "exit_code": exit_code},
        )
        return ShowSlowQueriesRunbook(tools=[tool])

    async def test_success_show(self):
        runbook = self._make_runbook(exit_code=0, stdout=SLOW_QUERY_OUTPUT)
        result = await runbook.execute({
            "host": "db-01",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is True
        assert "SELECT" in result.details

    async def test_failure_show(self):
        runbook = self._make_runbook(
            exit_code=1,
            stderr="tail: cannot open '/var/log/mysql/slow.log' for reading: No such file",
        )
        result = await runbook.execute({
            "host": "db-01",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert isinstance(result, RunbookResult)
        assert result.success is False

    async def test_is_not_dangerous(self):
        runbook = self._make_runbook(exit_code=0)
        assert runbook.is_dangerous is False

    async def test_name(self):
        runbook = self._make_runbook(exit_code=0)
        assert runbook.name == "show_slow_queries"

    async def test_custom_lines_and_log_path(self):
        runbook = self._make_runbook(exit_code=0, stdout=SLOW_QUERY_OUTPUT)
        result = await runbook.execute({
            "host": "db-01",
            "lines": 100,
            "log_path": "/var/log/mysql/custom-slow.log",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert result.success is True

    async def test_default_params(self):
        """Lines defaults to 50, log_path to /var/log/mysql/slow.log."""
        runbook = self._make_runbook(exit_code=0, stdout="")
        result = await runbook.execute({
            "host": "db-01",
            "ssh_user": "deploy",
            "ssh_key_path": "/home/deploy/.ssh/id_rsa",
            "ssh_port": 22,
        })
        assert result.success is True
