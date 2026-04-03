# Checks, Runbooks & TG Commands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 new infrastructure checks, 8 new runbooks, and interactive Telegram commands for querying servers/incidents from chat.

**Architecture:** All checks extend `Check(ABC)` → `list[Signal]`, all runbooks extend `Runbook(ABC)` → `RunbookResult`. Both use pre-bound `ssh_exec` tool. TG commands go through an expanded `command_graph` with a new `db_query` intent for DB-only reads.

**Tech Stack:** Python 3.12, asyncssh (via ssh_exec tool), pytest, aiogram 3.x, LangGraph

---

## File Structure

**Phase A — New checks (create):**
- `app/checks/memory.py` — MemoryUsageCheck
- `app/checks/load.py` — LoadAverageCheck
- `app/checks/inode.py` — DiskInodeCheck
- `app/checks/ssl.py` — SslCertificateCheck
- `app/checks/failed_units.py` — FailedUnitsCheck
- `app/checks/zombies.py` — ZombieProcessCheck
- `app/checks/ports.py` — OpenPortsCheck
- `tests/checks/test_memory.py`
- `tests/checks/test_load.py`
- `tests/checks/test_inode.py`
- `tests/checks/test_ssl.py`
- `tests/checks/test_failed_units.py`
- `tests/checks/test_zombies.py`
- `tests/checks/test_ports.py`

**Phase A — Modify:**
- `app/checks/__init__.py` — register all 7 new checks

**Phase B — New runbooks (create):**
- `app/runbooks/show_top_processes.py`
- `app/runbooks/show_connections.py`
- `app/runbooks/show_disk_usage.py`
- `app/runbooks/mysql_processlist.py`
- `app/runbooks/check_backup.py`
- `app/runbooks/rotate_logs.py`
- `app/runbooks/kill_process.py`
- `app/runbooks/free_memory.py`
- `tests/runbooks/test_show_top_processes.py`
- `tests/runbooks/test_show_connections.py`
- `tests/runbooks/test_show_disk_usage.py`
- `tests/runbooks/test_mysql_processlist.py`
- `tests/runbooks/test_check_backup.py`
- `tests/runbooks/test_rotate_logs.py`
- `tests/runbooks/test_kill_process.py`
- `tests/runbooks/test_free_memory.py`

**Phase B — Modify:**
- `app/runbooks/__init__.py` — register all 8 new runbooks

**Phase C — Modify:**
- `app/agent/graphs/command.py` — add `db_query` intent, new node, update routing
- `app/agent/prompts.py` — update CLASSIFY_PROMPT and NORMALIZE_PROMPT with all runbooks
- `app/bot/handlers.py` — response formatting (monospace, truncation)
- `tests/agent/test_command.py` — test new db_query node

---

### Task 1: Checks — memory_usage, load_average, disk_inode

**Files:**
- Create: `app/checks/memory.py`, `app/checks/load.py`, `app/checks/inode.py`
- Create: `tests/checks/test_memory.py`, `tests/checks/test_load.py`, `tests/checks/test_inode.py`

- [ ] **Step 1: Write tests for MemoryUsageCheck**

Create `tests/checks/test_memory.py`:

```python
"""Tests for MemoryUsageCheck."""

from app.checks.memory import MemoryUsageCheck
from tests.checks.conftest import MockTool

MEMINFO_NORMAL = """\
MemTotal:       16384000 kB
MemFree:         2000000 kB
MemAvailable:    8000000 kB
SwapTotal:       4096000 kB
SwapFree:        4096000 kB
"""

MEMINFO_WARNING = """\
MemTotal:       16384000 kB
MemFree:          500000 kB
MemAvailable:    2000000 kB
SwapTotal:       4096000 kB
SwapFree:        3000000 kB
"""

MEMINFO_CRITICAL = """\
MemTotal:       16384000 kB
MemFree:          100000 kB
MemAvailable:     500000 kB
SwapTotal:       4096000 kB
SwapFree:         100000 kB
"""


class TestMemoryUsageCheck:
    def _make(self, output, config=None):
        cfg = config or {"threshold_warning": 85, "threshold_critical": 95}
        return MemoryUsageCheck(host="web-01", config=cfg, tools=[MockTool("ssh_exec", output)])

    async def test_normal_no_signals(self):
        signals = await self._make(MEMINFO_NORMAL).run()
        assert signals == []

    async def test_warning_signal(self):
        signals = await self._make(MEMINFO_WARNING).run()
        assert len(signals) >= 1
        assert signals[0].severity == "warning"
        assert signals[0].problem_type == "high_memory"

    async def test_critical_signal(self):
        signals = await self._make(MEMINFO_CRITICAL).run()
        sev = [s.severity for s in signals]
        assert "critical" in sev

    async def test_check_name(self):
        assert self._make(MEMINFO_NORMAL).name == "memory_usage"
```

- [ ] **Step 2: Write tests for LoadAverageCheck**

Create `tests/checks/test_load.py`:

```python
"""Tests for LoadAverageCheck."""

from app.checks.load import LoadAverageCheck
from tests.checks.conftest import DynamicMockTool

NPROC_AND_LOAD_NORMAL = {"nproc": "4", "loadavg": "1.50 1.20 0.80 1/200 12345"}
NPROC_AND_LOAD_WARNING = {"nproc": "4", "loadavg": "7.00 5.00 3.00 3/200 12345"}
NPROC_AND_LOAD_CRITICAL = {"nproc": "2", "loadavg": "8.00 7.00 6.00 5/200 12345"}


class TestLoadAverageCheck:
    def _make(self, nproc, loadavg, config=None):
        cfg = config or {"multiplier_warning": 1.5, "multiplier_critical": 3.0}
        tool = DynamicMockTool("ssh_exec", {"nproc": nproc, "loadavg": loadavg})
        return LoadAverageCheck(host="web-01", config=cfg, tools=[tool])

    async def test_normal_no_signals(self):
        d = NPROC_AND_LOAD_NORMAL
        signals = await self._make(d["nproc"], d["loadavg"]).run()
        assert signals == []

    async def test_warning_signal(self):
        d = NPROC_AND_LOAD_WARNING
        signals = await self._make(d["nproc"], d["loadavg"]).run()
        assert len(signals) >= 1
        assert signals[0].severity == "warning"
        assert signals[0].problem_type == "high_load"

    async def test_critical_signal(self):
        d = NPROC_AND_LOAD_CRITICAL
        signals = await self._make(d["nproc"], d["loadavg"]).run()
        sev = [s.severity for s in signals]
        assert "critical" in sev

    async def test_check_name(self):
        d = NPROC_AND_LOAD_NORMAL
        assert self._make(d["nproc"], d["loadavg"]).name == "load_average"
```

