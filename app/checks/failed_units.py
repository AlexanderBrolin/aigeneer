"""Failed systemd units check."""

from __future__ import annotations

from app.checks.base import Check, Signal


class FailedUnitsCheck(Check):
    """Report any systemd units in a failed state.

    Runs ``systemctl --failed --no-legend --plain`` and emits a warning
    signal for each failed unit found.

    Config keys: (none required)
    """

    name = "systemd_failed"

    async def run(self) -> list[Signal]:
        output = await self._exec(self._sudo("systemctl --failed --no-legend --plain"))

        signals: list[Signal] = []

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            # First field is the unit name (e.g. "nginx.service")
            unit = line.split()[0]
            signals.append(
                Signal(
                    host=self.host,
                    severity="warning",
                    problem_type="systemd_unit_failed",
                    evidence=f"Systemd unit {unit} is in a failed state",
                    raw_data={"unit": unit, "raw_line": line},
                )
            )

        return signals
