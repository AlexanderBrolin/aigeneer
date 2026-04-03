"""Tests for ShowConnectionsRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.show_connections import ShowConnectionsRunbook


CONNECTIONS_OUTPUT = """\
State    Recv-Q  Send-Q  Local Address:Port  Peer Address:Port
ESTAB    0       0       10.0.0.1:80         10.0.0.2:54321  users:(("apache2",pid=1234))
ESTAB    0       0       10.0.0.1:3306       10.0.0.3:43210  users:(("mysqld",pid=5678))
LISTEN   0       128     0.0.0.0:22          0.0.0.0:*
"""


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestShowConnectionsRunbook:
    """Tests for ShowConnectionsRunbook."""

    def _make_runbook(self, response: str) -> ShowConnectionsRunbook:
        tool = MockTool("ssh_exec", response)
        return ShowConnectionsRunbook(tools=[tool])

    async def test_success_returns_runbook_result(self):
        runbook = self._make_runbook(CONNECTIONS_OUTPUT)
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)

    async def test_success_is_true(self):
        runbook = self._make_runbook(CONNECTIONS_OUTPUT)
        result = await runbook.execute({})
        assert result.success is True

    async def test_output_in_details(self):
        runbook = self._make_runbook(CONNECTIONS_OUTPUT)
        result = await runbook.execute({})
        assert CONNECTIONS_OUTPUT in result.details

    async def test_default_count_50(self):
        """Default count is 50 — command uses head -n 51."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return CONNECTIONS_OUTPUT

        runbook = ShowConnectionsRunbook(tools=[CaptureTool()])
        await runbook.execute({})
        assert "head -n 51" in called_with["command"]

    async def test_custom_count(self):
        """count param changes the head line count to count+1."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return CONNECTIONS_OUTPUT

        runbook = ShowConnectionsRunbook(tools=[CaptureTool()])
        await runbook.execute({"count": 10})
        assert "head -n 11" in called_with["command"]

    async def test_is_not_dangerous(self):
        runbook = self._make_runbook(CONNECTIONS_OUTPUT)
        assert runbook.is_dangerous is False

    async def test_name(self):
        runbook = self._make_runbook(CONNECTIONS_OUTPUT)
        assert runbook.name == "show_connections"
