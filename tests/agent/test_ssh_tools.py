"""Tests for SSH tools and tool_provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.ssh_tools import (
    SSHExecTool,
    SSHMysqlExecTool,
    SSHReadFileTool,
    SSHSystemctlRestartTool,
    SSHSystemctlStatusTool,
)
from app.agent.tool_provider import get_read_tools, get_write_tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ssh_result():
    """Standard successful SSH result mock."""
    result = MagicMock()
    result.stdout = "mock output"
    result.stderr = ""
    result.exit_status = 0
    return result


@pytest.fixture
def mock_ssh_connection(mock_ssh_result):
    """Patch asyncssh.connect to return a mock connection."""
    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_ssh_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    with patch("app.agent.ssh_tools.asyncssh.connect", return_value=mock_conn) as mock_connect:
        yield mock_connect, mock_conn


# ---------------------------------------------------------------------------
# Instantiation tests
# ---------------------------------------------------------------------------

class TestToolInstantiation:
    def test_ssh_exec_tool_creates(self):
        tool = SSHExecTool()
        assert tool.name == "ssh_exec"

    def test_ssh_read_file_tool_creates(self):
        tool = SSHReadFileTool()
        assert tool.name == "ssh_read_file"

    def test_ssh_systemctl_status_tool_creates(self):
        tool = SSHSystemctlStatusTool()
        assert tool.name == "ssh_systemctl_status"

    def test_ssh_systemctl_restart_tool_creates(self):
        tool = SSHSystemctlRestartTool()
        assert tool.name == "ssh_systemctl_restart"

    def test_ssh_mysql_exec_tool_creates(self):
        tool = SSHMysqlExecTool()
        assert tool.name == "ssh_mysql_exec"


# ---------------------------------------------------------------------------
# SSHExecTool tests
# ---------------------------------------------------------------------------

class TestSSHExecTool:
    async def test_arun_returns_correct_dict(self, mock_ssh_connection):
        tool = SSHExecTool()
        result = await tool._arun(host="test-host", command="uptime")

        assert isinstance(result, dict)
        assert "stdout" in result
        assert "stderr" in result
        assert "exit_code" in result
        assert result["stdout"] == "mock output"
        assert result["exit_code"] == 0

    async def test_arun_passes_ssh_params(self, mock_ssh_connection):
        mock_connect, mock_conn = mock_ssh_connection
        tool = SSHExecTool()

        await tool._arun(
            host="web-01",
            command="df -h",
            ssh_user="admin",
            ssh_key_path="/tmp/test_key",
            ssh_port=2222,
        )

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args
        # _ssh_run now passes all args as kwargs via **connect_kwargs
        positional_host = call_kwargs[0][0] if call_kwargs[0] else None
        kwarg_host = call_kwargs[1].get("host")
        assert positional_host == "web-01" or kwarg_host == "web-01"

    async def test_arun_handles_connection_error(self):
        with patch(
            "app.agent.ssh_tools.asyncssh.connect",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            tool = SSHExecTool()
            result = await tool._arun(host="unreachable", command="ls")

            assert result["exit_code"] == -1
            assert "error" in result
            assert "Connection refused" in result["error"]


# ---------------------------------------------------------------------------
# SSHReadFileTool tests
# ---------------------------------------------------------------------------

class TestSSHReadFileTool:
    async def test_arun_cat_full_file(self, mock_ssh_connection):
        _, mock_conn = mock_ssh_connection
        tool = SSHReadFileTool()
        result = await tool._arun(host="test-host", path="/var/log/syslog")

        assert "content" in result
        assert result["content"] == "mock output"
        # Verify cat was used
        mock_conn.run.assert_called_once()
        cmd_arg = mock_conn.run.call_args[0][0]
        assert cmd_arg == "cat /var/log/syslog"

    async def test_arun_tail_lines(self, mock_ssh_connection):
        _, mock_conn = mock_ssh_connection
        tool = SSHReadFileTool()
        result = await tool._arun(host="test-host", path="/var/log/syslog", tail_lines=50)

        assert "content" in result
        cmd_arg = mock_conn.run.call_args[0][0]
        assert cmd_arg == "tail -n 50 /var/log/syslog"


# ---------------------------------------------------------------------------
# SSHSystemctlStatusTool tests
# ---------------------------------------------------------------------------

class TestSSHSystemctlStatusTool:
    async def test_arun_returns_status(self, mock_ssh_connection):
        _, mock_conn = mock_ssh_connection
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_result.stderr = ""
        mock_result.exit_status = 0
        mock_conn.run = AsyncMock(return_value=mock_result)

        tool = SSHSystemctlStatusTool()
        result = await tool._arun(host="test-host", service="apache2")

        assert result["status"] == "active"
        assert result["exit_code"] == 0

    async def test_arun_inactive_service(self, mock_ssh_connection):
        _, mock_conn = mock_ssh_connection
        mock_result = MagicMock()
        mock_result.stdout = "inactive\n"
        mock_result.stderr = ""
        mock_result.exit_status = 3
        mock_conn.run = AsyncMock(return_value=mock_result)

        tool = SSHSystemctlStatusTool()
        result = await tool._arun(host="test-host", service="nginx")

        assert result["status"] == "inactive"


# ---------------------------------------------------------------------------
# SSHSystemctlRestartTool tests
# ---------------------------------------------------------------------------

class TestSSHSystemctlRestartTool:
    async def test_arun_sends_sudo_restart(self, mock_ssh_connection):
        _, mock_conn = mock_ssh_connection
        tool = SSHSystemctlRestartTool()
        result = await tool._arun(host="test-host", service="apache2")

        cmd_arg = mock_conn.run.call_args[0][0]
        assert cmd_arg == "sudo systemctl restart apache2"
        assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# SSHMysqlExecTool tests
# ---------------------------------------------------------------------------

class TestSSHMysqlExecTool:
    def test_build_mysql_command_regular_query(self):
        cmd = SSHMysqlExecTool._build_mysql_command("SELECT 1")
        assert cmd == 'mysql -B -N -e "SELECT 1"'

    def test_build_mysql_command_show_slave_status(self):
        cmd = SSHMysqlExecTool._build_mysql_command("SHOW SLAVE STATUS")
        assert "\\G" in cmd
        assert "-B" not in cmd
        assert "-N" not in cmd

    def test_build_mysql_command_show_slave_status_with_semicolon(self):
        cmd = SSHMysqlExecTool._build_mysql_command("SHOW SLAVE STATUS;")
        assert "\\G" in cmd

    def test_build_mysql_command_show_replica_status(self):
        cmd = SSHMysqlExecTool._build_mysql_command("SHOW REPLICA STATUS")
        assert "\\G" in cmd

    def test_build_mysql_command_show_status(self):
        # Regular SHOW STATUS should use batch mode
        cmd = SSHMysqlExecTool._build_mysql_command("SHOW STATUS")
        assert "-B" in cmd
        assert "-N" in cmd

    async def test_arun_returns_output(self, mock_ssh_connection):
        tool = SSHMysqlExecTool()
        result = await tool._arun(host="test-host", query="SHOW DATABASES")

        assert "output" in result
        assert result["output"] == "mock output"
        assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# tool_provider tests
# ---------------------------------------------------------------------------

class TestToolProvider:
    def test_get_read_tools_returns_four_tools(self):
        tools = get_read_tools()
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert names == {"ssh_exec", "ssh_read_file", "ssh_systemctl_status", "ssh_mysql_exec"}

    def test_get_write_tools_returns_five_tools(self):
        tools = get_write_tools()
        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "ssh_systemctl_restart" in names

    def test_get_write_tools_includes_all_read_tools(self):
        read_names = {t.name for t in get_read_tools()}
        write_names = {t.name for t in get_write_tools()}
        assert read_names.issubset(write_names)

    def test_get_read_tools_accepts_host_config(self):
        config = {"host": "web-01", "ssh_user": "deploy", "ssh_key_path": "~/.ssh/id_rsa", "ssh_port": 22}
        tools = get_read_tools(config)
        assert len(tools) == 4

    def test_get_write_tools_accepts_host_config(self):
        config = {"host": "web-01", "ssh_user": "deploy", "ssh_key_path": "~/.ssh/id_rsa", "ssh_port": 22}
        tools = get_write_tools(config)
        assert len(tools) == 5
