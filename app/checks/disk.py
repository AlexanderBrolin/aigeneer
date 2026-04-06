"""Disk space check — monitors filesystem usage via df."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class DiskSpaceCheck(Check):
    """Check free disk space on configured mount points.

    Parses output of ``df -h --output=source,pcent,target`` and produces
    warning/critical signals when usage exceeds thresholds.

    Config keys:
        threshold_warning  — percentage (default 80)
        threshold_critical — percentage (default 90)
        paths              — list of mount points to monitor (default ["/"])
    """

    name = "disk_space"

    async def run(self) -> list[Signal]:
        output = await self._exec("df -h --output=source,pcent,target")

        threshold_warn = self.config.get("threshold_warning", 80)
        threshold_crit = self.config.get("threshold_critical", 90)
        paths = self.config.get("paths", ["/"])

        signals: list[Signal] = []

        for line in output.strip().splitlines():
            # Skip header line(s)
            if "Filesystem" in line or "Use%" in line:
                continue

            match = re.search(r"(\d+)%\s+(\S+)", line)
            if not match:
                continue

            pcent = int(match.group(1))
            mount = match.group(2)

            if mount not in paths:
                continue

            if pcent >= threshold_crit:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="critical",
                        problem_type="disk_full",
                        evidence=f"{mount} is {pcent}% full (critical threshold: {threshold_crit}%)",
                        raw_data={"pcent": pcent, "mount": mount},
                    )
                )
            elif pcent >= threshold_warn:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="warning",
                        problem_type="disk_full",
                        evidence=f"{mount} is {pcent}% full (warning threshold: {threshold_warn}%)",
                        raw_data={"pcent": pcent, "mount": mount},
                    )
                )

        return signals
