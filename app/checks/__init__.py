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

CHECK_LABELS: dict[str, str] = {
    "disk_space": "Дисковое пространство",
    "systemd_services": "Systemd сервисы",
    "mariadb_replication": "MariaDB репликация",
    "slow_query": "MariaDB медленные запросы",
    "apache_errors": "Apache ошибки",
    "memory_usage": "Использование памяти",
    "load_average": "Нагрузка CPU (Load Average)",
    "disk_inode": "Inodes дисков",
    "ssl_certificate": "SSL сертификаты",
    "systemd_failed": "Failed systemd юниты",
    "zombie_processes": "Зомби-процессы",
    "open_ports": "Открытые порты",
}

CHECK_DEFAULT_PARAMS: dict[str, dict] = {
    "disk_space": {"threshold_warning": 80, "threshold_critical": 90, "paths": ["/", "/var"]},
    "systemd_services": {"services": ["apache2", "mariadb"]},
    "mariadb_replication": {"warning_lag_seconds": 30, "critical_lag_seconds": 300},
    "slow_query": {"lines": 50, "log_path": "/var/log/mysql/mysql-slow.log"},
    "apache_errors": {"log_path": "/var/log/apache2/error.log", "lookback_minutes": 30},
    "memory_usage": {"threshold_warning": 85, "threshold_critical": 95},
    "load_average": {"multiplier_warning": 1.5, "multiplier_critical": 3.0},
    "disk_inode": {"threshold_warning": 85, "threshold_critical": 95, "paths": ["/"]},
    "ssl_certificate": {"warning_days": 14, "critical_days": 3, "vhosts": ["localhost"]},
    "systemd_failed": {},
    "zombie_processes": {"threshold": 5},
    "open_ports": {"expected_ports": [22, 80, 443, 3306]},
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
