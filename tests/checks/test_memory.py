"""Tests for MemoryUsageCheck."""

import pytest

from app.checks.base import Signal
from app.checks.memory import MemoryUsageCheck
from tests.checks.conftest import MockTool

# /proc/meminfo output — normal usage (~45%), no swap used
MEMINFO_NORMAL = """\
MemTotal:       16384000 kB
MemFree:         1000000 kB
MemAvailable:    9000000 kB
Buffers:          500000 kB
Cached:          4000000 kB
SwapCached:            0 kB
SwapTotal:       8192000 kB
SwapFree:        8192000 kB
"""

# High RAM usage (~88%), no swap
MEMINFO_WARNING = """\
MemTotal:       16384000 kB
MemFree:          200000 kB
MemAvailable:    2000000 kB
Buffers:          100000 kB
Cached:           500000 kB
SwapCached:            0 kB
SwapTotal:       8192000 kB
SwapFree:        8192000 kB
"""

# Critical RAM usage (~97%), no swap
MEMINFO_CRITICAL = """\
MemTotal:       16384000 kB
MemFree:           50000 kB
MemAvailable:     500000 kB
Buffers:           50000 kB
Cached:           200000 kB
SwapCached:            0 kB
SwapTotal:       8192000 kB
SwapFree:        8192000 kB
"""

# Normal RAM, but high swap (85%)
MEMINFO_SWAP_WARNING = """\
MemTotal:       16384000 kB
MemFree:         5000000 kB
MemAvailable:    9000000 kB
Buffers:          300000 kB
Cached:          2000000 kB
SwapCached:       100000 kB
SwapTotal:       8192000 kB
SwapFree:        1228800 kB
"""

# No swap configured
MEMINFO_NO_SWAP = """\
MemTotal:       16384000 kB
MemFree:         5000000 kB
MemAvailable:    9000000 kB
Buffers:          300000 kB
Cached:          2000000 kB
SwapCached:            0 kB
SwapTotal:             0 kB
SwapFree:              0 kB
"""


class TestMemoryUsageCheck:
    """Tests for MemoryUsageCheck."""

    def _make_check(self, meminfo: str, config: dict | None = None) -> MemoryUsageCheck:
        cfg = config or {"threshold_warning": 85, "threshold_critical": 95}
        tool = MockTool("ssh_exec", meminfo)
        return MemoryUsageCheck(host="web-01", config=cfg, tools=[tool])

    async def test_no_signals_when_normal(self):
        check = self._make_check(MEMINFO_NORMAL)
        signals = await check.run()
        assert signals == []

    async def test_warning_signal_high_ram(self):
        check = self._make_check(MEMINFO_WARNING)
        signals = await check.run()
        ram_signals = [s for s in signals if s.problem_type == "high_memory"]
        assert len(ram_signals) == 1
        sig = ram_signals[0]
        assert sig.severity == "warning"
        assert sig.host == "web-01"
        assert "%" in sig.evidence

    async def test_critical_signal_high_ram(self):
        check = self._make_check(MEMINFO_CRITICAL)
        signals = await check.run()
        ram_signals = [s for s in signals if s.problem_type == "high_memory"]
        assert len(ram_signals) == 1
        assert ram_signals[0].severity == "critical"

    async def test_swap_warning(self):
        check = self._make_check(MEMINFO_SWAP_WARNING)
        signals = await check.run()
        swap_signals = [s for s in signals if s.problem_type == "high_swap"]
        assert len(swap_signals) == 1
        assert swap_signals[0].severity == "warning"

    async def test_no_swap_signal_when_no_swap_configured(self):
        """No swap signal if SwapTotal == 0."""
        check = self._make_check(MEMINFO_NO_SWAP)
        signals = await check.run()
        swap_signals = [s for s in signals if s.problem_type == "high_swap"]
        assert swap_signals == []

    async def test_raw_data_contains_usage_pct(self):
        check = self._make_check(MEMINFO_WARNING)
        signals = await check.run()
        ram_signals = [s for s in signals if s.problem_type == "high_memory"]
        assert len(ram_signals) == 1
        assert "usage_pct" in ram_signals[0].raw_data

    async def test_default_config_values(self):
        """Check uses defaults when config keys are missing."""
        tool = MockTool("ssh_exec", MEMINFO_WARNING)
        check = MemoryUsageCheck(host="web-01", config={}, tools=[tool])
        signals = await check.run()
        # MEMINFO_WARNING: ~88% usage, above default warning of 85
        assert len(signals) >= 1

    async def test_check_name(self):
        check = self._make_check(MEMINFO_NORMAL)
        assert check.name == "memory_usage"