- [ ] **Step 3: Write tests for DiskInodeCheck**

Create `tests/checks/test_inode.py`:

```python
"""Tests for DiskInodeCheck."""

from app.checks.inode import DiskInodeCheck
from tests.checks.conftest import MockTool

DF_INODE_NORMAL = """\
Filesystem     IUse% Mounted on
/dev/sda1        15% /
/dev/sda2        30% /var
"""

DF_INODE_WARNING = """\
Filesystem     IUse% Mounted on
/dev/sda1        90% /
"""

DF_INODE_CRITICAL = """\
Filesystem     IUse% Mounted on
/dev/sda1        98% /
"""


class TestDiskInodeCheck:
    def _make(self, output, config=None):
        cfg = config or {"threshold_warning": 85, "threshold_critical": 95, "paths": ["/"]}
        return DiskInodeCheck(host="web-01", config=cfg, tools=[MockTool("ssh_exec", output)])

    async def test_normal_no_signals(self):
        signals = await self._make(DF_INODE_NORMAL).run()
        assert signals == []

    async def test_warning_signal(self):
        signals = await self._make(DF_INODE_WARNING).run()
        assert len(signals) == 1
        assert signals[0].severity == "warning"
        assert signals[0].problem_type == "inode_exhaustion"

    async def test_critical_signal(self):
        signals = await self._make(DF_INODE_CRITICAL).run()
        assert signals[0].severity == "critical"

    async def test_check_name(self):
        assert self._make(DF_INODE_NORMAL).name == "disk_inode"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/checks/test_memory.py tests/checks/test_load.py tests/checks/test_inode.py -v`
