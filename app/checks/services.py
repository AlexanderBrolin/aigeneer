"""Systemd service check — monitors service status via systemctl."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class SystemdServiceCheck(Check):
    """Check the status of configured systemd services.

    Uses the ``ssh_systemctl_status`` tool for each service and parses
    the Active line to determine state.

    Config keys:
        services — list of service names to check (required)
    """

    name = "systemd_services"

    async def run(self) -> list[Signal]:
        services = self.config.get("services", [])

        signals: list[Signal] = []

        for service in services:
            output = await self._exec_status(service)
            state = self._parse_state(output)

            if state == "failed":
                signals.append(
                    Signal(
                        host=self.host,
                        severity="critical",
                        problem_type="service_down",
                        evidence=f"Service {service} is in failed state",
                        raw_data={"service": service, "state": state},
                    )
                )
            elif state != "active":
                # inactive, deactivating, activating, etc.
                signals.append(
                    Signal(
                        host=self.host,
                        severity="warning",
                        problem_type="service_down",
                        evidence=f"Service {service} is {state} (not running)",
                        raw_data={"service": service, "state": state},
                    )
                )

        return signals

    @staticmethod
    def _parse_state(output: str) -> str:
        """Extract the service state from systemctl output.

        Handles both:
        - Simple ``is-active`` output: just the state word (active/inactive/failed)
        - Full ``status`` output with an ``Active:`` line
        """
        simple = output.strip()
        known = {"active", "inactive", "failed", "activating", "deactivating", "reloading"}
        if simple in known:
            return simple
        for line in output.splitlines():
            match = re.search(r"Active:\s+(\S+)", line)
            if match:
                return match.group(1)
        return "unknown"
