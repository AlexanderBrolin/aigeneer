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

    def __init__(self, host: str, config: dict, tools: list):
        self.host = host
        self.config = config
        self.tools = tools

    @abstractmethod
    async def run(self) -> list[Signal]:
        """Execute the check and return a list of signals."""
        ...

    def _get_tool(self, name: str):
        """Look up a tool by name from the tool list.

        Raises StopIteration if the tool is not found.
        """
        return next(t for t in self.tools if t.name == name)
