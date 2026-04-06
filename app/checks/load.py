"""Load average check — monitors system load relative to CPU count."""

from __future__ import annotations

from app.checks.base import Check, Signal


class LoadAverageCheck(Check):
    """Check system load average relative to the number of CPUs.

    Issues two commands:
    - ``nproc`` — number of available CPUs
    - ``cat /proc/loadavg`` — 1/5/15-minute load averages

    A signal is raised when load_1 >= cpu_count * multiplier.

    Config keys:
        multiplier_warning  — load ratio to warn (default 1.5)
        multiplier_critical — load ratio for critical (default 3.0)
    """

    name = "load_average"

    async def run(self) -> list[Signal]:
        nproc_out = await self._exec("nproc")
        loadavg_out = await self._exec("cat /proc/loadavg")

        multiplier_warn = self.config.get("multiplier_warning", 1.5)
        multiplier_crit = self.config.get("multiplier_critical", 3.0)

        cpu_count = int(nproc_out.strip())
        load_1 = float(loadavg_out.strip().split()[0])

        ratio = load_1 / cpu_count if cpu_count > 0 else 0.0

        signals: list[Signal] = []

        if ratio >= multiplier_crit:
            signals.append(
                Signal(
                    host=self.host,
                    severity="critical",
                    problem_type="high_load",
                    evidence=(
                        f"1-minute load average {load_1:.2f} is {ratio:.1f}x CPU count "
                        f"({cpu_count} CPUs, critical threshold: {multiplier_crit}x)"
                    ),
                    raw_data={"load_1": load_1, "cpu_count": cpu_count, "ratio": round(ratio, 2)},
                )
            )
        elif ratio >= multiplier_warn:
            signals.append(
                Signal(
                    host=self.host,
                    severity="warning",
                    problem_type="high_load",
                    evidence=(
                        f"1-minute load average {load_1:.2f} is {ratio:.1f}x CPU count "
                        f"({cpu_count} CPUs, warning threshold: {multiplier_warn}x)"
                    ),
                    raw_data={"load_1": load_1, "cpu_count": cpu_count, "ratio": round(ratio, 2)},
                )
            )

        return signals
