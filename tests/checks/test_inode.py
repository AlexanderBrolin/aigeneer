"""Tests for DiskInodeCheck."""

import pytest

from app.checks.base import Signal
from app.checks.inode import DiskInodeCheck
from tests.checks.conftest import MockTool

# df -i --output=source,ipcent,target output
DF_INODE_NORMAL = """\
Filesystem     IUse% Mounted on
/dev/sda1        40% /
/dev/sda2        55% /var
tmpfs             1% /run
"""

DF_INODE_WARNING = """\
Filesystem     IUse% Mounted on
/dev/sda1        87% /
/dev/sda2        55% /var
"""

DF_INODE_CRITICAL = """\
Filesystem     IUse% Mounted on
/dev/sda1        96% /
/dev/sda2        93% /var
"""

DF_INODE_MIXED = """\
Filesystem     IUse% Mounted on
/dev/sda1        50% /
/dev/sda2        88% /var
/dev/sda3        97% /data
"""


class TestDiskInodeCheck:
    """Tests for DiskInodeCheck."""

    def _make_check(self, df_output: str, config: dict | None = None) -> DiskInodeCheck:
        cfg = config or {"threshold_warning": 85, "threshold_critical": 95, "paths": ["/", "/var"]}
        tool = MockTool("ssh_exec", df_output)
        return DiskInodeCheck(host="web-01", config=cfg, tools=[tool])

    async def test_no_signals_when_all_normal(self):
        check = self._make_check(DF_INODE_NORMAL)
        signals = await check.run()
        assert signals == []

    async def test_warning_signal(self):
        check = self._make_check(DF_INODE_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "warning"
        assert sig.host == "web-01"
        assert sig.problem_type == "inode_exhaustion"
        assert "87%" in sig.evidence
        assert "/" in sig.evidence

    async def test_critical_signal(self):
        check = self._make_check(DF_INODE_CRITICAL)
        signals = await check.run()
        # / at 96% → critical; /var at 93% → warning (below critical threshold of 95)
        critical = [s for s in signals if s.severity == "critical"]
        warning = [s for s in signals if s.severity == "warning"]
        assert len(critical) == 1
        assert critical[0].raw_data["mount"] == "/"
        assert len(warning) == 1
        assert warning[0].raw_data["mount"] == "/var"

    async def test_mixed_thresholds(self):
        check = self._make_check(
            DF_INODE_MIXED,
            config={
                "threshold_warning": 85,
                "threshold_critical": 95,
                "paths": ["/", "/var", "/data"],
            },
        )
        signals = await check.run()
        severities = {s.raw_data.get("mount"): s.severity for s in signals}
        assert "/" not in severities       # 50% — no signal
        assert severities.get("/var") == "warning"   # 88%
        assert severities.get("/data") == "critical"  # 97%

    async def test_filters_only_configured_paths(self):
        check = self._make_check(
            DF_INODE_CRITICAL,
            config={"threshold_warning": 85, "threshold_critical": 95, "paths": ["/var"]},
        )
        signals = await check.run()
        mounts = [s.raw_data.get("mount") for s in signals]
        assert "/" not in mounts
        assert "/var" in mounts

    async def test_default_config_values(self):
        """Check uses defaults when config keys are missing."""
        tool = MockTool("ssh_exec", DF_INODE_WARNING)
        check = DiskInodeCheck(host="web-01", config={}, tools=[tool])
        signals = await check.run()
        # / at 87% > default warning of 85
        assert len(signals) >= 1

    async def test_check_name(self):
        check = self._make_check(DF_INODE_NORMAL)
        assert check.name == "disk_inode"

    async def test_raw_data_contains_ipcent_and_mount(self):
        check = self._make_check(DF_INODE_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        rd = signals[0].raw_data
        assert rd["ipcent"] == 87
        assert rd["mount"] == "/"
