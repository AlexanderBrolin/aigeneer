"""Base classes for the runbook system."""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class RunbookResult:
    """Result of a runbook execution."""

    success: bool
    message: str
    details: str = ""


class Runbook(ABC):
    """Abstract base class for all runbooks.

    Runbooks are deterministic scripts that execute specific actions
    on remote servers via MCP/SSH tools. They are NOT LLM-driven.
    """

    name: str
    is_dangerous: bool = False

    def __init__(self, tools: list):
        self.tools = tools

    @abstractmethod
    async def execute(self, params: dict) -> RunbookResult:
        """Execute the runbook with the given parameters.

        Args:
            params: Dictionary of parameters specific to each runbook.

        Returns:
            RunbookResult with success/failure status and details.
        """
        ...

    def _get_tool(self, name: str):
        """Find a tool by name from the available tools list."""
        return next(t for t in self.tools if t.name == name)
