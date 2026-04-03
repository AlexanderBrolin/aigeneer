"""Tests for ZombieProcessCheck."""

from app.checks.zombies import ZombieProcessCheck
from tests.checks.conftest import MockTool


def _zombie_lines(count: int) -> str:
    """Generate realistic ps aux zombie output lines."""
    line = "root      1234  0.0  0.0      0     0 ?        Z    10:00   0:00 [defunct]"
    return "\n".join([line] * count) + ("\n" if count > 0 else "")


def _make_check(ps_output: str, threshold: int = 5) -> ZombieProcessCheck:
    tool = MockTool("ssh_exec", ps_output)
    return ZombieProcessCheck(host="web-01", config={"threshold": threshold}, tools=[tool])


class TestZombieProcessCheck:
    """Tests for ZombieProcessCheck."""

    async def test_empty_no_signals(self):
        """No zombie processes → no signals."""
        check = _make_check("")
        signals = await check.run()
        assert signals == []

    async def test_count_exceeds_threshold_warning(self):
        """6 zombie lines with threshold 5 → 1 warning signal."""
        check = _make_check(_zombie_lines(6), threshold=5)
        signals = await check.run()
        assert len(signals) == 1
        assert signals[0].severity == "warning"
        assert signals[0].host == "web-01"

    async def test_count_below_threshold_no_signal(self):
        """6 zombie lines with threshold 10 → no signal."""
        check = _make_check(_zombie_lines(6), threshold=10)
        signals = await check.run()
        assert signals == []

    async def test_check_name(self):
        check = _make_check("")
        assert check.name == "zombie_processes"

    async def test_zombie_count_in_evidence(self):
        """Signal evidence should mention zombie count."""
        check = _make_check(_zombie_lines(6), threshold=5)
        signals = await check.run()
        assert len(signals) == 1
        assert "6" in signals[0].evidence

    async def test_default_threshold_applied(self):
        """Without config, default threshold of 5 is applied."""
        tool = MockTool("ssh_exec", _zombie_lines(6))
        check = ZombieProcessCheck(host="web-01", config={}, tools=[tool])
        signals = await check.run()
        assert len(signals) == 1

    async def test_exactly_at_threshold_no_signal(self):
        """Count equal to threshold should NOT trigger (only strictly greater)."""
        check = _make_check(_zombie_lines(5), threshold=5)
        signals = await check.run()
        assert signals == []
