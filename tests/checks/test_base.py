"""Tests for base check infrastructure: Signal dataclass and Check ABC."""

import pytest

from app.checks.base import Check, Signal
from tests.checks.conftest import MockTool


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation_minimal(self):
        sig = Signal(
            host="web-01",
            severity="warning",
            problem_type="disk_full",
            evidence="/ is 85% full",
        )
        assert sig.host == "web-01"
        assert sig.severity == "warning"
        assert sig.problem_type == "disk_full"
        assert sig.evidence == "/ is 85% full"
        assert sig.raw_data == {}

    def test_signal_creation_with_raw_data(self):
        raw = {"pcent": 95, "mount": "/var"}
        sig = Signal(
            host="db-01",
            severity="critical",
            problem_type="disk_full",
            evidence="/var is 95% full",
            raw_data=raw,
        )
        assert sig.raw_data == raw

    def test_signal_severity_values(self):
        for sev in ("critical", "warning", "info"):
            sig = Signal(host="h", severity=sev, problem_type="test", evidence="e")
            assert sig.severity == sev

    def test_signal_raw_data_default_not_shared(self):
        """Each Signal gets its own default dict (no mutable default sharing)."""
        s1 = Signal(host="a", severity="info", problem_type="t", evidence="e")
        s2 = Signal(host="b", severity="info", problem_type="t", evidence="e")
        s1.raw_data["key"] = "value"
        assert "key" not in s2.raw_data


class TestCheckABC:
    """Tests for Check abstract base class."""

    def test_check_is_abstract(self):
        """Cannot instantiate Check directly."""
        with pytest.raises(TypeError):
            Check(host="h", config={}, tools=[])

    def test_concrete_check_can_be_instantiated(self):
        """A concrete subclass implementing run() can be created."""

        class MyCheck(Check):
            name = "my_check"

            async def run(self) -> list[Signal]:
                return []

        c = MyCheck(host="web-01", config={"key": "val"}, tools=[])
        assert c.host == "web-01"
        assert c.config == {"key": "val"}
        assert c.name == "my_check"

    def test_get_tool_finds_by_name(self):
        """_get_tool returns the tool matching the given name."""

        class MyCheck(Check):
            name = "my_check"

            async def run(self) -> list[Signal]:
                return []

        t1 = MockTool("ssh_exec", "ok")
        t2 = MockTool("ssh_systemctl_status", "active")
        c = MyCheck(host="h", config={}, tools=[t1, t2])
        assert c._get_tool("ssh_exec") is t1
        assert c._get_tool("ssh_systemctl_status") is t2

    def test_get_tool_raises_on_missing(self):
        """_get_tool raises StopIteration when tool is not found."""

        class MyCheck(Check):
            name = "my_check"

            async def run(self) -> list[Signal]:
                return []

        c = MyCheck(host="h", config={}, tools=[])
        with pytest.raises(StopIteration):
            c._get_tool("nonexistent")