Expected: FAIL — ImportError (modules don't exist yet)

- [ ] **Step 5: Implement MemoryUsageCheck**

Create `app/checks/memory.py`:

```python
"""Memory usage check — monitors RAM and swap via /proc/meminfo."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class MemoryUsageCheck(Check):
    """Check memory usage by parsing /proc/meminfo.

    Config keys:
        threshold_warning  — RAM usage percentage (default 85)
        threshold_critical — RAM usage percentage (default 95)
    """

    name = "memory_usage"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "cat /proc/meminfo"})

        values = {}
        for line in output.splitlines():
            match = re.match(r"(\w+):\s+(\d+)", line)
            if match:
                values[match.group(1)] = int(match.group(2))

        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        if not total:
            return []

        usage_pct = round((total - available) / total * 100, 1)
        threshold_warn = self.config.get("threshold_warning", 85)
        threshold_crit = self.config.get("threshold_critical", 95)

        signals: list[Signal] = []

        if usage_pct >= threshold_crit:
            signals.append(Signal(
                host=self.host, severity="critical", problem_type="high_memory",
                evidence=f"RAM usage {usage_pct}% (critical threshold: {threshold_crit}%)",
                raw_data={"usage_pct": usage_pct, "total_kb": total, "available_kb": available},
            ))
        elif usage_pct >= threshold_warn:
            signals.append(Signal(
                host=self.host, severity="warning", problem_type="high_memory",
                evidence=f"RAM usage {usage_pct}% (warning threshold: {threshold_warn}%)",
                raw_data={"usage_pct": usage_pct, "total_kb": total, "available_kb": available},
            ))

        # Swap check
        swap_total = values.get("SwapTotal", 0)
        swap_free = values.get("SwapFree", 0)
        if swap_total > 0:
            swap_pct = round((swap_total - swap_free) / swap_total * 100, 1)
            if swap_pct >= 80:
                signals.append(Signal(
                    host=self.host, severity="warning", problem_type="high_swap",
                    evidence=f"Swap usage {swap_pct}% ({swap_total - swap_free} / {swap_total} kB)",
                    raw_data={"swap_pct": swap_pct},
                ))

        return signals
```

- [ ] **Step 6: Implement LoadAverageCheck**

Create `app/checks/load.py`:

```python
"""Load average check — monitors system load vs CPU count."""

from __future__ import annotations

from app.checks.base import Check, Signal


class LoadAverageCheck(Check):
    """Check load average against CPU count.

    Config keys:
        multiplier_warning  — load/cpu ratio for warning (default 1.5)
        multiplier_critical — load/cpu ratio for critical (default 3.0)
    """

    name = "load_average"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")

        nproc_out = await ssh.ainvoke({"command": "nproc"})
        load_out = await ssh.ainvoke({"command": "cat /proc/loadavg"})

        try:
            cpu_count = int(nproc_out.strip())
        except ValueError:
            return []

        parts = load_out.strip().split()
        if not parts:
            return []

        try:
            load_1 = float(parts[0])
        except (ValueError, IndexError):
            return []

        warn_mult = self.config.get("multiplier_warning", 1.5)
        crit_mult = self.config.get("multiplier_critical", 3.0)

        signals: list[Signal] = []

        if load_1 >= cpu_count * crit_mult:
            signals.append(Signal(
                host=self.host, severity="critical", problem_type="high_load",
                evidence=f"Load average {load_1} (CPUs: {cpu_count}, critical: {cpu_count * crit_mult})",
                raw_data={"load_1": load_1, "cpu_count": cpu_count},
            ))
        elif load_1 >= cpu_count * warn_mult:
            signals.append(Signal(
                host=self.host, severity="warning", problem_type="high_load",
                evidence=f"Load average {load_1} (CPUs: {cpu_count}, warning: {cpu_count * warn_mult})",
                raw_data={"load_1": load_1, "cpu_count": cpu_count},
            ))

        return signals
```

- [ ] **Step 7: Implement DiskInodeCheck**

Create `app/checks/inode.py`:

```python
"""Disk inode check — monitors inode usage via df -i."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class DiskInodeCheck(Check):
    """Check inode usage on configured mount points.

    Config keys:
        threshold_warning  — percentage (default 85)
        threshold_critical — percentage (default 95)
        paths              — list of mount points (default ["/"])
    """

    name = "disk_inode"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "df -i --output=source,ipcent,target"})

        threshold_warn = self.config.get("threshold_warning", 85)
        threshold_crit = self.config.get("threshold_critical", 95)
        paths = self.config.get("paths", ["/"])

        signals: list[Signal] = []

        for line in output.strip().splitlines():
            if "Filesystem" in line or "IUse%" in line:
                continue
            match = re.search(r"(\d+)%\s+(\S+)", line)
            if not match:
                continue

            pcent = int(match.group(1))
            mount = match.group(2)

            if mount not in paths:
                continue

            if pcent >= threshold_crit:
                signals.append(Signal(
                    host=self.host, severity="critical", problem_type="inode_exhaustion",
                    evidence=f"{mount} inodes {pcent}% used (critical: {threshold_crit}%)",
                    raw_data={"pcent": pcent, "mount": mount},
                ))
            elif pcent >= threshold_warn:
                signals.append(Signal(
                    host=self.host, severity="warning", problem_type="inode_exhaustion",
                    evidence=f"{mount} inodes {pcent}% used (warning: {threshold_warn}%)",
                    raw_data={"pcent": pcent, "mount": mount},
                ))

        return signals
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/checks/test_memory.py tests/checks/test_load.py tests/checks/test_inode.py -v`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add app/checks/memory.py app/checks/load.py app/checks/inode.py \
       tests/checks/test_memory.py tests/checks/test_load.py tests/checks/test_inode.py
git commit -m "feat: add memory_usage, load_average, disk_inode checks"
```

---

### Task 2: Checks — ssl_certificate, failed_units, zombies, open_ports

**Files:**
- Create: `app/checks/ssl.py`, `app/checks/failed_units.py`, `app/checks/zombies.py`, `app/checks/ports.py`
- Create: `tests/checks/test_ssl.py`, `tests/checks/test_failed_units.py`, `tests/checks/test_zombies.py`, `tests/checks/test_ports.py`

- [ ] **Step 1: Write tests for SslCertificateCheck**

Create `tests/checks/test_ssl.py`:

```python
"""Tests for SslCertificateCheck."""

from app.checks.ssl import SslCertificateCheck
from tests.checks.conftest import DynamicMockTool


class TestSslCertificateCheck:
    def _make(self, response, config=None):
        cfg = config or {"warning_days": 14, "critical_days": 3, "vhosts": ["example.com"]}
        tool = DynamicMockTool("ssh_exec", {"openssl": response})
        return SslCertificateCheck(host="web-01", config=cfg, tools=[tool])

    async def test_valid_cert_no_signal(self):
        signals = await self._make("notAfter=Dec 31 23:59:59 2027 GMT").run()
        assert signals == []

    async def test_expiring_soon_warning(self):
        # Use a date ~10 days in future (test may need adjustment)
        from datetime import datetime, timedelta, timezone
        future = datetime.now(timezone.utc) + timedelta(days=10)
        date_str = future.strftime("notAfter=%b %d %H:%M:%S %Y GMT")
        signals = await self._make(date_str).run()
        assert len(signals) == 1
        assert signals[0].severity == "warning"
        assert signals[0].problem_type == "ssl_expiring"

    async def test_expiring_critical(self):
        from datetime import datetime, timedelta, timezone
        future = datetime.now(timezone.utc) + timedelta(days=2)
        date_str = future.strftime("notAfter=%b %d %H:%M:%S %Y GMT")
        signals = await self._make(date_str).run()
        assert signals[0].severity == "critical"

    async def test_check_name(self):
        assert self._make("notAfter=Dec 31 23:59:59 2027 GMT").name == "ssl_certificate"
```

- [ ] **Step 2: Write tests for FailedUnitsCheck**

Create `tests/checks/test_failed_units.py`:

```python
"""Tests for FailedUnitsCheck."""

from app.checks.failed_units import FailedUnitsCheck
from tests.checks.conftest import MockTool

SYSTEMCTL_NO_FAILED = ""
SYSTEMCTL_FAILED = """\
  snapd.socket      loaded failed failed  Socket activation for snappy daemon
  ufw.service       loaded failed failed  Uncomplicated firewall
"""


class TestFailedUnitsCheck:
    def _make(self, output):
        return FailedUnitsCheck(host="web-01", config={}, tools=[MockTool("ssh_exec", output)])

    async def test_no_failed_units(self):
        signals = await self._make(SYSTEMCTL_NO_FAILED).run()
        assert signals == []

    async def test_failed_units_produce_signals(self):
        signals = await self._make(SYSTEMCTL_FAILED).run()
        assert len(signals) == 2
        assert all(s.severity == "warning" for s in signals)
        assert all(s.problem_type == "systemd_unit_failed" for s in signals)

    async def test_check_name(self):
        assert self._make("").name == "systemd_failed"
```

- [ ] **Step 3: Write tests for ZombieProcessCheck**

Create `tests/checks/test_zombies.py`:

```python
"""Tests for ZombieProcessCheck."""

from app.checks.zombies import ZombieProcessCheck
from tests.checks.conftest import MockTool

NO_ZOMBIES = ""
SOME_ZOMBIES = """\
root      1234  0.0  0.0      0     0 ?        Z    10:00   0:00 [defunct]
root      1235  0.0  0.0      0     0 ?        Z    10:01   0:00 [defunct]
root      1236  0.0  0.0      0     0 ?        Z    10:02   0:00 [defunct]
root      1237  0.0  0.0      0     0 ?        Z    10:03   0:00 [defunct]
root      1238  0.0  0.0      0     0 ?        Z    10:04   0:00 [defunct]
root      1239  0.0  0.0      0     0 ?        Z    10:05   0:00 [defunct]
"""


class TestZombieProcessCheck:
    def _make(self, output, config=None):
        cfg = config or {"threshold": 5}
        return ZombieProcessCheck(host="web-01", config=cfg, tools=[MockTool("ssh_exec", output)])

    async def test_no_zombies(self):
        signals = await self._make(NO_ZOMBIES).run()
        assert signals == []

    async def test_above_threshold(self):
        signals = await self._make(SOME_ZOMBIES).run()
        assert len(signals) == 1
        assert signals[0].severity == "warning"
        assert signals[0].problem_type == "zombie_processes"

    async def test_below_threshold(self):
        signals = await self._make(SOME_ZOMBIES, config={"threshold": 10}).run()
        assert signals == []
```

- [ ] **Step 4: Write tests for OpenPortsCheck**

Create `tests/checks/test_ports.py`:

```python
"""Tests for OpenPortsCheck."""

from app.checks.ports import OpenPortsCheck
from tests.checks.conftest import MockTool

SS_OUTPUT = """\
State    Recv-Q   Send-Q   Local Address:Port   Peer Address:Port  Process
LISTEN   0        128      0.0.0.0:22            0.0.0.0:*
LISTEN   0        128      0.0.0.0:80            0.0.0.0:*
LISTEN   0        128      0.0.0.0:443           0.0.0.0:*
LISTEN   0        80       0.0.0.0:3306          0.0.0.0:*
LISTEN   0        128      0.0.0.0:9090          0.0.0.0:*
"""


class TestOpenPortsCheck:
    def _make(self, output, config=None):
        cfg = config or {"expected_ports": [22, 80, 443, 3306]}
        return OpenPortsCheck(host="web-01", config=cfg, tools=[MockTool("ssh_exec", output)])

    async def test_all_expected_no_signal(self):
        normal = "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\nLISTEN 0 128 0.0.0.0:80 0.0.0.0:*\n"
        signals = await self._make(normal).run()
        assert signals == []

    async def test_unexpected_port_signal(self):
        signals = await self._make(SS_OUTPUT).run()
        assert len(signals) == 1
        assert signals[0].problem_type == "unexpected_port"
        assert "9090" in signals[0].evidence

    async def test_check_name(self):
        assert self._make(SS_OUTPUT).name == "open_ports"
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `python -m pytest tests/checks/test_ssl.py tests/checks/test_failed_units.py tests/checks/test_zombies.py tests/checks/test_ports.py -v`
Expected: FAIL — ImportError

- [ ] **Step 6: Implement all four checks**

Create `app/checks/ssl.py`:

```python
"""SSL certificate expiry check."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.checks.base import Check, Signal


class SslCertificateCheck(Check):
    """Check SSL certificate expiry dates.

    Config keys:
        warning_days  — days before expiry for warning (default 14)
        critical_days — days before expiry for critical (default 3)
        vhosts        — list of server names to check (default ["localhost"])
    """

    name = "ssl_certificate"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        vhosts = self.config.get("vhosts", ["localhost"])
        warn_days = self.config.get("warning_days", 14)
        crit_days = self.config.get("critical_days", 3)
        signals: list[Signal] = []

        for vhost in vhosts:
            cmd = (
                f'echo | openssl s_client -connect {vhost}:443 '
                f'-servername {vhost} 2>/dev/null | openssl x509 -noout -enddate'
            )
            output = await ssh.ainvoke({"command": cmd})
            match = re.search(r"notAfter=(.+)", output)
            if not match:
                continue

            try:
                expiry = datetime.strptime(match.group(1).strip(), "%b %d %H:%M:%S %Y %Z")
                expiry = expiry.replace(tzinfo=timezone.utc)
                days_left = (expiry - datetime.now(timezone.utc)).days
            except ValueError:
                continue

            if days_left <= crit_days:
                signals.append(Signal(
                    host=self.host, severity="critical", problem_type="ssl_expiring",
                    evidence=f"SSL cert for {vhost} expires in {days_left} days",
                    raw_data={"vhost": vhost, "days_left": days_left},
                ))
            elif days_left <= warn_days:
                signals.append(Signal(
                    host=self.host, severity="warning", problem_type="ssl_expiring",
                    evidence=f"SSL cert for {vhost} expires in {days_left} days",
                    raw_data={"vhost": vhost, "days_left": days_left},
                ))

        return signals
```

Create `app/checks/failed_units.py`:

```python
"""Failed systemd units check."""

from __future__ import annotations

from app.checks.base import Check, Signal


class FailedUnitsCheck(Check):
    """Check for any failed systemd units.

    No config keys — scans all units.
    """

    name = "systemd_failed"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "systemctl --failed --no-legend --plain"})

        signals: list[Signal] = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            unit = line.split()[0] if line.split() else line
            signals.append(Signal(
                host=self.host, severity="warning", problem_type="systemd_unit_failed",
                evidence=f"Systemd unit {unit} is in failed state",
                raw_data={"unit": unit, "line": line},
            ))

        return signals
```

Create `app/checks/zombies.py`:

```python
"""Zombie process check."""

from __future__ import annotations

from app.checks.base import Check, Signal


class ZombieProcessCheck(Check):
    """Check for zombie processes.

    Config keys:
        threshold — number of zombies before signaling (default 5)
    """

    name = "zombie_processes"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "ps aux --no-headers | awk '$8 ~ /^Z/ {print $0}'"})

        zombies = [l for l in output.strip().splitlines() if l.strip()]
        threshold = self.config.get("threshold", 5)

        if len(zombies) > threshold:
            return [Signal(
                host=self.host, severity="warning", problem_type="zombie_processes",
                evidence=f"{len(zombies)} zombie processes found (threshold: {threshold})",
                raw_data={"count": len(zombies), "sample": zombies[:5]},
            )]

        return []
```

Create `app/checks/ports.py`:

```python
"""Open ports check — detects unexpected listening ports."""

from __future__ import annotations

import re

from app.checks.base import Check, Signal


class OpenPortsCheck(Check):
    """Check for unexpected open ports.

    Config keys:
        expected_ports — list of port numbers considered normal
    """

    name = "open_ports"

    async def run(self) -> list[Signal]:
        ssh = self._get_tool("ssh_exec")
        output = await ssh.ainvoke({"command": "ss -tlnp"})

        expected = set(self.config.get("expected_ports", []))
        unexpected: list[int] = []

        for line in output.strip().splitlines():
            match = re.search(r":(\d+)\s", line)
            if match:
                port = int(match.group(1))
                if port not in expected:
                    unexpected.append(port)

        signals: list[Signal] = []
        # Deduplicate
        for port in sorted(set(unexpected)):
            signals.append(Signal(
                host=self.host, severity="info", problem_type="unexpected_port",
                evidence=f"Unexpected open port {port}",
                raw_data={"port": port},
            ))

        return signals
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/checks/test_ssl.py tests/checks/test_failed_units.py tests/checks/test_zombies.py tests/checks/test_ports.py -v`
Expected: all pass

- [ ] **Step 8: Register all 7 new checks in __init__.py**

In `app/checks/__init__.py`, add imports and registry entries for all 7 new checks:

```python
from app.checks.failed_units import FailedUnitsCheck
from app.checks.inode import DiskInodeCheck
from app.checks.load import LoadAverageCheck
from app.checks.memory import MemoryUsageCheck
from app.checks.ports import OpenPortsCheck
from app.checks.ssl import SslCertificateCheck
from app.checks.zombies import ZombieProcessCheck
```

Add to `CHECK_REGISTRY`:

```python
    "memory_usage": MemoryUsageCheck,
    "load_average": LoadAverageCheck,
    "disk_inode": DiskInodeCheck,
    "ssl_certificate": SslCertificateCheck,
    "systemd_failed": FailedUnitsCheck,
    "zombie_processes": ZombieProcessCheck,
    "open_ports": OpenPortsCheck,
```

- [ ] **Step 9: Run all check tests**

Run: `python -m pytest tests/checks/ -v`
Expected: all pass

- [ ] **Step 10: Commit**

```bash
git add app/checks/ tests/checks/
git commit -m "feat: add ssl, failed_units, zombie, open_ports checks + register all 7"
```

---

### Task 3: Runbooks — 5 safe (read-only)

**Files:**
- Create: `app/runbooks/show_top_processes.py`, `show_connections.py`, `show_disk_usage.py`, `mysql_processlist.py`, `check_backup.py`
- Create: corresponding test files in `tests/runbooks/`

- [ ] **Step 1: Write tests for all 5 safe runbooks**

Create `tests/runbooks/test_show_top_processes.py`:

```python
"""Tests for ShowTopProcessesRunbook."""

import pytest
from app.runbooks.show_top_processes import ShowTopProcessesRunbook

PS_OUTPUT = "USER PID %CPU %MEM VSZ RSS\nroot 1 0.0 0.1 1000 500\nmysql 200 5.0 30.0 8000 6000\n"


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_show_top_processes():
    rb = ShowTopProcessesRunbook(tools=[MockTool("ssh_exec", PS_OUTPUT)])
    result = await rb.execute({"count": 10})
    assert result.success is True
    assert "mysql" in result.details


async def test_default_count():
    rb = ShowTopProcessesRunbook(tools=[MockTool("ssh_exec", PS_OUTPUT)])
    result = await rb.execute({})
    assert result.success is True
```

Create `tests/runbooks/test_show_connections.py`:

```python
"""Tests for ShowConnectionsRunbook."""

from app.runbooks.show_connections import ShowConnectionsRunbook

SS_OUTPUT = "State  Recv-Q Send-Q  Local:Port  Peer:Port\nESTAB  0      0      10.0.0.1:443  192.168.1.1:50000\n"


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_show_connections():
    rb = ShowConnectionsRunbook(tools=[MockTool("ssh_exec", SS_OUTPUT)])
    result = await rb.execute({"count": 50})
    assert result.success is True
    assert "ESTAB" in result.details
```

Create `tests/runbooks/test_show_disk_usage.py`:

```python
"""Tests for ShowDiskUsageRunbook."""

from app.runbooks.show_disk_usage import ShowDiskUsageRunbook

DU_OUTPUT = "5.0G\t/var\n2.0G\t/usr\n1.0G\t/home\n"


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_show_disk_usage():
    rb = ShowDiskUsageRunbook(tools=[MockTool("ssh_exec", DU_OUTPUT)])
    result = await rb.execute({"path": "/", "count": 20})
    assert result.success is True
    assert "/var" in result.details
```

Create `tests/runbooks/test_mysql_processlist.py`:

```python
"""Tests for MysqlProcesslistRunbook."""

from app.runbooks.mysql_processlist import MysqlProcesslistRunbook

PL_OUTPUT = "Id\tUser\tHost\tdb\tCommand\tTime\tState\tInfo\n1\troot\tlocalhost\tNULL\tSleep\t100\t\tNULL\n"


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_mysql_processlist():
    rb = MysqlProcesslistRunbook(tools=[MockTool("ssh_mysql_exec", PL_OUTPUT)])
    result = await rb.execute({})
    assert result.success is True
    assert "root" in result.details
```

Create `tests/runbooks/test_check_backup.py`:

```python
"""Tests for CheckBackupRunbook."""

from app.runbooks.check_backup import CheckBackupRunbook

FIND_OUTPUT = "/backups/db-2026-04-03.sql.gz\n/backups/db-2026-04-02.sql.gz\n"
FIND_EMPTY = ""


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_backup_found():
    rb = CheckBackupRunbook(tools=[MockTool("ssh_exec", FIND_OUTPUT)])
    result = await rb.execute({"backup_path": "/backups"})
    assert result.success is True
    assert "2026-04-03" in result.details


async def test_no_backup():
    rb = CheckBackupRunbook(tools=[MockTool("ssh_exec", FIND_EMPTY)])
    result = await rb.execute({"backup_path": "/backups"})
    assert result.success is False


async def test_missing_param():
    rb = CheckBackupRunbook(tools=[MockTool("ssh_exec", "")])
    result = await rb.execute({})
    assert result.success is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runbooks/test_show_top_processes.py tests/runbooks/test_show_connections.py tests/runbooks/test_show_disk_usage.py tests/runbooks/test_mysql_processlist.py tests/runbooks/test_check_backup.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement all 5 safe runbooks**

Create `app/runbooks/show_top_processes.py`:

```python
"""Runbook: show top processes by memory usage."""

from app.runbooks.base import Runbook, RunbookResult


class ShowTopProcessesRunbook(Runbook):
    name = "show_top_processes"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")
        count = params.get("count", 20)
        output = await tool.ainvoke({"command": f"ps aux --sort=-rss | head -n {count + 1}"})
        return RunbookResult(success=True, message=f"Top {count} processes by RAM", details=output)
```

Create `app/runbooks/show_connections.py`:

```python
"""Runbook: show active network connections."""

from app.runbooks.base import Runbook, RunbookResult


class ShowConnectionsRunbook(Runbook):
    name = "show_connections"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")
        count = params.get("count", 50)
        output = await tool.ainvoke({"command": f"ss -tnp | head -n {count + 1}"})
        return RunbookResult(success=True, message=f"Active connections (top {count})", details=output)
```

Create `app/runbooks/show_disk_usage.py`:

```python
"""Runbook: show disk usage by directory."""

from app.runbooks.base import Runbook, RunbookResult


class ShowDiskUsageRunbook(Runbook):
    name = "show_disk_usage"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")
        path = params.get("path", "/")
        count = params.get("count", 20)
        output = await tool.ainvoke({"command": f"du -sh {path}/* 2>/dev/null | sort -rh | head -n {count}"})
        return RunbookResult(success=True, message=f"Disk usage in {path}", details=output)
```

Create `app/runbooks/mysql_processlist.py`:

```python
"""Runbook: show MySQL process list."""

from app.runbooks.base import Runbook, RunbookResult


class MysqlProcesslistRunbook(Runbook):
    name = "mysql_processlist"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_mysql_exec")
        output = await tool.ainvoke({"query": "SHOW FULL PROCESSLIST"})
        return RunbookResult(success=True, message="MySQL PROCESSLIST", details=output)
```

Create `app/runbooks/check_backup.py`:

```python
"""Runbook: check for recent backups."""

from app.runbooks.base import Runbook, RunbookResult


class CheckBackupRunbook(Runbook):
    name = "check_backup"
    is_dangerous = False

    async def execute(self, params: dict) -> RunbookResult:
        backup_path = params.get("backup_path")
        if not backup_path:
            return RunbookResult(success=False, message="Параметр 'backup_path' не указан")

        tool = self._get_tool("ssh_exec")
        output = await tool.ainvoke(
            {"command": f"find {backup_path} -maxdepth 1 -type f -mtime -1 | head -10"}
        )

        files = [l for l in output.strip().splitlines() if l.strip()]
        if files:
            return RunbookResult(
                success=True,
                message=f"Найдено {len(files)} свежих файлов в {backup_path}",
                details=output,
            )
        return RunbookResult(
            success=False,
            message=f"Свежих бэкапов не найдено в {backup_path} (за последние 24ч)",
        )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/runbooks/test_show_top_processes.py tests/runbooks/test_show_connections.py tests/runbooks/test_show_disk_usage.py tests/runbooks/test_mysql_processlist.py tests/runbooks/test_check_backup.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/runbooks/show_top_processes.py app/runbooks/show_connections.py \
       app/runbooks/show_disk_usage.py app/runbooks/mysql_processlist.py \
       app/runbooks/check_backup.py tests/runbooks/
git commit -m "feat: add 5 safe runbooks (top procs, connections, disk usage, mysql, backup)"
```

---

### Task 4: Runbooks — 3 dangerous + register all

**Files:**
- Create: `app/runbooks/rotate_logs.py`, `app/runbooks/kill_process.py`, `app/runbooks/free_memory.py`
- Create: corresponding test files
- Modify: `app/runbooks/__init__.py`

- [ ] **Step 1: Write tests for 3 dangerous runbooks**

Create `tests/runbooks/test_rotate_logs.py`:

```python
"""Tests for RotateLogsRunbook."""

from app.runbooks.rotate_logs import RotateLogsRunbook


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_rotate_logs():
    rb = RotateLogsRunbook(tools=[MockTool("ssh_exec", "rotating /var/log/apache2/access.log")])
    result = await rb.execute({"config": "apache2"})
    assert result.success is True


async def test_missing_config():
    rb = RotateLogsRunbook(tools=[MockTool("ssh_exec", "")])
    result = await rb.execute({})
    assert result.success is False


async def test_is_dangerous():
    rb = RotateLogsRunbook(tools=[MockTool("ssh_exec", "")])
    assert rb.is_dangerous is True
```

Create `tests/runbooks/test_kill_process.py`:

```python
"""Tests for KillProcessRunbook."""

from app.runbooks.kill_process import KillProcessRunbook


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_kill_process():
    rb = KillProcessRunbook(tools=[MockTool("ssh_exec", "")])
    result = await rb.execute({"pid": 1234})
    assert result.success is True


async def test_kill_with_signal():
    rb = KillProcessRunbook(tools=[MockTool("ssh_exec", "")])
    result = await rb.execute({"pid": 1234, "signal": 9})
    assert result.success is True


async def test_missing_pid():
    rb = KillProcessRunbook(tools=[MockTool("ssh_exec", "")])
    result = await rb.execute({})
    assert result.success is False


async def test_is_dangerous():
    rb = KillProcessRunbook(tools=[MockTool("ssh_exec", "")])
    assert rb.is_dangerous is True
```

Create `tests/runbooks/test_free_memory.py`:

```python
"""Tests for FreeMemoryRunbook."""

from app.runbooks.free_memory import FreeMemoryRunbook


class MockTool:
    def __init__(self, name, response):
        self.name = name
        self._response = response

    async def ainvoke(self, params):
        return self._response


async def test_free_memory():
    rb = FreeMemoryRunbook(tools=[MockTool("ssh_exec", "")])
    result = await rb.execute({})
    assert result.success is True


async def test_is_dangerous():
    rb = FreeMemoryRunbook(tools=[MockTool("ssh_exec", "")])
    assert rb.is_dangerous is True
```

- [ ] **Step 2: Implement 3 dangerous runbooks**

Create `app/runbooks/rotate_logs.py`:

```python
"""Runbook: force log rotation."""

from app.runbooks.base import Runbook, RunbookResult


class RotateLogsRunbook(Runbook):
    name = "rotate_logs"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        config = params.get("config")
        if not config:
            return RunbookResult(success=False, message="Параметр 'config' не указан")

        tool = self._get_tool("ssh_exec")
        output = await tool.ainvoke({"command": f"sudo logrotate -f /etc/logrotate.d/{config}"})
        return RunbookResult(success=True, message=f"Ротация логов {config} выполнена", details=output)
```

Create `app/runbooks/kill_process.py`:

```python
"""Runbook: kill a process by PID."""

from app.runbooks.base import Runbook, RunbookResult


class KillProcessRunbook(Runbook):
    name = "kill_process"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        pid = params.get("pid")
        if not pid:
            return RunbookResult(success=False, message="Параметр 'pid' не указан")

        signal = params.get("signal", 15)
        tool = self._get_tool("ssh_exec")
        output = await tool.ainvoke({"command": f"sudo kill -{signal} {pid}"})
        return RunbookResult(success=True, message=f"Отправлен сигнал {signal} процессу {pid}", details=output)
```

Create `app/runbooks/free_memory.py`:

```python
"""Runbook: free page cache memory."""

from app.runbooks.base import Runbook, RunbookResult


class FreeMemoryRunbook(Runbook):
    name = "free_memory"
    is_dangerous = True

    async def execute(self, params: dict) -> RunbookResult:
        tool = self._get_tool("ssh_exec")
        output = await tool.ainvoke({"command": "sudo sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'"})
        return RunbookResult(success=True, message="Page cache очищен", details=output)
```

- [ ] **Step 3: Register all 8 new runbooks**

In `app/runbooks/__init__.py`, add imports and registry entries:

```python
from app.runbooks.check_backup import CheckBackupRunbook
from app.runbooks.free_memory import FreeMemoryRunbook
from app.runbooks.kill_process import KillProcessRunbook
from app.runbooks.mysql_processlist import MysqlProcesslistRunbook
from app.runbooks.rotate_logs import RotateLogsRunbook
from app.runbooks.show_connections import ShowConnectionsRunbook
from app.runbooks.show_disk_usage import ShowDiskUsageRunbook
from app.runbooks.show_top_processes import ShowTopProcessesRunbook
```

Add to `RUNBOOK_REGISTRY`:

```python
    "show_top_processes": ShowTopProcessesRunbook,
    "show_connections": ShowConnectionsRunbook,
    "show_disk_usage": ShowDiskUsageRunbook,
    "mysql_processlist": MysqlProcesslistRunbook,
    "check_backup": CheckBackupRunbook,
    "rotate_logs": RotateLogsRunbook,
    "kill_process": KillProcessRunbook,
    "free_memory": FreeMemoryRunbook,
```

- [ ] **Step 4: Run all runbook tests**

Run: `python -m pytest tests/runbooks/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/runbooks/ tests/runbooks/
git commit -m "feat: add 3 dangerous runbooks (rotate_logs, kill_process, free_memory) + register all 8"
```

---

### Task 5: Update LLM prompts with all runbooks

**Files:**
- Modify: `app/agent/prompts.py`
- Modify: `app/agent/graphs/command.py` (CLASSIFY_PROMPT)

- [ ] **Step 1: Update NORMALIZE_PROMPT in prompts.py**

Replace the runbooks section in `app/agent/prompts.py` `NORMALIZE_PROMPT`:

```
Доступные runbooks:
- restart_service — params: {host, service}
- restart_replication — params: {host}
- clear_old_logs — params: {host, log_path, older_than_days}
- show_slow_queries — params: {host, lines, log_path} (safe, read-only)
- show_replication_status — params: {} (safe, read-only)
- show_top_processes — params: {count} (safe, read-only)
- show_connections — params: {count} (safe, read-only)
- show_disk_usage — params: {path, count} (safe, read-only)
- mysql_processlist — params: {} (safe, read-only)
- check_backup — params: {backup_path} (safe, read-only)
- rotate_logs — params: {config} (dangerous)
- kill_process — params: {pid, signal} (dangerous)
- free_memory — params: {} (dangerous)

Примечание: параметры SSH (ssh_user, ssh_port, ssh_key_content) добавляются автоматически — НЕ включай их в params.
```

- [ ] **Step 2: Update CLASSIFY_PROMPT in command.py**

Replace the runbook list in `CLASSIFY_PROMPT`:

```
- runbook: runbook name if write op (restart_service|restart_replication|clear_old_logs|rotate_logs|kill_process|free_memory) or null for read ops
- read_runbook: runbook name if safe read (show_slow_queries|show_replication_status|show_top_processes|show_connections|show_disk_usage|mysql_processlist|check_backup) or null
```

- [ ] **Step 3: Commit**

```bash
git add app/agent/prompts.py app/agent/graphs/command.py
git commit -m "feat: update LLM prompts with all 13 runbooks"
```

---

### Task 6: TG Commands — db_query intent + execute_db_query node

**Files:**
- Modify: `app/agent/graphs/command.py`
- Create: `tests/agent/test_db_query.py`

- [ ] **Step 1: Write tests for execute_db_query**

Create `tests/agent/test_db_query.py`:

```python
"""Tests for db_query functionality in command graph."""

import pytest
from sqlalchemy import select

from app.db.models import Incident, Server, CheckRun


@pytest.mark.asyncio
async def test_db_query_servers(db_session):
    from app.agent.graphs.command import execute_db_query_node, CommandState

    db_session.add(Server(name="web-01", host="1.2.3.4", enabled=True))
    db_session.add(Server(name="db-01", host="5.6.7.8", enabled=False))
    await db_session.flush()

    state = CommandState(message="какие серверы", intent="db_query")
    # We'll need to mock get_session — use monkeypatch
    # Mock get_session to return our test session
    from unittest.mock import patch, AsyncMock
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield db_session

    with patch("app.agent.graphs.command.get_session", mock_session):
        state.db_query_type = "servers"
        result = await execute_db_query_node(state)
        assert "web-01" in result["response"]
        assert "db-01" in result["response"]


@pytest.mark.asyncio
async def test_db_query_incidents(db_session):
    from app.agent.graphs.command import execute_db_query_node, CommandState

    server = Server(name="web-01", host="1.2.3.4")
    db_session.add(server)
    await db_session.flush()

    run = CheckRun(server_id=server.id, host="1.2.3.4", check_name="disk")
    db_session.add(run)
    await db_session.flush()

    inc = Incident(check_run_id=run.id, host="1.2.3.4", severity="critical",
                   problem_type="disk_full", evidence="/ at 95%", status="new")
    db_session.add(inc)
    await db_session.flush()

    from unittest.mock import patch
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_session():
        yield db_session

    with patch("app.agent.graphs.command.get_session", mock_session):
        state = CommandState(message="открытые инциденты", intent="db_query", db_query_type="incidents")
        result = await execute_db_query_node(state)
        assert "disk_full" in result["response"]
```

- [ ] **Step 2: Add db_query_type to CommandState**

In `app/agent/graphs/command.py`, update `CommandState`:

```python
@dataclass
class CommandState:
    message: str = ""
    host: str = ""
    intent: str = ""
    db_query_type: str = ""  # "servers" | "incidents" | "check_runs"
    tool_results: list[str] = field(default_factory=list)
    response: str = ""
    requires_confirm: bool = False
    pending_command: dict | None = None
```

- [ ] **Step 3: Update classify_intent to detect db_query**

In `classify_intent`, update CLASSIFY_PROMPT to include `db_query` intent and `db_query_type` field. In the result parsing, add:

```python
    if result["intent"] == "db_query":
        result["db_query_type"] = data.get("db_query_type", "servers")
```

- [ ] **Step 4: Implement execute_db_query_node**

Add new function in `app/agent/graphs/command.py`:

```python
async def execute_db_query_node(state: CommandState) -> dict:
    """Handle DB-only queries: server list, incidents, check runs."""
    from app.db.session import get_session
    from app.db.models import Server, Incident, CheckRun
    from sqlalchemy import select

    query_type = state.db_query_type or "servers"

    async with get_session() as session:
        if query_type == "servers":
            result = await session.execute(select(Server).order_by(Server.name))
            servers = result.scalars().all()
            if not servers:
                return {"response": "Нет добавленных серверов."}
            lines = ["<b>Серверы:</b>"]
            for s in servers:
                status = "✅" if s.enabled else "⏸"
                last = s.last_check_at.strftime("%d.%m %H:%M") if s.last_check_at else "—"
                lines.append(f"{status} <b>{s.name}</b> ({s.host}) — последняя проверка: {last}")
            return {"response": "\n".join(lines)}

        elif query_type == "incidents":
            result = await session.execute(
                select(Incident)
                .where(Incident.status.in_(["new", "notified"]))
                .order_by(Incident.created_at.desc())
                .limit(20)
            )
            incidents = result.scalars().all()
            if not incidents:
                return {"response": "Открытых инцидентов нет. 👍"}
            lines = [f"<b>Открытые инциденты ({len(incidents)}):</b>"]
            for inc in incidents:
                emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(inc.severity, "⚪")
                dt = inc.created_at.strftime("%d.%m %H:%M") if inc.created_at else ""
                lines.append(f"{emoji} [{inc.host}] {inc.problem_type} — {dt}")
            return {"response": "\n".join(lines)}

        elif query_type == "check_runs":
            result = await session.execute(
                select(CheckRun)
                .order_by(CheckRun.started_at.desc())
                .limit(10)
            )
            runs = result.scalars().all()
            if not runs:
                return {"response": "Проверок пока не было."}
            lines = ["<b>Последние проверки:</b>"]
            for r in runs:
                emoji = {"ok": "✅", "incident": "⚠️", "error": "❌", "running": "🔄"}.get(r.status, "❓")
                dt = r.started_at.strftime("%d.%m %H:%M") if r.started_at else ""
                lines.append(f"{emoji} [{r.host}] {r.check_name} — {r.status} ({dt})")
            return {"response": "\n".join(lines)}

    return {"response": "Неизвестный тип запроса."}
```

- [ ] **Step 5: Update routing**

Update `route_after_classify`:

```python
def route_after_classify(state: CommandState) -> Literal["execute_read", "confirm", "execute_db_query", "__end__"]:
    if state.intent == "db_query":
        return "execute_db_query"
    if state.intent == "write" and state.requires_confirm:
        return "confirm"
    if state.intent in ("read", "unknown"):
        return "execute_read"
    return END
```

Register the node in the graph:

```python
_builder.add_node("execute_db_query", execute_db_query_node)
_builder.add_edge("execute_db_query", END)
```

- [ ] **Step 6: Commit**

```bash
git add app/agent/graphs/command.py tests/agent/test_db_query.py
git commit -m "feat: add db_query intent for TG commands (servers, incidents, check_runs)"
```

---

### Task 7: TG Bot — response formatting + truncation

**Files:**
- Modify: `app/bot/handlers.py`

- [ ] **Step 1: Add response formatting**

In `app/bot/handlers.py`, update `handle_text_command` to format and truncate the response:

After `response_text = result.get("response") or "Команда обработана."`, add:

```python
        # Truncate long responses for Telegram (4096 char limit)
        MAX_LEN = 4000
        if len(response_text) > MAX_LEN:
            total = len(response_text)
            response_text = response_text[:MAX_LEN] + f"\n\n<i>...обрезано ({total} символов)</i>"

        await message.answer(response_text)
```

Also read TG_ALLOWED_USERS from SettingsService for hot-reload:

```python
    # Check allowed users (with DB fallback)
    from app.services.settings import SettingsService
    from app.config import settings as env_settings
    svc = SettingsService(secret_key=env_settings.secret_key)

    try:
        from app.db.session import get_session
        async with get_session() as session:
            app_settings = await svc.get_cached(session)
        allowed_raw = app_settings.get("tg_allowed_users") or settings.tg_allowed_users
    except Exception:
        allowed_raw = settings.tg_allowed_users

    allowed_ids = [int(uid.strip()) for uid in allowed_raw.split(",") if uid.strip()] if allowed_raw else []

    if message.from_user and allowed_ids and message.from_user.id not in allowed_ids:
        return
```

- [ ] **Step 2: Commit**

```bash
git add app/bot/handlers.py
git commit -m "feat: TG response truncation + read allowed_users from DB"
```

---

### Task 8: Integration smoke test

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all new + existing tests pass

- [ ] **Step 2: Verify import**

Run: `python -c "from app.main import app; print('ok')"`

- [ ] **Step 3: Verify registries**

Run:
```python
python -c "from app.checks import CHECK_REGISTRY; print(len(CHECK_REGISTRY), 'checks:', list(CHECK_REGISTRY.keys()))"
python -c "from app.runbooks import RUNBOOK_REGISTRY; print(len(RUNBOOK_REGISTRY), 'runbooks:', list(RUNBOOK_REGISTRY.keys()))"
```
Expected: 12 checks, 13 runbooks

- [ ] **Step 4: Build and restart Docker**

```bash
docker compose build app celery-worker
docker compose up -d
```

- [ ] **Step 5: Commit if anything remaining**

```bash
git add -A && git commit -m "feat: monitoring expansion complete — 7 checks, 8 runbooks, TG commands"
```
