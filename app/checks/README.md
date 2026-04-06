# Checks — Infrastructure Monitoring

Each check collects signals from a remote server via SSH and returns a list of `Signal` objects for the analysis graph.

## How to Configure

1. Go to **Servers** in the web panel
2. Click **Configure Checks** for a server
3. Enable the checks you need and set JSON parameters
4. Save

Checks run on a schedule via Celery Beat (interval in Settings > Schedule).

## Available Checks

### disk_space — Disk Space
Monitors filesystem usage via `df -h`.

```json
{
  "threshold_warning": 80,
  "threshold_critical": 90,
  "paths": ["/", "/var"]
}
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `threshold_warning` | int | 80 | % usage for warning |
| `threshold_critical` | int | 90 | % usage for critical |
| `paths` | list[str] | `["/"]` | Mount points to monitor |

### disk_inode — Inode Usage
Monitors inode usage via `df -i`. Same params as disk_space.

```json
{
  "threshold_warning": 85,
  "threshold_critical": 95,
  "paths": ["/"]
}
```

### memory_usage — RAM & Swap
Monitors memory via `/proc/meminfo`. Swap alerts at 80% regardless of thresholds.

```json
{
  "threshold_warning": 85,
  "threshold_critical": 95
}
```

### load_average — CPU Load
Compares 1-minute load average against CPU count.

```json
{
  "multiplier_warning": 1.5,
  "multiplier_critical": 3.0
}
```
Warning when `load_1min >= cpu_count * multiplier_warning`.

### systemd_services — Service Status
Checks specific systemd services.

```json
{
  "services": ["apache2", "mariadb"]
}
```
Returns critical for `failed`, warning for `inactive`/other states.

### systemd_failed — All Failed Units
Scans all systemd units for failed state. No params needed.

```json
{}
```

### mariadb_replication — Replication Health
Checks `SHOW SLAVE STATUS` for stopped threads and lag.

```json
{
  "warning_lag_seconds": 30,
  "critical_lag_seconds": 300
}
```

### slow_query — MariaDB Slow Queries
Tails the slow query log.

```json
{
  "lines": 50,
  "log_path": "/var/log/mysql/mysql-slow.log"
}
```

### apache_errors — Apache Error Log
Scans Apache error log for recent errors.

```json
{
  "log_path": "/var/log/apache2/error.log",
  "lookback_minutes": 30
}
```

### ssl_certificate — SSL Expiry
Checks SSL certificate expiry dates for vhosts.

```json
{
  "warning_days": 14,
  "critical_days": 3,
  "vhosts": ["example.com"]
}
```

### zombie_processes — Zombie Processes
Counts zombie processes.

```json
{
  "threshold": 5
}
```
Warns when zombie count exceeds threshold.

### open_ports — Unexpected Ports
Reports listening ports not in the expected list.

```json
{
  "expected_ports": [22, 80, 443, 3306]
}
```

## How to Add a New Check

1. Create `app/checks/your_check.py` extending `Check(ABC)` from `base.py`
2. Implement `async def run(self) -> list[Signal]`
3. Use `self._get_tool("ssh_exec")` for commands, `self._sudo(cmd)` for privileged ones
4. Register in `app/checks/__init__.py`: add to `CHECK_REGISTRY`, `CHECK_LABELS`, `CHECK_DEFAULT_PARAMS`
5. Write tests in `tests/checks/test_your_check.py`

## Sudo Handling

When `ssh_user != root`, checks receive `use_sudo=True`. Use `self._sudo(command)` to automatically prefix with `sudo` for privileged commands (mysql, log reads, ss, systemctl).

Commands that DON'T need sudo: `df`, `cat /proc/*`, `nproc`, `ps aux`, `openssl`.
