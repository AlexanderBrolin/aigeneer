"""Base classes for the check system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Signal:
    """A raw signal produced by a check.

    Signals are the output of check functions. They are later normalized
    into Incident cards by the analysis graph.
    """

    host: str
    severity: Literal["critical", "warning", "info"]
    problem_type: str
    evidence: str
    raw_data: dict = field(default_factory=dict)


class Check(ABC):
    """Abstract base class for all infrastructure checks.

    Each check knows how to collect signals from a host using the
    provided MCP tools.
    """

    name: str

    def __init__(self, host: str, config: dict, tools: list, use_sudo: bool = False):
        self.host = host
        self.config = config
        self.tools = tools
        self.use_sudo = use_sudo

    def _sudo(self, command: str) -> str:
        """Prefix command with sudo when SSH user is not root."""
        return f"sudo {command}" if self.use_sudo else command

    @abstractmethod
    async def run(self) -> list[Signal]:
        """Execute the check and return a list of signals."""
        ...

    async def _exec(self, command: str) -> str:
        """Execute a command via ssh_exec and return stdout.

        Handles both dict responses (from tool_provider tools) and
        plain string responses (from test mocks).
        """
        ssh = self._get_tool("ssh_exec")
        result = await ssh.ainvoke({"command": command})
        if isinstance(result, dict):
            return result.get("stdout", "")
        return result

    async def _exec_status(self, service: str) -> str:
        """Get systemd service status, return the state string."""
        tool = self._get_tool("ssh_systemctl_status")
        result = await tool.ainvoke({"service": service})
        if isinstance(result, dict):
            return result.get("stdout", "").strip()
        return result.strip()

    def _get_tool(self, name: str):
        """Look up a tool by name from the tool list.

        Raises StopIteration if the tool is not found.
        """
        return next(t for t in self.tools if t.name == name)
