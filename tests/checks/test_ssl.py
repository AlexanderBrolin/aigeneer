"""Tests for SslCertificateCheck."""

from app.checks.ssl import SslCertificateCheck
from tests.checks.conftest import DynamicMockTool


def _make_check(openssl_output: str, config: dict | None = None) -> SslCertificateCheck:
    cfg = config or {"warning_days": 14, "critical_days": 3, "vhosts": ["example.com"]}
    tool = DynamicMockTool(
        "ssh_exec",
        {"openssl": openssl_output},
        default="",
    )
    return SslCertificateCheck(host="web-01", config=cfg, tools=[tool])


class TestSslCertificateCheck:
    """Tests for SslCertificateCheck."""

    async def test_valid_cert_far_future_no_signal(self):
        """Certificate valid far in the future — no signal."""
        # 9999 is far future
        output = "notAfter=Dec 31 23:59:59 9999 GMT\n"
        check = _make_check(output)
        signals = await check.run()
        assert signals == []

    async def test_expiring_in_10_days_warning(self):
        """Certificate expiring in ~10 days → warning signal."""
        from datetime import datetime, timedelta, timezone

        expiry = datetime.now(timezone.utc) + timedelta(days=10)
        # openssl date format: "Dec 31 23:59:59 2025 GMT"
        date_str = expiry.strftime("%b %d %H:%M:%S %Y GMT")
        output = f"notAfter={date_str}\n"
        check = _make_check(output)
        signals = await check.run()
        assert len(signals) == 1
        assert signals[0].severity == "warning"
        assert signals[0].problem_type == "ssl_expiring"
        assert signals[0].host == "web-01"

    async def test_expiring_in_2_days_critical(self):
        """Certificate expiring in ~2 days → critical signal."""
        from datetime import datetime, timedelta, timezone

        expiry = datetime.now(timezone.utc) + timedelta(days=2)
        date_str = expiry.strftime("%b %d %H:%M:%S %Y GMT")
        output = f"notAfter={date_str}\n"
        check = _make_check(output)
        signals = await check.run()
        assert len(signals) == 1
        assert signals[0].severity == "critical"
        assert signals[0].problem_type == "ssl_expiring"

    async def test_check_name(self):
        check = _make_check("notAfter=Dec 31 23:59:59 9999 GMT\n")
        assert check.name == "ssl_certificate"

    async def test_evidence_contains_days_left(self):
        """Evidence string should mention days remaining."""
        from datetime import datetime, timedelta, timezone

        expiry = datetime.now(timezone.utc) + timedelta(days=10)
        date_str = expiry.strftime("%b %d %H:%M:%S %Y GMT")
        output = f"notAfter={date_str}\n"
        check = _make_check(output)
        signals = await check.run()
        assert len(signals) == 1
        assert "10" in signals[0].evidence or "days" in signals[0].evidence
