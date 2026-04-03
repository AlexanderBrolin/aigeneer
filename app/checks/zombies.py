"""Zombie process check."""

from __future__ import annotations

from app.checks.base import Check, Signal


class ZombieProcessCheck(Check):
    """Detect zombie (defunct) processes exceeding a configurable threshold.

    Runs ``ps aux --no-headers | awk '$8 ~ /^Z/ {print $0}'`` to list
    zombie processes, then signals if the count exceeds the threshold.

    Config keys:
        threshold — number of zombies before signalling (default 5)
    """

    name = "zombie_processes"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke(
            {"command": r"ps aux --no-headers | awk '$8 ~ /^Z/ {print $0}'"}
        )

        threshold = self.config.get("threshold", 5)

        zombie_lines = [line for line in output.splitlines() if line.strip()]
        count = len(zombie_lines)

        if count > threshold:
            return [
                Signal(
                    host=self.host,
                    severity="warning",
                    problem_type="zombie_processes",
                    evidence=(
                        f"Found {count} zombie processes (threshold: {threshold})"
                    ),
                    raw_data={"count": count, "threshold": threshold},
                )
            ]

        return []
