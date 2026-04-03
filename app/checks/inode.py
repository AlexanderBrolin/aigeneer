"""Disk inode check — monitors inode usage via df -i."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class DiskInodeCheck(Check):
    """Check inode usage on configured mount points.

    Parses output of ``df -i --output=source,ipcent,target`` and produces
    warning/critical signals when inode usage exceeds thresholds.

    Config keys:
        threshold_warning  — percentage (default 85)
        threshold_critical — percentage (default 95)
        paths              — list of mount points to monitor (default ["/"])
    """

    name = "disk_inode"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "df -i --output=source,ipcent,target"})

        threshold_warn = self.config.get("threshold_warning", 85)
        threshold_crit = self.config.get("threshold_critical", 95)
        paths = self.config.get("paths", ["/"])

        signals: list[Signal] = []

        for line in output.strip().splitlines():
            # Skip header line(s)
            if "Filesystem" in line or "IUse%" in line:
                continue

            match = re.search(r"(\d+)%\s+(\S+)", line)
            if not match:
                continue

            ipcent = int(match.group(1))
            mount = match.group(2)

            if mount not in paths:
                continue

            if ipcent >= threshold_crit:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="critical",
                        problem_type="inode_exhaustion",
                        evidence=(
                            f"{mount} inode usage is {ipcent}% "
                            f"(critical threshold: {threshold_crit}%)"
                        ),
                        raw_data={"ipcent": ipcent, "mount": mount},
                    )
                )
            elif ipcent >= threshold_warn:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="warning",
                        problem_type="inode_exhaustion",
                        evidence=(
                            f"{mount} inode usage is {ipcent}% "
                            f"(warning threshold: {threshold_warn}%)"
                        ),
                        raw_data={"ipcent": ipcent, "mount": mount},
                    )
                )

        return signals
