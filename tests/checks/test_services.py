"""Tests for SystemdServiceCheck."""

import pytest

from app.checks.base import Signal
from app.checks.services import SystemdServiceCheck
from tests.checks.conftest import DynamicMockTool, MockTool

STATUS_ACTIVE = """\
● apache2.service - The Apache HTTP Server
     Loaded: loaded (/lib/systemd/system/apache2.service; enabled)
     Active: active (running) since Mon 2026-03-31 10:00:00 UTC; 2 days ago
   Main PID: 1234 (apache2)
"""

STATUS_INACTIVE = """\
● mariadb.service - MariaDB 10.11 database server
     Loaded: loaded (/lib/systemd/system/mariadb.service; enabled)
     Active: inactive (dead) since Tue 2026-04-01 08:00:00 UTC; 1h ago
"""

STATUS_FAILED = """\
● apache2.service - The Apache HTTP Server
     Loaded: loaded (/lib/systemd/system/apache2.service; enabled)
     Active: failed (Result: exit-code) since Tue 2026-04-01 09:30:00 UTC; 15min ago
   Main PID: 1234 (code=exited, status=1/FAILURE)
"""


class TestSystemdServiceCheck:
    """Tests for SystemdServiceCheck."""

    def _make_check(self, status_tool, config: dict | None = None) -> SystemdServiceCheck:
        cfg = config or {"services": ["apache2", "mariadb"]}
        return SystemdServiceCheck(host="web-01", config=cfg, tools=[status_tool])

    async def test_no_signals_when_all_active(self):
        tool = MockTool("ssh_systemctl_status", STATUS_ACTIVE)
        check = self._make_check(tool)
        signals = await check.run()
        assert signals == []

    async def test_inactive_service_produces_warning(self):
        tool = DynamicMockTool(
            "ssh_systemctl_status",
            responses={
                "apache2": STATUS_ACTIVE,
                "mariadb": STATUS_INACTIVE,
            },
        )
        check = self._make_check(tool)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "warning"
        assert sig.problem_type == "service_down"
        assert "mariadb" in sig.evidence

    async def test_failed_service_produces_critical(self):
        tool = DynamicMockTool(
            "ssh_systemctl_status",
            responses={
                "apache2": STATUS_FAILED,
                "mariadb": STATUS_ACTIVE,
            },
        )
        check = self._make_check(tool)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "critical"
        assert sig.problem_type == "service_down"
        assert "apache2" in sig.evidence

    async def test_multiple_failed_services(self):
        tool = DynamicMockTool(
            "ssh_systemctl_status",
            responses={
                "apache2": STATUS_FAILED,
                "mariadb": STATUS_INACTIVE,
            },
        )
        check = self._make_check(tool)
        signals = await check.run()
        assert len(signals) == 2

    async def test_host_is_set_on_signals(self):
        tool = MockTool("ssh_systemctl_status", STATUS_FAILED)
        check = self._make_check(tool, config={"services": ["apache2"]})
        signals = await check.run()
        assert signals[0].host == "web-01"

    async def test_check_name(self):
        tool = MockTool("ssh_systemctl_status", STATUS_ACTIVE)
        check = self._make_check(tool)
        assert check.name == "systemd_services"

    async def test_raw_data_contains_service_and_state(self):
        tool = MockTool("ssh_systemctl_status", STATUS_INACTIVE)
        check = self._make_check(tool, config={"services": ["mariadb"]})
        signals = await check.run()
        assert signals[0].raw_data["service"] == "mariadb"
        assert signals[0].raw_data["state"] == "inactive"
