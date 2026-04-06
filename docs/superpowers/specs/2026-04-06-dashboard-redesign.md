# Dashboard Redesign — Incident-Centric Monitoring

**Date:** 2026-04-06
**Status:** Approved

## Summary

Redesign the dashboard to be incident-centric with live polling, action buttons, and a server health grid. Inspired by AlertManager/PagerDuty UX.

## Decisions

- **Layout:** Incident Table + Health Grid (option A)
- **Refresh:** Polling every 30 seconds via fetch API
- **Actions:** Resolve + runbook buttons directly in the incident table
- **Tech:** Alpine.js for reactivity, Chart.js for timeline, Tailwind CSS

---

## 1. Layout Structure (top to bottom)

### 1.1 Severity Summary Bar

Four colored stat cards in a row:
- **Critical** (red) — count of open critical incidents
- **Warning** (yellow) — count of open warning incidents
- **Servers OK** (green) — count of servers with no open incidents
- **Checks 24h** (blue) — total check runs in last 24 hours

Cards update via polling. Large number, small label below.

### 1.2 Active Incidents Table (main block, ~60% height)

Header: "Active Incidents (N)" with "auto-refresh 30s" indicator.

Columns:
| Column | Content |
|--------|---------|
| Severity dot | Colored circle (red/yellow/blue), pulsing animation for critical |
| Host | Server name, bold |
| Type | problem_type |
| Description | evidence, truncated to ~80 chars |
| Time | Relative time ("2m ago", "1h ago") |
| Actions | "Resolve" button + runbook button if incident has dangerous_actions |

Sorting: critical first, then warning, then info. Within severity — newest first.

Row click → `/incidents/{id}` for full details.
Resolve button → `POST /api/dashboard/resolve/{id}` (AJAX, row removed from table).
Runbook button → `POST /api/dashboard/run-action/{id}/{action_idx}` (AJAX, shows result inline).

Only shows incidents with status in `["new", "notified"]` (active, not resolved/ignored).

### 1.3 Bottom Section (two columns)

**Left: Server Health Grid**
- Mini cards for each enabled server
- Color: green (0 issues), yellow (warnings only), red (has critical)
- Shows: server name + issue count
- Click → `/servers/{id}/checks`

**Right: Incidents Timeline**
- Bar chart, 7 days, color-coded by severity
- Chart.js (same library as current)
- Loaded once on page load (not polled)

### 1.4 Auto-refresh Indicator

Small text in top-right of page header: "Обновлено Xs назад" with countdown. Resets on each fetch cycle.

---

## 2. API Endpoints

### `GET /api/dashboard/live`

Single endpoint for polling. Returns:

```json
{
  "counters": {
    "critical": 3,
    "warning": 7,
    "servers_ok": 2,
    "servers_total": 4,
    "checks_24h": 142,
    "checks_ok": 128,
    "checks_error": 14
  },
  "incidents": [
    {
      "id": 42,
      "host": "autotest2.itscrm.ru",
      "severity": "critical",
      "problem_type": "disk_full",
      "evidence": "/ заполнен на 95%",
      "status": "notified",
      "created_at": "2026-04-06T12:01:00",
      "has_actions": true
    }
  ],
  "servers": [
    {
      "id": 3,
      "name": "autotest2.itscrm.ru",
      "status": "critical",
      "issue_count": 2
    }
  ]
}
```

Query: incidents with status in `["new", "notified"]`, ordered by severity (critical first) then `created_at desc`. Limit 50.

Servers: all enabled servers, with aggregated incident status (worst severity among open incidents) and count.

### `POST /api/dashboard/resolve/{incident_id}`

Marks incident as resolved. Returns `{"ok": true}`.

### `POST /api/dashboard/run-action/{incident_id}/{action_idx}`

Executes a dangerous_action runbook for the incident. Reads `actions_json` from incident DB record. Returns `{"ok": true, "success": true, "message": "...", "details": "..."}` or `{"ok": false, "error": "..."}`.

---

## 3. Frontend Implementation

### Alpine.js reactive data

```javascript
x-data="dashboardApp()" x-init="startPolling()"

dashboardApp() {
  return {
    counters: {},
    incidents: [],
    servers: [],
    lastUpdate: 0,
    secondsAgo: 0,
    
    async refresh() { /* fetch /api/dashboard/live */ },
    startPolling() { this.refresh(); setInterval(() => this.refresh(), 30000); },
    async resolve(id) { /* POST /api/dashboard/resolve/{id} */ },
    async runAction(id, idx) { /* POST /api/dashboard/run-action/{id}/{idx} */ },
    timeAgo(isoStr) { /* relative time formatting */ },
  }
}
```

### Template structure

Single Jinja2 template `dashboard.html` (replaces current). All dynamic content rendered by Alpine.js from `x-data`. Initial render shows loading state, first fetch populates data.

### Alerts banner

Config alerts (missing API key, SSH keys, TG token) remain at the top — rendered server-side by Jinja2, not polled.

---

## 4. Files Changed

- **Modify:** `app/web/templates/dashboard.html` — full rewrite of template
- **Modify:** `app/web/views/dashboard.py` — simplify server-side data (alerts only), add live endpoint
- **Modify:** `app/web/api.py` — add `/api/dashboard/live`, `/api/dashboard/resolve/{id}`, `/api/dashboard/run-action/{id}/{idx}`
- **No new files needed** — all changes in existing dashboard + API modules
