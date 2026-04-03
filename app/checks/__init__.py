"""Check system — collects signals from monitored hosts.

Each check class knows how to gather data via MCP tools (SSH, MySQL)
and return a list of Signal objects for further analysis.
"""

from app.checks.apache import ApacheHealthCheck
from app.checks.base import Check, Signal
from app.checks.disk import DiskSpaceCheck
from app.checks.failed_units import FailedUnitsCheck
from app.checks.inode import DiskInodeCheck
from app.checks.load import LoadAverageCheck
from app.checks.mariadb import ReplicationCheck, SlowQueryCheck
from app.checks.memory import MemoryUsageCheck
from app.checks.ports import OpenPortsCheck
from app.checks.services import SystemdServiceCheck
from app.checks.ssl import SslCertificateCheck
from app.checks.zombies import ZombieProcessCheck

CHECK_REGISTRY: dict[str, type[Check]] = {
    "disk_space": DiskSpaceCheck,
    "systemd_services": SystemdServiceCheck,
    "mariadb_replication": ReplicationCheck,
    "slow_query": SlowQueryCheck,
    "apache_errors": ApacheHealthCheck,
    "memory_usage": MemoryUsageCheck,
    "load_average": LoadAverageCheck,
    "disk_inode": DiskInodeCheck,
    "ssl_certificate": SslCertificateCheck,
    "systemd_failed": FailedUnitsCheck,
    "zombie_processes": ZombieProcessCheck,
    "open_ports": OpenPortsCheck,
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
    "MemoryUsageCheck",
    "LoadAverageCheck",
    "DiskInodeCheck",
    "SslCertificateCheck",
    "FailedUnitsCheck",
    "ZombieProcessCheck",
    "OpenPortsCheck",
]
