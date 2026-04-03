# Checks, Runbooks & TG Commands Expansion — Design Spec

**Date:** 2026-04-03
**Status:** Approved
**Epic:** opsagent-0j2

---

## Summary

Expand ops-agent with 7 new checks, 8 new runbooks, and interactive Telegram commands allowing admins to query servers and execute commands from chat.

## Scope

Three phases (A → B → C), each independent except C depends on B.

---

## Phase A: New Checks (opsagent-dza)

All checks follow the existing pattern: extend `Check(ABC)`, return `list[Signal]`, use `ssh_exec` tool. Register in `CHECK_REGISTRY`.

### A.1 — `memory_usage`

**File:** `app/checks/memory.py`
**Command:** `cat /proc/meminfo`
**Config:** `threshold_warning` (default 85), `threshold_critical` (default 95)
**Logic:** Parse MemTotal, MemAvailable → compute usage %. Also check swap usage. Signal per threshold breach.

### A.2 — `load_average`

**File:** `app/checks/load.py`
**Command:** `nproc && cat /proc/loadavg`
**Config:** `multiplier_warning` (default 1.5), `multiplier_critical` (default 3.0)
**Logic:** load_1min vs nproc * multiplier. Signal if exceeded.

### A.3 — `disk_inode`

**File:** `app/checks/inode.py`
**Command:** `df -i --output=source,ipcent,target`
**Config:** `threshold_warning` (default 85), `threshold_critical` (default 95), `paths` (default ["/"])
**Logic:** Same pattern as `disk_space` but for inodes.

### A.4 — `ssl_certificate`

**File:** `app/checks/ssl.py`
**Command:** `echo | openssl s_client -connect localhost:443 -servername <vhost> 2>/dev/null | openssl x509 -noout -enddate`
**Config:** `warning_days` (default 14), `critical_days` (default 3), `vhosts` (default ["localhost"])
**Logic:** Parse `notAfter=`, compute days until expiry. Signal per vhost.

### A.5 — `systemd_failed`

**File:** `app/checks/failed_units.py`
**Command:** `systemctl --failed --no-legend --plain`
**Config:** none
**Logic:** Each failed unit → warning signal. Zero failed → no signal.

### A.6 — `zombie_processes`

**File:** `app/checks/zombies.py`
**Command:** `ps aux --no-headers | awk '$8 ~ /^Z/ {print $0}'`
**Config:** `threshold` (default 5)
**Logic:** Count zombie lines. Signal if > threshold.

### A.7 — `open_ports`

**File:** `app/checks/ports.py`
**Command:** `ss -tlnp`
**Config:** `expected_ports` (list of int, e.g. [22, 80, 443, 3306])
**Logic:** Parse listening ports. Any port NOT in expected_ports → info signal. Reports unexpected open ports.

---

## Phase B: New Runbooks (opsagent-iex)

All runbooks follow the existing pattern: extend `Runbook(ABC)`, return `RunbookResult`, use `ssh_exec` tool. Register in `RUNBOOK_REGISTRY`.

### Safe (read-only)

| # | Name | Command | Params |
|---|------|---------|--------|
| B.1 | `show_top_processes` | `ps aux --sort=-rss \| head -N` | `count` (default 20) |
| B.2 | `show_connections` | `ss -tnp \| head -N` | `count` (default 50) |
| B.3 | `show_disk_usage` | `du -sh /* 2>/dev/null \| sort -rh \| head -N` | `count` (default 20), `path` (default "/") |
| B.4 | `mysql_processlist` | `mysql -e "SHOW FULL PROCESSLIST"` | none |
| B.5 | `check_backup` | `find <path> -maxdepth 1 -type f -mtime -1 \| head -5` | `backup_path` (required) |

### Dangerous (require confirmation)

| # | Name | Command | Params |
|---|------|---------|--------|
| B.6 | `rotate_logs` | `logrotate -f /etc/logrotate.d/<config>` | `config` (required, e.g. "apache2") |
| B.7 | `kill_process` | `kill -<signal> <pid>` | `pid` (required), `signal` (default 15) |
| B.8 | `free_memory` | `sync && echo 3 > /proc/sys/vm/drop_caches` | none (requires sudo) |

---

## Phase C: Interactive TG Commands (opsagent-p7m)

### Current state

`command_graph` (app/agent/graphs/command.py) already handles:
- Free-text → LLM classify → read or write intent
- Read: bind SSH tools to host, LLM executes tools, synthesizes response
- Write: interrupt for confirmation → resume → run runbook

`handle_text_command` in bot/handlers.py invokes the graph and sends response.

### What's missing

1. **DB queries** — "какие серверы?", "открытые инциденты?" — these don't need SSH, just DB reads
2. **Server name resolution** — user says "autotest2", graph needs to find the server by name
3. **Response formatting** — monospace for command output, truncation for long results
4. **New runbooks in classify prompt** — CLASSIFY_PROMPT lists only 4 runbooks, needs all 13

### Changes

#### C.1 — Extend `classify_intent` categories

Add new intent type: `"db_query"` for server list, incidents, check runs.

Updated CLASSIFY_PROMPT:
```
- intent: "read" | "write" | "db_query" | "unknown"
- db_query_type: "servers" | "incidents" | "check_runs" | null
```

#### C.2 — New node: `execute_db_query`

Handles `db_query` intent without SSH. Queries DB directly:
- `servers` → list enabled servers with name, host, last_check_at
- `incidents` → open incidents (new/notified) with host, severity, problem_type
- `check_runs` → last 10 check runs with status

Returns formatted text response.

#### C.3 — Update routing

```
classify → route:
  - "read"     → execute_read (SSH + LLM, as before)
  - "write"    → confirm → execute_write (runbook, as before)
  - "db_query" → execute_db_query (new node, DB only)
  - "unknown"  → execute_read (best effort)
```

#### C.4 — Response formatting in bot handler

After getting response from graph:
- If response > 4000 chars → truncate with "...(обрезано, полный вывод X символов)"
- Wrap command output in `<pre>` for Telegram monospace
- Keep HTML parse mode (already set in bot config)

#### C.5 — Update CLASSIFY_PROMPT with all runbooks

Add all 13 runbooks to the classification prompt so LLM knows what's available.

#### C.6 — Update NORMALIZE_PROMPT with all runbooks

Same — analysis graph needs to know about new runbooks for incident actions.

---

## What stays unchanged

- `app/checks/base.py`, `app/runbooks/base.py` — no changes
- `app/scheduler/tasks.py` — already iterates CHECK_REGISTRY dynamically
- `app/bot/callbacks.py` — already handles runbook execution dynamically
- `app/web/views/recommendations.py` — already reads CHECK_REGISTRY dynamically
- `app/agent/tool_provider.py` — no changes
- DB models — no changes (new checks/runbooks are code-only)
