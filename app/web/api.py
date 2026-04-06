"""JSON API endpoints for chart data and live dashboard."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import case, func, select

from app.db.models import CheckRun, Incident, Server
from app.db.session import get_session
from app.web.auth import login_required

router = APIRouter(prefix="/api")


@router.get("/chart/incidents-timeline")
async def incidents_timeline():
    """Incidents per day for the last 7 days."""
    now = datetime.utcnow()
    labels = []
    values = []

    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        async with get_session() as session:
            count = (
                await session.execute(
                    select(func.count(Incident.id)).where(
                        Incident.created_at >= day_start,
                        Incident.created_at < day_end,
                    )
                )
            ).scalar() or 0

        labels.append(day_start.strftime("%d.%m"))
        values.append(count)

    return {"labels": labels, "values": values}


@router.get("/chart/incidents-severity")
async def incidents_severity():
    """Incidents by severity for the last 7 days."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    result = {"critical": 0, "warning": 0, "info": 0}

    async with get_session() as session:
        for severity in result:
            count = (
                await session.execute(
                    select(func.count(Incident.id)).where(
                        Incident.created_at >= week_ago,
                        Incident.severity == severity,
                    )
                )
            ).scalar() or 0
            result[severity] = count

    return {
        "labels": ["Critical", "Warning", "Info"],
        "values": [result["critical"], result["warning"], result["info"]],
    }


# ---------------------------------------------------------------------------
# Live dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard/live")
@login_required
async def dashboard_live(request: Request):
    """Single endpoint for dashboard polling — counters, incidents, servers."""
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)

    async with get_session() as session:
        # Counters
        critical = (await session.execute(
            select(func.count(Incident.id)).where(
                Incident.status.in_(["new", "notified"]), Incident.severity == "critical"
            )
        )).scalar() or 0

        warning = (await session.execute(
            select(func.count(Incident.id)).where(
                Incident.status.in_(["new", "notified"]), Incident.severity == "warning"
            )
        )).scalar() or 0

        servers_total = (await session.execute(
            select(func.count(Server.id)).where(Server.enabled.is_(True))
        )).scalar() or 0

        checks_24h = (await session.execute(
            select(func.count(CheckRun.id)).where(CheckRun.started_at >= day_ago)
        )).scalar() or 0

        checks_ok = (await session.execute(
            select(func.count(CheckRun.id)).where(
                CheckRun.started_at >= day_ago, CheckRun.status == "ok"
            )
        )).scalar() or 0

        checks_error = (await session.execute(
            select(func.count(CheckRun.id)).where(
                CheckRun.started_at >= day_ago, CheckRun.status == "error"
            )
        )).scalar() or 0

        # Active incidents
        inc_result = await session.execute(
            select(Incident)
            .where(Incident.status.in_(["new", "notified"]))
            .order_by(
                case(
                    (Incident.severity == "critical", 0),
                    (Incident.severity == "warning", 1),
                    else_=2,
                ),
                Incident.created_at.desc(),
            )
            .limit(50)
        )
        incidents_list = []
        for inc in inc_result.scalars().all():
            incidents_list.append({
                "id": inc.id,
                "host": inc.host,
                "severity": inc.severity,
                "problem_type": inc.problem_type,
                "evidence": inc.evidence[:120] if inc.evidence else "",
                "status": inc.status,
                "created_at": inc.created_at.isoformat() if inc.created_at else "",
                "has_actions": bool(inc.actions_json and inc.actions_json.get("dangerous_actions")),
            })

        # Server health: aggregate open incidents per server
        srv_result = await session.execute(
            select(Server).where(Server.enabled.is_(True)).order_by(Server.name)
        )
        servers_list = []
        server_ok_count = 0
        for srv in srv_result.scalars().all():
            # Count open incidents for this server
            srv_inc = await session.execute(
                select(
                    func.count(Incident.id),
                    func.max(case(
                        (Incident.severity == "critical", 2),
                        (Incident.severity == "warning", 1),
                        else_=0,
                    )),
                ).where(
                    Incident.host == srv.host,
                    Incident.status.in_(["new", "notified"]),
                )
            )
            row = srv_inc.one()
            issue_count = row[0] or 0
            worst = row[1] or 0

            if issue_count == 0:
                status = "ok"
                server_ok_count += 1
            elif worst >= 2:
                status = "critical"
            else:
                status = "warning"

            servers_list.append({
                "id": srv.id,
                "name": srv.name,
                "status": status,
                "issue_count": issue_count,
            })

    return {
        "counters": {
            "critical": critical,
            "warning": warning,
            "servers_ok": server_ok_count,
            "servers_total": servers_total,
            "checks_24h": checks_24h,
            "checks_ok": checks_ok,
            "checks_error": checks_error,
        },
        "incidents": incidents_list,
        "servers": servers_list,
    }


@router.post("/dashboard/resolve/{incident_id}")
@login_required
async def dashboard_resolve(request: Request, incident_id: int):
    """Resolve an incident from the dashboard."""
    from app.services.incident import update_incident_status

    await update_incident_status(incident_id, "resolved")
    return {"ok": True}


@router.post("/dashboard/run-action/{incident_id}/{action_idx}")
@login_required
async def dashboard_run_action(request: Request, incident_id: int, action_idx: int):
    """Execute a dangerous_action runbook for an incident."""
    from app.services.incident import get_incident, update_incident_status

    async with get_session() as session:
        from app.db.models import Incident as IncModel
        result = await session.execute(select(IncModel).where(IncModel.id == incident_id))
        inc = result.scalar_one_or_none()

        if not inc or not inc.actions_json:
            return {"ok": False, "error": "Incident not found or no actions"}

        actions = inc.actions_json.get("dangerous_actions", [])
        if action_idx >= len(actions):
            return {"ok": False, "error": "Action index out of range"}

        action = actions[action_idx]
        host_config = inc.actions_json.get("host_config", {})

    # Execute runbook
    from app.runbooks import run_runbook
    from app.agent.tool_provider import get_write_tools

    try:
        tools = get_write_tools(host_config) if host_config else []
        rb_result = await run_runbook(action.get("runbook", ""), action.get("params", {}), tools)
        await update_incident_status(incident_id, "actioned", action.get("runbook"))
        return {
            "ok": True,
            "success": rb_result.success,
            "message": rb_result.message,
            "details": (rb_result.details or "")[:2000],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
