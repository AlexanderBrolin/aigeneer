"""Tests for LoadAverageCheck."""

import pytest

from app.checks.base import Signal
from app.checks.load import LoadAverageCheck
from tests.checks.conftest import DynamicMockTool

# /proc/loadavg: load_1 load_5 load_15 running/total last_pid
LOADAVG_NORMAL = "0.50 0.60 0.55 2/300 12345"   # load_1=0.5, 4 CPUs → 0.5/4=0.125
LOADAVG_WARNING = "7.00 5.00 4.00 3/300 12346"   # load_1=7.0, 4 CPUs → 1.75x (>1.5)
LOADAVG_CRITICAL = "14.00 10.00 8.00 5/300 12347"  # load_1=14.0, 4 CPUs → 3.5x (>3.0)

NPROC_4 = "4"
NPROC_8 = "8"


class TestLoadAverageCheck:
    """Tests for LoadAverageCheck."""

    def _make_check(
        self,
        nproc: str,
        loadavg: str,
        config: dict | None = None,
    ) -> LoadAverageCheck:
        cfg = config or {"multiplier_warning": 1.5, "multiplier_critical": 3.0}
        tool = DynamicMockTool(
            "ssh_exec",
            {
                "nproc": nproc,
                "loadavg": loadavg,
            },
        )
        return LoadAverageCheck(host="web-01", config=cfg, tools=[tool])

    async def test_no_signals_when_normal(self):
        check = self._make_check(NPROC_4, LOADAVG_NORMAL)
        signals = await check.run()
        assert signals == []

    async def test_warning_signal(self):
        check = self._make_check(NPROC_4, LOADAVG_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "warning"
        assert sig.host == "web-01"
        assert sig.problem_type == "high_load"
        assert "7" in sig.evidence or "load" in sig.evidence.lower()

    async def test_critical_signal(self):
        check = self._make_check(NPROC_4, LOADAVG_CRITICAL)
        signals = await check.run()
        assert len(signals) == 1
        assert signals[0].severity == "critical"

    async def test_more_cpus_means_higher_threshold(self):
        """Same load on 8 CPUs should not trigger a warning."""
        # load_1=7.0, 8 CPUs → 0.875x — below warning multiplier of 1.5
        check = self._make_check(NPROC_8, LOADAVG_WARNING)
        signals = await check.run()
        assert signals == []

    async def test_raw_data_contains_load_and_cpu_count(self):
        check = self._make_check(NPROC_4, LOADAVG_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        rd = signals[0].raw_data
        assert "load_1" in rd
        assert "cpu_count" in rd

    async def test_default_config_values(self):
        """Check uses defaults when config keys are missing."""
        tool = DynamicMockTool(
            "ssh_exec",
            {"nproc": NPROC_4, "loadavg": LOADAVG_WARNING},
        )
        check = LoadAverageCheck(host="web-01", config={}, tools=[tool])
        signals = await check.run()
        # load_1=7.0 / 4 CPUs = 1.75x > default warning 1.5
        assert len(signals) >= 1

    async def test_check_name(self):
        check = self._make_check(NPROC_4, LOADAVG_NORMAL)
        assert check.name == "load_average"
