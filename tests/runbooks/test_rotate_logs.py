"""Tests for RotateLogsRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.rotate_logs import RotateLogsRunbook


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestRotateLogsRunbook:
    """Tests for RotateLogsRunbook."""

    def _make_runbook(self, response: str) -> RotateLogsRunbook:
        tool = MockTool("ssh_exec", response)
        return RotateLogsRunbook(tools=[tool])

    async def test_success_rotate(self):
        """Successful log rotation returns RunbookResult with success=True."""
        runbook = self._make_runbook("rotating /var/log/apache2/*.log\n")
        result = await runbook.execute({"config": "apache2"})
        assert isinstance(result, RunbookResult)
        assert result.success is True
        assert "apache2" in result.message

    async def test_missing_config_returns_failure(self):
        """Missing 'config' param must return failure without calling SSH."""
        runbook = self._make_runbook("")
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)
        assert result.success is False
        assert "config" in result.message.lower()

    async def test_is_dangerous(self):
        runbook = self._make_runbook("")
        assert runbook.is_dangerous is True

    async def test_name(self):
        runbook = self._make_runbook("")
        assert runbook.name == "rotate_logs"

    async def test_config_used_in_command(self):
        """config param is inserted into the logrotate command."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return "rotating\n"

        runbook = RotateLogsRunbook(tools=[CaptureTool()])
        await runbook.execute({"config": "nginx"})
        assert "/etc/logrotate.d/nginx" in called_with["command"]
