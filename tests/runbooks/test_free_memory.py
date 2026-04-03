"""Tests for FreeMemoryRunbook."""

import pytest

from app.runbooks.base import RunbookResult
from app.runbooks.free_memory import FreeMemoryRunbook


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


class TestFreeMemoryRunbook:
    """Tests for FreeMemoryRunbook."""

    def _make_runbook(self, response: str) -> FreeMemoryRunbook:
        tool = MockTool("ssh_exec", response)
        return FreeMemoryRunbook(tools=[tool])

    async def test_success_free_memory(self):
        """Successful cache drop returns RunbookResult with success=True."""
        runbook = self._make_runbook("")
        result = await runbook.execute({})
        assert isinstance(result, RunbookResult)
        assert result.success is True

    async def test_success_message_mentions_memory(self):
        """Result message mentions memory/cache drop."""
        runbook = self._make_runbook("")
        result = await runbook.execute({})
        msg = result.message.lower()
        assert "память" in msg or "кэш" in msg or "cache" in msg or "memory" in msg

    async def test_no_required_params(self):
        """No required params — executes with empty params dict."""
        runbook = self._make_runbook("")
        result = await runbook.execute({})
        assert result.success is True

    async def test_correct_command_used(self):
        """Command drops page cache, dentries and inodes (level 3)."""
        called_with = {}

        class CaptureTool:
            name = "ssh_exec"

            async def ainvoke(self, params):
                called_with.update(params)
                return ""

        runbook = FreeMemoryRunbook(tools=[CaptureTool()])
        await runbook.execute({})
        assert "drop_caches" in called_with["command"]
        assert "sync" in called_with["command"]

    async def test_is_dangerous(self):
        runbook = self._make_runbook("")
        assert runbook.is_dangerous is True

    async def test_name(self):
        runbook = self._make_runbook("")
        assert runbook.name == "free_memory"
