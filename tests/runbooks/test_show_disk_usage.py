"""Tests for ShowDiskUsageRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.show_disk_usage import ShowDiskUsageRunbook


DISK_USAGE_OUTPUT = """\
4.5G\t/var/log
2.1G\t/var/lib
1.3G\t/usr/share
500M\t/var/cache
200M\t/tmp
"""


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestShowDiskUsageRunbook:
    """Tests for ShowDiskUsageRunbook."""

    def _make_runbook(self, response: str) -> ShowDiskUsageRunbook:
        tool = MockTool("ssh_exec", response)
        return ShowDiskUsageRunbook(tools=[tool])

    async def test_success_returns_runbook_result(self):
        runbook = self._make_runbook(DISK_USAGE_OUTPUT)
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)

    async def test_success_is_true(self):
        runbook = self._make_runbook(DISK_USAGE_OUTPUT)
        result = await runbook.execute({})
        assert result.success is True

    async def test_output_in_details(self):
        runbook = self._make_runbook(DISK_USAGE_OUTPUT)
        result = await runbook.execute({})
        assert DISK_USAGE_OUTPUT in result.details

    async def test_default_path_and_count(self):
        """Defaults: path='/', count=20."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return DISK_USAGE_OUTPUT

        runbook = ShowDiskUsageRunbook(tools=[CaptureTool()])
        await runbook.execute({})
        assert "/*" in called_with["command"]
        assert "head -n 20" in called_with["command"]

    async def test_custom_path(self):
        """Custom path is used in command."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return DISK_USAGE_OUTPUT

        runbook = ShowDiskUsageRunbook(tools=[CaptureTool()])
        await runbook.execute({"path": "/var"})
        assert "/var/*" in called_with["command"]

    async def test_custom_count(self):
        """Custom count is used in command."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return DISK_USAGE_OUTPUT

        runbook = ShowDiskUsageRunbook(tools=[CaptureTool()])
        await runbook.execute({"count": 5})
        assert "head -n 5" in called_with["command"]

    async def test_is_not_dangerous(self):
        runbook = self._make_runbook(DISK_USAGE_OUTPUT)
        assert runbook.is_dangerous is False

    async def test_name(self):
        runbook = self._make_runbook(DISK_USAGE_OUTPUT)
        assert runbook.name == "show_disk_usage"
