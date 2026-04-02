"""MariaDB checks — replication status and slow query log."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class ReplicationCheck(Check):
    """Check MariaDB replication health.

    Executes ``SHOW SLAVE STATUS\\G`` via ssh_exec and parses the output
    to detect stopped threads and replication lag.

    Config keys:
        warning_lag_seconds  — lag threshold for warning (default 30)
        critical_lag_seconds — lag threshold for critical (default 300)
    """

    name = "mariadb_replication"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke(
            {"command": 'mysql -e "SHOW SLAVE STATUS\\G"'}
        )

        # If output is empty/whitespace, replication is not configured
        if not output or not output.strip():
            return [
                Signal(
                    host=self.host,
                    severity="info",
                    problem_type="replication_not_configured",
                    evidence="SHOW SLAVE STATUS returned empty — replication is not configured",
                )
            ]

        signals: list[Signal] = []

        io_running = self._extract_field(output, "Slave_IO_Running")
        sql_running = self._extract_field(output, "Slave_SQL_Running")
        lag_raw = self._extract_field(output, "Seconds_Behind_Master")

        # Check thread status
        stopped_threads = []
        if io_running and io_running.lower() != "yes":
            stopped_threads.append("Slave_IO_Running")
        if sql_running and sql_running.lower() != "yes":
            stopped_threads.append("Slave_SQL_Running")

        if stopped_threads:
            last_error = self._extract_field(output, "Last_SQL_Error") or ""
            evidence_parts = [
                f"Replication thread(s) stopped: {', '.join(stopped_threads)}"
            ]
            if last_error:
                evidence_parts.append(f"Last error: {last_error}")

            signals.append(
                Signal(
                    host=self.host,
                    severity="critical",
                    problem_type="replication_stopped",
                    evidence="; ".join(evidence_parts),
                    raw_data={
                        "io_running": io_running,
                        "sql_running": sql_running,
                        "stopped_threads": stopped_threads,
                    },
                )
            )

        # Check lag (only meaningful if threads are running)
        if lag_raw and lag_raw.upper() != "NULL" and not stopped_threads:
            try:
                lag = int(lag_raw)
            except ValueError:
                lag = None

            if lag is not None:
                warn_threshold = self.config.get("warning_lag_seconds", 30)
                crit_threshold = self.config.get("critical_lag_seconds", 300)

                if lag >= crit_threshold:
                    signals.append(
                        Signal(
                            host=self.host,
                            severity="critical",
                            problem_type="replication_lag",
                            evidence=f"Replication lag is {lag}s (critical threshold: {crit_threshold}s)",
                            raw_data={"lag_seconds": lag},
                        )
                    )
                elif lag >= warn_threshold:
                    signals.append(
                        Signal(
                            host=self.host,
                            severity="warning",
                            problem_type="replication_lag",
                            evidence=f"Replication lag is {lag}s (warning threshold: {warn_threshold}s)",
                            raw_data={"lag_seconds": lag},
                        )
                    )

        return signals

    @staticmethod
    def _extract_field(output: str, field_name: str) -> str | None:
        """Extract a field value from SHOW SLAVE STATUS \\G output."""
        pattern = rf"^\s*{re.escape(field_name)}:\s*(.*)$"
        match = re.search(pattern, output, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None


class SlowQueryCheck(Check):
    """Check MariaDB slow query log for recent entries.

    Tails the slow query log and returns info-level signals with
    the content.

    Config keys:
        log_path   — path to slow query log (default /var/log/mysql/slow.log)
        tail_lines — how many lines to tail (default 50)
    """

    name = "slow_query"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        log_path = self.config.get("log_path", "/var/log/mysql/slow.log")
        tail_lines = self.config.get("tail_lines", 50)

        output = await ssh.ainvoke(
            {"command": f"tail -n {tail_lines} {log_path}"}
        )

        if not output or not output.strip():
            return []

        return [
            Signal(
                host=self.host,
                severity="info",
                problem_type="slow_query",
                evidence=f"Slow queries found in {log_path}:\n{output.strip()}",
                raw_data={"log_path": log_path, "content": output.strip()},
            )
        ]
