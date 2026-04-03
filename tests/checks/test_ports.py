"""Tests for OpenPortsCheck."""

from app.checks.ports import OpenPortsCheck
from tests.checks.conftest import MockTool

# Realistic ss -tlnp output
SS_ONLY_EXPECTED = """\
State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*     users:(("sshd",pid=123,fd=3))
LISTEN 0      128          0.0.0.0:80         0.0.0.0:*     users:(("apache2",pid=456,fd=4))
LISTEN 0      128          0.0.0.0:443        0.0.0.0:*     users:(("apache2",pid=456,fd=5))
"""

SS_EXTRA_PORT = """\
State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*     users:(("sshd",pid=123,fd=3))
LISTEN 0      128          0.0.0.0:80         0.0.0.0:*     users:(("apache2",pid=456,fd=4))
LISTEN 0      128          0.0.0.0:443        0.0.0.0:*     users:(("apache2",pid=456,fd=5))
LISTEN 0      128          0.0.0.0:9090       0.0.0.0:*     users:(("mystery",pid=789,fd=6))
"""


def _make_check(ss_output: str, expected_ports: list[int] | None = None) -> OpenPortsCheck:
    cfg = {"expected_ports": expected_ports if expected_ports is not None else [22, 80, 443]}
    tool = MockTool("ssh_exec", ss_output)
    return OpenPortsCheck(host="web-01", config=cfg, tools=[tool])


class TestOpenPortsCheck:
    """Tests for OpenPortsCheck."""

    async def test_only_expected_ports_no_signal(self):
        """All open ports are in the expected list → no signal."""
        check = _make_check(SS_ONLY_EXPECTED)
        signals = await check.run()
        assert signals == []

    async def test_extra_port_info_signal(self):
        """Unexpected port 9090 → 1 info signal."""
        check = _make_check(SS_EXTRA_PORT)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "info"
        assert sig.problem_type == "unexpected_port"
        assert sig.host == "web-01"

    async def test_unexpected_port_in_evidence(self):
        """Port number should appear in the signal evidence."""
        check = _make_check(SS_EXTRA_PORT)
        signals = await check.run()
        assert len(signals) == 1
        assert "9090" in signals[0].evidence

    async def test_check_name(self):
        check = _make_check(SS_ONLY_EXPECTED)
        assert check.name == "open_ports"

    async def test_multiple_unexpected_ports(self):
        """Multiple unexpected ports → one signal per unexpected port."""
        ss_output = SS_ONLY_EXPECTED + (
            "LISTEN 0      128          0.0.0.0:8080       0.0.0.0:*\n"
            "LISTEN 0      128          0.0.0.0:9090       0.0.0.0:*\n"
        )
        check = _make_check(ss_output)
        signals = await check.run()
        assert len(signals) == 2
        ports = {int(s.raw_data["port"]) for s in signals}
        assert ports == {8080, 9090}
