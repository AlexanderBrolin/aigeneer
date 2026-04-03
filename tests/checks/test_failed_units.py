"""Tests for FailedUnitsCheck."""

from app.checks.failed_units import FailedUnitsCheck
from tests.checks.conftest import MockTool


def _make_check(systemctl_output: str) -> FailedUnitsCheck:
    tool = MockTool("ssh_exec", systemctl_output)
    return FailedUnitsCheck(host="web-01", config={}, tools=[tool])


class TestFailedUnitsCheck:
    """Tests for FailedUnitsCheck."""

    async def test_empty_output_no_signals(self):
        """No failed units → no signals."""
        check = _make_check("")
        signals = await check.run()
        assert signals == []

    async def test_two_failed_lines_two_warning_signals(self):
        """Two failed units → 2 warning signals with correct problem_type."""
        output = (
            "nginx.service   failed  failed  A high performance web server\n"
            "myapp.service   failed  failed  My application service\n"
        )
        check = _make_check(output)
        signals = await check.run()
        assert len(signals) == 2
        for sig in signals:
            assert sig.severity == "warning"
            assert sig.problem_type == "systemd_unit_failed"
            assert sig.host == "web-01"

    async def test_unit_names_in_evidence(self):
        """Unit names should appear in signal evidence."""
        output = "nginx.service   failed  failed  A high performance web server\n"
        check = _make_check(output)
        signals = await check.run()
        assert len(signals) == 1
        assert "nginx.service" in signals[0].evidence

    async def test_check_name(self):
        check = _make_check("")
        assert check.name == "systemd_failed"

    async def test_blank_lines_skipped(self):
        """Blank lines in output should produce no signals."""
        output = "\n\n\n"
        check = _make_check(output)
        signals = await check.run()
        assert signals == []
