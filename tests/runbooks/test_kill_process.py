"""Tests for KillProcessRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.kill_process import KillProcessRunbook


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestKillProcessRunbook:
    """Tests for KillProcessRunbook."""

    def _make_runbook(self, response: str) -> KillProcessRunbook:
        tool = MockTool("ssh_exec", response)
        return KillProcessRunbook(tools=[tool])

    async def test_success_kill(self):
        """Successful kill returns RunbookResult with success=True."""
        runbook = self._make_runbook("")
        result = await runbook.execute({"pid": "1234"})
        assert isinstance(result, RunbookResult)
        assert result.success is True
        assert "1234" in result.message

    async def test_success_with_custom_signal(self):
        """Custom signal is used in the kill command."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return ""

        runbook = KillProcessRunbook(tools=[CaptureTool()])
        result = await runbook.execute({"pid": "5678", "signal": 9})
        assert result.success is True
        assert "-9" in called_with["command"]
        assert "5678" in called_with["command"]

    async def test_default_signal_15(self):
        """Default signal is 15 (SIGTERM)."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return ""

        runbook = KillProcessRunbook(tools=[CaptureTool()])
        await runbook.execute({"pid": "9999"})
        assert "-15" in called_with["command"]

    async def test_missing_pid_returns_failure(self):
        """Missing 'pid' param must return failure without calling SSH."""
        runbook = self._make_runbook("")
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "pid" in result.message.lower()

    async def test_is_dangerous(self):
        runbook = self._make_runbook("")
        assert runbook.is_dangerous is True

    async def test_name(self):
        runbook = self._make_runbook("")
        assert runbook.name == "kill_process"
