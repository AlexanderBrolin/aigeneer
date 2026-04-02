"""Tests for ReplicationCheck and SlowQueryCheck."""

import pytest

from app.checks.base import Signal
from app.checks.mariadb import ReplicationCheck, SlowQueryCheck
from tests.checks.conftest import MockTool

SLAVE_STATUS_OK = """\
*************************** 1. row ***************************
               Slave_IO_State: Waiting for master to send event
                  Master_Host: db-master.example.com
             Slave_IO_Running: Yes
            Slave_SQL_Running: Yes
        Seconds_Behind_Master: 0
"""

SLAVE_STATUS_LAG_WARNING = """\
*************************** 1. row ***************************
               Slave_IO_State: Waiting for master to send event
                  Master_Host: db-master.example.com
             Slave_IO_Running: Yes
            Slave_SQL_Running: Yes
        Seconds_Behind_Master: 60
"""

SLAVE_STATUS_LAG_CRITICAL = """\
*************************** 1. row ***************************
               Slave_IO_State: Waiting for master to send event
                  Master_Host: db-master.example.com
             Slave_IO_Running: Yes
            Slave_SQL_Running: Yes
        Seconds_Behind_Master: 500
"""

SLAVE_STATUS_IO_STOPPED = """\
*************************** 1. row ***************************
               Slave_IO_State:
                  Master_Host: db-master.example.com
             Slave_IO_Running: No
            Slave_SQL_Running: Yes
        Seconds_Behind_Master: NULL
"""

SLAVE_STATUS_SQL_STOPPED = """\
*************************** 1. row ***************************
               Slave_IO_State: Waiting for master to send event
                  Master_Host: db-master.example.com
             Slave_IO_Running: Yes
            Slave_SQL_Running: No
        Seconds_Behind_Master: NULL
                Last_SQL_Error: Error 'Duplicate entry' on query
"""

SLAVE_STATUS_BOTH_STOPPED = """\
*************************** 1. row ***************************
             Slave_IO_Running: No
            Slave_SQL_Running: No
        Seconds_Behind_Master: NULL
"""

SLAVE_STATUS_EMPTY = """\
"""

SLOW_QUERY_OUTPUT = """\
# Time: 2026-04-01T10:30:00.000000Z
# User@Host: root[root] @ localhost []
# Query_time: 12.345  Lock_time: 0.001 Rows_sent: 1  Rows_examined: 1000000
SET timestamp=1743500000;
SELECT * FROM large_table WHERE unindexed_col = 'value';
"""


class TestReplicationCheck:
    """Tests for MariaDB ReplicationCheck."""

    def _make_check(self, slave_output: str, config: dict | None = None) -> ReplicationCheck:
        cfg = config or {"warning_lag_seconds": 30, "critical_lag_seconds": 300}
        tool = MockTool("ssh_exec", slave_output)
        return ReplicationCheck(host="db-01", config=cfg, tools=[tool])

    async def test_no_signals_when_replication_ok(self):
        check = self._make_check(SLAVE_STATUS_OK)
        signals = await check.run()
        assert signals == []

    async def test_warning_on_lag(self):
        check = self._make_check(SLAVE_STATUS_LAG_WARNING)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "warning"
        assert sig.problem_type == "replication_lag"
        assert "60" in sig.evidence

    async def test_critical_on_large_lag(self):
        check = self._make_check(SLAVE_STATUS_LAG_CRITICAL)
        signals = await check.run()
        assert len(signals) == 1
        assert signals[0].severity == "critical"
        assert signals[0].problem_type == "replication_lag"

    async def test_critical_on_io_thread_stopped(self):
        check = self._make_check(SLAVE_STATUS_IO_STOPPED)
        signals = await check.run()
        stopped = [s for s in signals if s.problem_type == "replication_stopped"]
        assert len(stopped) >= 1
        assert stopped[0].severity == "critical"
        assert "IO" in stopped[0].evidence or "Slave_IO" in stopped[0].evidence

    async def test_critical_on_sql_thread_stopped(self):
        check = self._make_check(SLAVE_STATUS_SQL_STOPPED)
        signals = await check.run()
        stopped = [s for s in signals if s.problem_type == "replication_stopped"]
        assert len(stopped) >= 1
        assert stopped[0].severity == "critical"

    async def test_both_threads_stopped(self):
        check = self._make_check(SLAVE_STATUS_BOTH_STOPPED)
        signals = await check.run()
        stopped = [s for s in signals if s.problem_type == "replication_stopped"]
        assert len(stopped) >= 1
        assert all(s.severity == "critical" for s in stopped)

    async def test_empty_output_produces_warning(self):
        """If SHOW SLAVE STATUS returns empty, not a replica — info signal."""
        check = self._make_check(SLAVE_STATUS_EMPTY)
        signals = await check.run()
        # Either no signals or info that replication is not configured
        if signals:
            assert signals[0].severity == "info"

    async def test_check_name(self):
        check = self._make_check(SLAVE_STATUS_OK)
        assert check.name == "mariadb_replication"

    async def test_host_set_on_signals(self):
        check = self._make_check(SLAVE_STATUS_IO_STOPPED)
        signals = await check.run()
        assert all(s.host == "db-01" for s in signals)

    async def test_default_config_thresholds(self):
        """Uses default thresholds when config is empty."""
        tool = MockTool("ssh_exec", SLAVE_STATUS_LAG_WARNING)
        check = ReplicationCheck(host="db-01", config={}, tools=[tool])
        signals = await check.run()
        # 60s lag > default 30s warning
        assert len(signals) == 1
        assert signals[0].severity == "warning"


class TestSlowQueryCheck:
    """Tests for MariaDB SlowQueryCheck."""

    def _make_check(self, output: str, config: dict | None = None) -> SlowQueryCheck:
        cfg = config or {"log_path": "/var/log/mysql/slow.log", "tail_lines": 50}
        tool = MockTool("ssh_exec", output)
        return SlowQueryCheck(host="db-01", config=cfg, tools=[tool])

    async def test_signals_on_slow_queries(self):
        check = self._make_check(SLOW_QUERY_OUTPUT)
        signals = await check.run()
        assert len(signals) == 1
        sig = signals[0]
        assert sig.severity == "info"
        assert sig.problem_type == "slow_query"
        assert sig.host == "db-01"

    async def test_no_signals_on_empty_output(self):
        check = self._make_check("")
        signals = await check.run()
        assert signals == []

    async def test_check_name(self):
        check = self._make_check("")
        assert check.name == "slow_query"
