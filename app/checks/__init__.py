"""Check system — collects signals from monitored hosts.

Each check class knows how to gather data via MCP tools (SSH, MySQL)
and return a list of Signal objects for further analysis.
"""

from app.checks.apache import ApacheHealthCheck
from app.checks.base import Check, Signal
from app.checks.disk import DiskSpaceCheck
from app.checks.mariadb import ReplicationCheck, SlowQueryCheck
from app.checks.services import SystemdServiceCheck

CHECK_REGISTRY: dict[str, type[Check]] = {
    "disk_space": DiskSpaceCheck,
    "systemd_services": SystemdServiceCheck,
    "mariadb_replication": ReplicationCheck,
    "slow_query": SlowQueryCheck,
    "apache_errors": ApacheHealthCheck,
}

__all__ = [
    "CHECK_REGISTRY",
    "Check",
    "Signal",
    "DiskSpaceCheck",
    "SystemdServiceCheck",
    "ReplicationCheck",
    "SlowQueryCheck",
    "ApacheHealthCheck",
]
