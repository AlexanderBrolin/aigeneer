"""Apache2 health check — service status and error log."""

from __future__ import annotations

from app.checks.base import Check, Signal


class ApacheHealthCheck(Check):
    """Check Apache2 health by verifying service status and scanning error log.

    Uses ``ssh_systemctl_status`` to check the apache2 service, and
    ``ssh_exec`` to tail the error log for recent errors.

    Config keys:
        log_path         — path to Apache error log (default /var/log/apache2/error.log)
        lookback_minutes — how far back to scan in minutes (default 30)
    """

    name = "apache_errors"

    async def run(self) -> list[Signal]:
        signals: list[Signal] = []

        # Check service status
        try:
            status_tool = self._get_tool("ssh_systemctl_status")
            status_output = await status_tool.ainvoke({"service": "apache2"})
            if "inactive" in status_output or "failed" in status_output:
                severity = "critical" if "failed" in status_output else "warning"
                signals.append(
                    Signal(
                        host=self.host,
                        severity=severity,
                        problem_type="service_down",
                        evidence=f"Apache2 service is not running: {status_output.strip()[:200]}",
                        raw_data={"service": "apache2"},
                    )
                )
        except StopIteration:
            # ssh_systemctl_status tool not available, skip service check
            pass

        # Check error log
        ssh = self._get_tool("ssh_exec")
        log_path = self.config.get("log_path", "/var/log/apache2/error.log")
        lookback = self.config.get("lookback_minutes", 30)

        output = await ssh.ainvoke(
            {"command": self._sudo(f"find {log_path} -mmin -{lookback} -exec tail -n 50 {{}} \\;")}
        )

        if output and output.strip():
            # Count error lines (lines containing [error] or [crit] etc.)
            error_lines = [
                line
                for line in output.strip().splitlines()
                if any(lvl in line.lower() for lvl in ("[error]", "[crit]", "[alert]", "[emerg]"))
            ]

            if error_lines:
                severity = "warning" if len(error_lines) < 10 else "critical"
                signals.append(
                    Signal(
                        host=self.host,
                        severity=severity,
                        problem_type="apache_errors",
                        evidence=(
                            f"{len(error_lines)} error(s) in {log_path} "
                            f"(last {lookback} min):\n" + "\n".join(error_lines[:5])
                        ),
                        raw_data={
                            "log_path": log_path,
                            "error_count": len(error_lines),
                            "sample_errors": error_lines[:5],
                        },
                    )
                )

        return signals
