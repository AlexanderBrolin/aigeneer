"""Factory functions that return pre-configured tool sets for a given host.

Tools are *bound* to a specific host/SSH config so callers (checks, runbooks)
don't need to pass host/user/key on every invocation.  Each tool returns
plain stdout string — straightforward for checks and runbooks.
"""

from __future__ import annotations

import os

from langchain_core.tools import tool

from app.agent.ssh_tools import _ssh_run, SSHMysqlExecTool
from app.config import settings


def get_read_tools(host_config: dict) -> list:
    """Return read-only SSH tools pre-bound to the given host.

    Parameters
    ----------
    host_config : dict
        Keys: host, ssh_user, ssh_key_path, ssh_port
    """
    host = host_config["host"]
    ssh_user = host_config.get("ssh_user") or settings.ssh_default_user
    raw_key = host_config.get("ssh_key_path") or settings.ssh_default_key_path
    ssh_key_path = os.path.expanduser(raw_key)
    ssh_port = int(host_config.get("ssh_port") or 22)

    @tool
    async def ssh_exec(command: str) -> str:
        """Execute a shell command on the remote host via SSH. Returns stdout."""
        result = await _ssh_run(host, command, ssh_user, ssh_key_path, ssh_port)
        return result["stdout"]

    @tool
    async def ssh_read_file(path: str, tail_lines: int = 0) -> str:
        """Read a file from the remote host via SSH.
        Set tail_lines > 0 to read only the last N lines."""
        cmd = f"tail -n {tail_lines} {path}" if tail_lines else f"cat {path}"
        result = await _ssh_run(host, cmd, ssh_user, ssh_key_path, ssh_port)
        return result["stdout"]

    @tool
    async def ssh_systemctl_status(service: str) -> str:
        """Get the active state of a systemd service (active/inactive/failed)."""
        result = await _ssh_run(
            host, f"systemctl is-active {service}", ssh_user, ssh_key_path, ssh_port
        )
        return result["stdout"].strip()

    @tool
    async def ssh_mysql_exec(query: str) -> str:
        """Execute a MySQL query on the remote host via SSH. Returns tab-separated output."""
        cmd = SSHMysqlExecTool._build_mysql_command(query)
        result = await _ssh_run(host, cmd, ssh_user, ssh_key_path, ssh_port)
        return result["stdout"]

    return [ssh_exec, ssh_read_file, ssh_systemctl_status, ssh_mysql_exec]


def get_write_tools(host_config: dict) -> list:
    """Return all tools including write (destructive) operations."""
    host = host_config["host"]
    ssh_user = host_config.get("ssh_user") or settings.ssh_default_user
    raw_key = host_config.get("ssh_key_path") or settings.ssh_default_key_path
    ssh_key_path = os.path.expanduser(raw_key)
    ssh_port = int(host_config.get("ssh_port") or 22)

    read_tools = get_read_tools(host_config)

    @tool
    async def ssh_systemctl_restart(service: str) -> str:
        """Restart a systemd service on the remote host via sudo. WRITE operation."""
        result = await _ssh_run(
            host, f"sudo systemctl restart {service}", ssh_user, ssh_key_path, ssh_port
        )
        return result["stdout"] or result["stderr"]

    return read_tools + [ssh_systemctl_restart]
