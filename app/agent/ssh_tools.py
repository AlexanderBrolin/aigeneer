"""SSH-based LangChain tools for remote server management.

Each tool accepts host/ssh_user/ssh_key_path/ssh_port as input arguments
so a single tool instance can operate on any host.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional

import asyncssh
import structlog
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Shared SSH helper
# ---------------------------------------------------------------------------

async def _ssh_run(
    host: str,
    command: str,
    ssh_user: str = "deploy",
    ssh_key_path: str | None = None,
    ssh_key_content: str | None = None,
    ssh_port: int = 22,
) -> dict[str, Any]:
    """Execute a command on a remote host via asyncssh and return structured result.

    Authentication priority:
    1. ``ssh_key_content`` — raw PEM key string (decrypted from DB)
    2. ``ssh_key_path``    — path to a key file on disk
    If neither is provided, asyncssh will try the SSH agent / default keys.
    """
    try:
        connect_kwargs: dict[str, Any] = {
            "host": host,
            "port": ssh_port,
            "username": ssh_user,
            "known_hosts": None,
        }

        client_keys: list[Any] = []
        if ssh_key_content:
            client_keys.append(asyncssh.import_private_key(ssh_key_content))
        if ssh_key_path:
            client_keys.append(os.path.expanduser(ssh_key_path))
        if client_keys:
            # Provided keys first; also keep default key discovery
            # so ~/.ssh/ keys still work as fallback
            connect_kwargs["client_keys"] = client_keys
            connect_kwargs["agent_path"] = None  # no agent, but keep default keys below
        # NOTE: when client_keys is set, asyncssh skips ~/.ssh/ auto-discovery.
        # Re-add default paths so mounted keys still work as fallback.
        if client_keys:
            for default_key in ("~/.ssh/id_rsa", "~/.ssh/id_ed25519", "~/.ssh/id_ecdsa"):
                expanded = os.path.expanduser(default_key)
                if os.path.isfile(expanded) and expanded not in [str(k) for k in client_keys]:
                    client_keys.append(expanded)

        async with asyncssh.connect(**connect_kwargs) as conn:
            result = await conn.run(command)
            return {
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "exit_code": result.exit_status,
            }
    except Exception as exc:
        logger.error("ssh_run_failed", host=host, command=command, error=str(exc))
        return {
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class SSHExecInput(BaseModel):
    host: str = Field(description="Target hostname or IP")
    command: str = Field(description="Shell command to execute")
    ssh_user: str = Field(default="deploy", description="SSH user")
    ssh_key_path: str = Field(default="~/.ssh/id_rsa", description="Path to SSH private key")
    ssh_port: int = Field(default=22, description="SSH port")


class SSHReadFileInput(BaseModel):
    host: str = Field(description="Target hostname or IP")
    path: str = Field(description="Absolute path to file on remote host")
    tail_lines: Optional[int] = Field(default=None, description="Read only last N lines (uses tail)")
    ssh_user: str = Field(default="deploy", description="SSH user")
    ssh_key_path: str = Field(default="~/.ssh/id_rsa", description="Path to SSH private key")
    ssh_port: int = Field(default=22, description="SSH port")


class SSHSystemctlInput(BaseModel):
    host: str = Field(description="Target hostname or IP")
    service: str = Field(description="Systemd service name")
    ssh_user: str = Field(default="deploy", description="SSH user")
    ssh_key_path: str = Field(default="~/.ssh/id_rsa", description="Path to SSH private key")
    ssh_port: int = Field(default=22, description="SSH port")


class SSHMysqlExecInput(BaseModel):
    host: str = Field(description="Target hostname or IP")
    query: str = Field(description="MySQL query to execute")
    ssh_user: str = Field(default="deploy", description="SSH user")
    ssh_key_path: str = Field(default="~/.ssh/id_rsa", description="Path to SSH private key")
    ssh_port: int = Field(default=22, description="SSH port")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class SSHExecTool(BaseTool):
    """Execute an arbitrary command on a remote host via SSH."""

    name: str = "ssh_exec"
    description: str = (
        "Execute a shell command on a remote host via SSH. "
        "Returns stdout, stderr, and exit_code."
    )
    args_schema: type[BaseModel] = SSHExecInput

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        return asyncio.get_event_loop().run_until_complete(self._arun(**kwargs))

    async def _arun(
        self,
        host: str,
        command: str,
        ssh_user: str = "deploy",
        ssh_key_path: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
    ) -> dict[str, Any]:
        return await _ssh_run(host, command, ssh_user, ssh_key_path=ssh_key_path, ssh_port=ssh_port)


class SSHReadFileTool(BaseTool):
    """Read a file from a remote host via SSH."""

    name: str = "ssh_read_file"
    description: str = (
        "Read file content from a remote host via SSH. "
        "Optionally read only the last N lines with tail_lines."
    )
    args_schema: type[BaseModel] = SSHReadFileInput

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        return asyncio.get_event_loop().run_until_complete(self._arun(**kwargs))

    async def _arun(
        self,
        host: str,
        path: str,
        tail_lines: Optional[int] = None,
        ssh_user: str = "deploy",
        ssh_key_path: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
    ) -> dict[str, Any]:
        if tail_lines is not None:
            cmd = f"tail -n {tail_lines} {path}"
        else:
            cmd = f"cat {path}"

        result = await _ssh_run(host, cmd, ssh_user, ssh_key_path=ssh_key_path, ssh_port=ssh_port)
        return {"content": result["stdout"], **{k: v for k, v in result.items() if k != "stdout"}}


class SSHSystemctlStatusTool(BaseTool):
    """Get the status of a systemd service on a remote host."""

    name: str = "ssh_systemctl_status"
    description: str = (
        "Get the active/inactive/failed status of a systemd service via SSH."
    )
    args_schema: type[BaseModel] = SSHSystemctlInput

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        return asyncio.get_event_loop().run_until_complete(self._arun(**kwargs))

    async def _arun(
        self,
        host: str,
        service: str,
        ssh_user: str = "deploy",
        ssh_key_path: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
    ) -> dict[str, Any]:
        result = await _ssh_run(host, f"systemctl is-active {service}", ssh_user, ssh_key_path=ssh_key_path, ssh_port=ssh_port)
        status_text = result["stdout"].strip()
        return {
            "status": status_text,
            "output": result["stdout"],
            "stderr": result["stderr"],
            "exit_code": result["exit_code"],
        }


class SSHSystemctlRestartTool(BaseTool):
    """Restart a systemd service on a remote host (requires sudo)."""

    name: str = "ssh_systemctl_restart"
    description: str = (
        "Restart a systemd service on a remote host via sudo. "
        "This is a WRITE operation -- use with confirmation."
    )
    args_schema: type[BaseModel] = SSHSystemctlInput

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        return asyncio.get_event_loop().run_until_complete(self._arun(**kwargs))

    async def _arun(
        self,
        host: str,
        service: str,
        ssh_user: str = "deploy",
        ssh_key_path: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
    ) -> dict[str, Any]:
        return await _ssh_run(host, f"sudo systemctl restart {service}", ssh_user, ssh_key_path=ssh_key_path, ssh_port=ssh_port)


class SSHMysqlExecTool(BaseTool):
    """Execute a MySQL query on a remote host via SSH."""

    name: str = "ssh_mysql_exec"
    description: str = (
        "Execute a MySQL query on a remote host via SSH. "
        "Uses mysql CLI with -B -N flags for batch output. "
        "For SHOW SLAVE STATUS, uses \\G format automatically."
    )
    args_schema: type[BaseModel] = SSHMysqlExecInput

    def _run(self, **kwargs: Any) -> dict[str, Any]:
        return asyncio.get_event_loop().run_until_complete(self._arun(**kwargs))

    async def _arun(
        self,
        host: str,
        query: str,
        ssh_user: str = "deploy",
        ssh_key_path: str = "~/.ssh/id_rsa",
        ssh_port: int = 22,
    ) -> dict[str, Any]:
        cmd = self._build_mysql_command(query)
        result = await _ssh_run(host, cmd, ssh_user, ssh_key_path=ssh_key_path, ssh_port=ssh_port)
        return {"output": result["stdout"], "stderr": result["stderr"], "exit_code": result["exit_code"]}

    @staticmethod
    def _build_mysql_command(query: str) -> str:
        """Build the mysql CLI command string for the given query."""
        normalized = query.strip().upper()
        if normalized.startswith("SHOW SLAVE STATUS") or normalized.startswith("SHOW REPLICA STATUS"):
            # Use vertical format (\G) for slave/replica status
            clean_query = query.rstrip(";").rstrip("\\G")
            return f'mysql -e "{clean_query}\\G"'
        else:
            # Batch mode, no column names, tab-separated
            escaped_query = query.replace('"', '\\"')
            return f'mysql -B -N -e "{escaped_query}"'
