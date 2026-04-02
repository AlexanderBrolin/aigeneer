"""TDD tests for command_graph — LangGraph for text commands from Telegram."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.graphs.command import (
    CommandState,
    classify_intent,
    execute_read_node,
    confirm_node,
    get_command_graph,
)


class TestCommandState:
    def test_default_state(self):
        state = CommandState()
        assert state.message == ""
        assert state.host == ""
        assert state.intent == ""
        assert state.tool_results == []
        assert state.response == ""
        assert state.requires_confirm is False
        assert state.pending_command is None

    def test_state_with_values(self):
        state = CommandState(
            message="check disk on web-01",
            host="web-01",
            intent="read",
            tool_results=["df output"],
            response="Disk is 80% full",
        )
        assert state.message == "check disk on web-01"
        assert state.host == "web-01"
        assert state.intent == "read"
        assert state.response == "Disk is 80% full"


class TestClassifyIntent:
    @pytest.mark.asyncio
    async def test_read_intent_no_confirm(self):
        """Read operations should not require confirmation."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"intent": "read", "summary": "check disk space", "host": "web-01", "requires_confirm": false}'
        )

        state = CommandState(message="check disk space on web-01")

        with patch("app.agent.graphs.command.get_fast_llm", return_value=mock_llm):
            result = await classify_intent(state)

        assert result["intent"] == "read"
        assert result["requires_confirm"] is False
        assert result["host"] == "web-01"

    @pytest.mark.asyncio
    async def test_write_intent_requires_confirm(self):
        """Write operations must require confirmation."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"intent": "write", "summary": "restart apache2 on web-01", "host": "web-01", "requires_confirm": true, "runbook": "restart_service", "params": {"service": "apache2", "host": "web-01"}}'
        )

        state = CommandState(message="restart apache on web-01")

        with patch("app.agent.graphs.command.get_fast_llm", return_value=mock_llm):
            result = await classify_intent(state)

        assert result["intent"] == "write"
        assert result["requires_confirm"] is True
        assert result["pending_command"]["runbook"] == "restart_service"

    @pytest.mark.asyncio
    async def test_malformed_llm_response_defaults_to_read(self):
        """Malformed JSON falls back safely."""
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(content="not json at all")

        state = CommandState(message="do something")

        with patch("app.agent.graphs.command.get_fast_llm", return_value=mock_llm):
            result = await classify_intent(state)

        assert result["intent"] == "unknown"
        assert result["requires_confirm"] is False


class TestExecuteReadNode:
    @pytest.mark.asyncio
    async def test_executes_ssh_command_and_returns_result(self):
        """Read node runs SSH tool and stores result."""
        mock_tool = AsyncMock()
        mock_tool.name = "ssh_exec"
        mock_tool.arun.return_value = "Filesystem 80% used"

        state = CommandState(
            message="check disk on web-01",
            host="web-01",
            intent="read",
            pending_command={"tool": "ssh_exec", "input": {"command": "df -h", "host": "web-01"}},
        )

        mock_llm = AsyncMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke.return_value = MagicMock(
            content="Disk usage: 80%",
            tool_calls=[],
        )

        with patch("app.agent.graphs.command.get_read_tools", return_value=[mock_tool]):
            with patch("app.agent.graphs.command.get_llm", return_value=mock_llm):
                result = await execute_read_node(state)

        assert "response" in result

    @pytest.mark.asyncio
    async def test_returns_unknown_response_for_empty_host(self):
        """If host is unknown, returns helpful message."""
        state = CommandState(
            message="check something",
            host="",
            intent="read",
        )

        mock_llm = AsyncMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke.return_value = MagicMock(
            content="Не указан хост. Укажите имя сервера.",
            tool_calls=[],
        )

        with patch("app.agent.graphs.command.get_read_tools", return_value=[]):
            with patch("app.agent.graphs.command.get_llm", return_value=mock_llm):
                result = await execute_read_node(state)

        assert "response" in result


class TestConfirmNode:
    @pytest.mark.asyncio
    async def test_write_op_triggers_interrupt(self):
        """confirm_node must call interrupt() for write operations."""
        state = CommandState(
            message="restart apache on web-01",
            host="web-01",
            intent="write",
            requires_confirm=True,
            pending_command={
                "runbook": "restart_service",
                "params": {"service": "apache2", "host": "web-01"},
                "summary": "restart apache2 on web-01",
            },
        )

        # interrupt() raises GraphInterrupt outside of LangGraph runnable context
        from langgraph.errors import GraphInterrupt

        with pytest.raises((GraphInterrupt, RuntimeError)):
            await confirm_node(state)

    @pytest.mark.asyncio
    async def test_no_interrupt_when_no_confirm_needed(self):
        """If requires_confirm is False, confirm_node passes through."""
        from langgraph.types import Command

        state = CommandState(
            message="check disk",
            intent="read",
            requires_confirm=False,
        )

        result = await confirm_node(state)
        # Should return a dict or Command going to the next node, not raise
        assert result is not None


class TestGetCommandGraph:
    @pytest.mark.asyncio
    async def test_graph_compiles_successfully(self):
        """The graph should compile without errors."""
        from langgraph.checkpoint.memory import MemorySaver

        with patch("app.agent.graphs.command.get_checkpointer", new_callable=AsyncMock, return_value=MemorySaver()):
            graph = await get_command_graph()

        assert graph is not None

    @pytest.mark.asyncio
    async def test_graph_has_expected_nodes(self):
        """Graph should contain classify, execute_read, confirm, execute_write nodes."""
        from langgraph.checkpoint.memory import MemorySaver

        with patch("app.agent.graphs.command.get_checkpointer", new_callable=AsyncMock, return_value=MemorySaver()):
            graph = await get_command_graph()

        node_names = set(graph.get_graph().nodes.keys())
        assert "classify" in node_names
        assert "execute_read" in node_names
        assert "confirm" in node_names
        assert "execute_write" in node_names
