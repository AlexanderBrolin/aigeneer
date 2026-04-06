"""SSL certificate expiry check."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.checks.base import Check, Signal

# openssl date format: "Dec 31 23:59:59 2025 GMT"
_OPENSSL_DATE_FMT = "%b %d %H:%M:%S %Y %Z"


class SslCertificateCheck(Check):
    """Check SSL certificate expiry for configured virtual hosts.

    Connects to each vhost on port 443 using openssl s_client and reads
    the certificate's notAfter date, then computes days remaining.

    Config keys:
        warning_days  — warn when this many days left (default 14)
        critical_days — critical when this many days left (default 3)
        vhosts        — list of hostnames to check (default ["localhost"])
    """

    name = "ssl_certificate"

    async def run(self) -> list[Signal]:
        warning_days = self.config.get("warning_days", 14)
        critical_days = self.config.get("critical_days", 3)
        vhosts = self.config.get("vhosts", ["localhost"])

        signals: list[Signal] = []
        now = datetime.now(timezone.utc)

        for vhost in vhosts:
            cmd = (
                f"echo | openssl s_client -connect {vhost}:443 -servername {vhost} "
                f"2>/dev/null | openssl x509 -noout -enddate"
            )
            output = await self._exec(cmd)

            match = re.search(r"notAfter=(.+)", output)
            if not match:
                continue

            date_str = match.group(1).strip()
            try:
                expiry = datetime.strptime(date_str, _OPENSSL_DATE_FMT).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue

            days_left = (expiry - now).days

            if days_left <= critical_days:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="critical",
                        problem_type="ssl_expiring",
                        evidence=(
                            f"SSL cert for {vhost} expires in {days_left} days "
                            f"(critical threshold: {critical_days} days)"
                        ),
                        raw_data={"vhost": vhost, "days_left": days_left, "expiry": date_str},
                    )
                )
            elif days_left <= warning_days:
                signals.append(
                    Signal(
                        host=self.host,
                        severity="warning",
                        problem_type="ssl_expiring",
                        evidence=(
                            f"SSL cert for {vhost} expires in {days_left} days "
                            f"(warning threshold: {warning_days} days)"
                        ),
                        raw_data={"vhost": vhost, "days_left": days_left, "expiry": date_str},
                    )
                )

        return signals
