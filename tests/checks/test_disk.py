"""Tests for DiskSpaceCheck."""

import pytest

from app.checks.base import Signal
from app.checks.disk import DiskSpaceCheck
from tests.checks.conftest import MockTool

# Realistic df output
DF_OUTPUT_NORMAL = """\
Filesystem     Use% Mounted on
/dev/sda1       45% /
/dev/sda2       60% /var
tmpfs            1% /run
"""

DF_OUTPUT_WARNING = """\
Filesystem     Use% Mounted on
/dev/sda1       85% /
/dev/sda2       60% /var
"""

DF_OUTPUT_CRITICAL = """\
Filesystem     Use% Mounted on
/dev/sda1       95% /
/dev/sda2       92% /var
"""

DF_OUTPUT_MIXED = """\
Filesystem     Use% Mounted on
/dev/sda1       50% /
/dev/sda2       88% /var
/dev/sda3       96% /data
"""


class TestDiskSpaceCheck:
    """Tests for DiskSpaceCheck."""

    def _make_check(self, df_output: str, config: dict | None = None) -> DiskSpaceCheck:
        cfg = config or {"threshold_warning": 80, "threshold_critical": 90, "paths": ["/", "/var"]}
        tool = MockTool("ssh_exec", df_output)
        return DiskSpaceCheck(host="web-01", config=cfg, tools=[tool])

    async def test_no_signals_when_all_normal(self):
        check = self._make_check(DF_OUTPUT_NORMAL)
        signals = await check.run()
        assert signals == []

    async def test_warning_signal(self):
        check = self._make_check(DF_OUTPUT_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "warning"
        assert sig.host == "web-01"
        assert sig.problem_type == "disk_full"
        assert "85%" in sig.evidence
        assert "/" in sig.evidence

    async def test_critical_signal(self):
        check = self._make_check(DF_OUTPUT_CRITICAL)
        signals = await check.run()
        # Both / and /var are above critical
        critical = [s for s in signals if s.severity == "critical"]
        assert len(critical) == 2

    async def test_mixed_thresholds(self):
        check = self._make_check(
            DF_OUTPUT_MIXED,
            config={
                "threshold_warning": 80,
                "threshold_critical": 90,
                "paths": ["/", "/var", "/data"],
            },
        )
        signals = await check.run()
        severities = {s.raw_data.get("mount"): s.severity for s in signals}
        assert "/" not in severities  # 50% — no signal
        assert severities.get("/var") == "warning"  # 88%
        assert severities.get("/data") == "critical"  # 96%

    async def test_default_config_values(self):
        """Check uses defaults when config keys are missing."""
        tool = MockTool("ssh_exec", DF_OUTPUT_WARNING)
        check = DiskSpaceCheck(host="web-01", config={}, tools=[tool])
        signals = await check.run()
        # With default paths=["/"], and / at 85% > default warning 80
        assert len(signals) >= 1

    async def test_filters_only_configured_paths(self):
        """Only configured paths are checked."""
        check = self._make_check(
            DF_OUTPUT_CRITICAL,
            config={"threshold_warning": 80, "threshold_critical": 90, "paths": ["/var"]},
        )
        signals = await check.run()
        mounts = [s.raw_data.get("mount") for s in signals]
        assert "/" not in mounts
        assert "/var" in mounts

    async def test_check_name(self):
        check = self._make_check(DF_OUTPUT_NORMAL)
        assert check.name == "disk_space"

    async def test_signal_raw_data_contains_percent(self):
        check = self._make_check(DF_OUTPUT_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        assert signals[0].raw_data["pcent"] == 85
