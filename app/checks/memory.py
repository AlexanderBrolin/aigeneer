"""Memory usage check — monitors RAM and swap via /proc/meminfo."""

from __future__ import annotations

from app.checks.base import Check, Signal


class MemoryUsageCheck(Check):
    """Check RAM and swap usage on a host.

    Reads ``/proc/meminfo`` and computes:
    - RAM usage: (MemTotal - MemAvailable) / MemTotal * 100
    - Swap usage: (SwapTotal - SwapFree) / SwapTotal * 100  (skipped if SwapTotal == 0)

    Config keys:
        threshold_warning  — RAM usage % (default 85)
        threshold_critical — RAM usage % (default 95)
        swap_threshold     — swap usage % to warn (default 80)
    """

    name = "memory_usage"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "cat /proc/meminfo"})

        threshold_warn = self.config.get("threshold_warning", 85)
        threshold_crit = self.config.get("threshold_critical", 95)
        swap_threshold = self.config.get("swap_threshold", 80)

        values: dict[str, int] = {}
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                try:
                    values[key] = int(parts[1])
                except ValueError:
                    pass

        signals: list[Signal] = []

        mem_total = values.get("MemTotal", 0)
        mem_available = values.get("MemAvailable", 0)

        if mem_total > 0:
            usage_pct = (mem_total - mem_available) / mem_total * 100

            if usage_pct >= threshold_crit:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="critical",
                        problem_type="high_memory",
                        evidence=(
                            f"RAM usage is {usage_pct:.1f}% "
                            f"(critical threshold: {threshold_crit}%)"
                        ),
                        raw_data={"usage_pct": round(usage_pct, 1), "mem_total_kb": mem_total},
                    )
                )
            elif usage_pct >= threshold_warn:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="warning",
                        problem_type="high_memory",
                        evidence=(
                            f"RAM usage is {usage_pct:.1f}% "
                            f"(warning threshold: {threshold_warn}%)"
                        ),
                        raw_data={"usage_pct": round(usage_pct, 1), "mem_total_kb": mem_total},
                    )
                )

        swap_total = values.get("SwapTotal", 0)
        swap_free = values.get("SwapFree", 0)

        if swap_total > 0:
            swap_pct = (swap_total - swap_free) / swap_total * 100

            if swap_pct >= swap_threshold:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="warning",
                        problem_type="high_swap",
                        evidence=(
                            f"Swap usage is {swap_pct:.1f}% "
                            f"(threshold: {swap_threshold}%)"
                        ),
                        raw_data={"swap_pct": round(swap_pct, 1), "swap_total_kb": swap_total},
                    )
                )

        return signals
