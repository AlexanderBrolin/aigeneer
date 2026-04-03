"""Tests for ShowTopProcessesRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.show_top_processes import ShowTopProcessesRunbook


TOP_OUTPUT = """\
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
www-data  1234  5.2 12.3 456789 123456 ?       Sl   08:00   2:15 /usr/sbin/apache2
mysql     5678  2.1  8.4 789012  84321 ?       Ssl  08:00   1:30 /usr/sbin/mysqld
deploy    9012  0.5  1.2  12345   6789 pts/0   Ss   09:00   0:01 bash
"""


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestShowTopProcessesRunbook:
    """Tests for ShowTopProcessesRunbook."""

    def _make_runbook(self, response: str) -> ShowTopProcessesRunbook:
        tool = MockTool("ssh_exec", response)
        return ShowTopProcessesRunbook(tools=[tool])

    async def test_success_returns_runbook_result(self):
        runbook = self._make_runbook(TOP_OUTPUT)
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)

    async def test_success_is_true(self):
        runbook = self._make_runbook(TOP_OUTPUT)
        result = await runbook.execute({})
        assert result.success is True

    async def test_output_in_details(self):
        runbook = self._make_runbook(TOP_OUTPUT)
        result = await runbook.execute({})
        assert TOP_OUTPUT in result.details

    async def test_default_count_20(self):
        """Default count is 20 — command uses head -n 21."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return TOP_OUTPUT

        runbook = ShowTopProcessesRunbook(tools=[CaptureTool()])
        await runbook.execute({})
        assert "head -n 21" in called_with["command"]

    async def test_custom_count(self):
        """count param changes the head line count to count+1."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return TOP_OUTPUT

        runbook = ShowTopProcessesRunbook(tools=[CaptureTool()])
        await runbook.execute({"count": 5})
        assert "head -n 6" in called_with["command"]

    async def test_is_not_dangerous(self):
        runbook = self._make_runbook(TOP_OUTPUT)
        assert runbook.is_dangerous is False

    async def test_name(self):
        runbook = self._make_runbook(TOP_OUTPUT)
        assert runbook.name == "show_top_processes"
