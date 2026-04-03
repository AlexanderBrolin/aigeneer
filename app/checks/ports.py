"""Open ports check — detects unexpected listening ports."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal

_PORT_RE = re.compile(r":(\d+)\s")


class OpenPortsCheck(Check):
    """Report listening ports not in the expected list.

    Runs ``ss -tlnp`` and parses port numbers from the local address column.
    Any port not in ``expected_ports`` produces an info signal.

    Config keys:
        expected_ports — list of int port numbers that are allowed (default [])
    """

    name = "open_ports"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "ss -tlnp"})

        expected = set(self.config.get("expected_ports", []))

        found_ports: set[int] = set()
        for line in output.splitlines():
            for match in _PORT_RE.finditer(line):
                found_ports.add(int(match.group(1)))

        signals: list[Signal] = []
        for port in sorted(found_ports - expected):
            signals.append(
                Signal(
                    host=self.host,
                    severity="info",
                    problem_type="unexpected_port",
                    evidence=f"Unexpected port {port} is listening (not in expected_ports)",
                    raw_data={"port": port},
                )
            )

        return signals
