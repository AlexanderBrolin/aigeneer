"""Tests for MysqlProcesslistRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.mysql_processlist import MysqlProcesslistRunbook


PROCESSLIST_OUTPUT = """\
+-----+-------+-----------+----------+---------+------+-------+------------------+
| Id  | User  | Host      | db       | Command | Time | State | Info             |
+-----+-------+-----------+----------+---------+------+-------+------------------+
|   1 | app   | web-01:54 | mydb     | Query   |    0 | NULL  | SHOW FULL PROC.. |
|   2 | root  | localhost | NULL     | Sleep   |  120 | NULL  | NULL             |
+-----+-------+-----------+----------+---------+------+-------+------------------+
"""


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestMysqlProcesslistRunbook:
    """Tests for MysqlProcesslistRunbook."""

    def _make_runbook(self, response: str) -> MysqlProcesslistRunbook:
        tool = MockTool("ssh_mysql_exec", response)
        return MysqlProcesslistRunbook(tools=[tool])

    async def test_success_returns_runbook_result(self):
        runbook = self._make_runbook(PROCESSLIST_OUTPUT)
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)

    async def test_success_is_true(self):
        runbook = self._make_runbook(PROCESSLIST_OUTPUT)
        result = await runbook.execute({})
        assert result.success is True

    async def test_output_in_details(self):
        runbook = self._make_runbook(PROCESSLIST_OUTPUT)
        result = await runbook.execute({})
        assert PROCESSLIST_OUTPUT in result.details

    async def test_uses_ssh_mysql_exec_tool(self):
        """Runbook must use ssh_mysql_exec, not ssh_exec."""
        called_with = {}

        class CaptureMysqlTool:
            name = "ssh_mysql_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return PROCESSLIST_OUTPUT

        runbook = MysqlProcesslistRunbook(tools=[CaptureMysqlTool()])
        result = await runbook.execute({})
        assert result.success is True
        assert "SHOW FULL PROCESSLIST" in called_with.get("query", called_with.get("command", ""))

    async def test_fails_if_ssh_exec_instead_of_mysql(self):
        """Runbook raises RuntimeError (wraps StopIteration) if only ssh_exec is provided."""
        tool = MockTool("ssh_exec", PROCESSLIST_OUTPUT)
        runbook = MysqlProcesslistRunbook(tools=[tool])
        with pytest.raises((StopIteration, RuntimeError)):
            await runbook.execute({})

    async def test_is_not_dangerous(self):
        runbook = self._make_runbook(PROCESSLIST_OUTPUT)
        assert runbook.is_dangerous is False

    async def test_name(self):
        runbook = self._make_runbook(PROCESSLIST_OUTPUT)
        assert runbook.name == "mysql_processlist"
