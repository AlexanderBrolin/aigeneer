"""Factory functions that return pre-configured tool sets for a given host."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.ssh_tools import (
    SSHExecTool,
    SSHMysqlExecTool,
    SSHReadFileTool,
    SSHSystemctlRestartTool,
    SSHSystemctlStatusTool,
)


def get_read_tools(host_config: dict | None = None) -> list[BaseTool]:
    """Return read-only SSH tools.

    Parameters
    ----------
    host_config : dict, optional
        Ignored for now (tools receive host params at call time),
        but kept for future pre-binding.

    Returns
    -------
    list[BaseTool]
        [SSHExecTool, SSHReadFileTool, SSHSystemctlStatusTool, SSHMysqlExecTool]
    """
    return [
        SSHExecTool(),
        SSHReadFileTool(),
        SSHSystemctlStatusTool(),
        SSHMysqlExecTool(),
    ]


def get_write_tools(host_config: dict | None = None) -> list[BaseTool]:
    """Return all tools including write (destructive) operations.

    Parameters
    ----------
    host_config : dict, optional
        Ignored for now; kept for forward compatibility.

    Returns
    -------
    list[BaseTool]
        read_tools + [SSHSystemctlRestartTool]
    """
    return get_read_tools(host_config) + [
        SSHSystemctlRestartTool(),
    ]
