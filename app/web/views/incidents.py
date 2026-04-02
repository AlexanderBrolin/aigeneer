"""Incidents views — filterable list and detail page."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.db.models import Incident
from app.db.session import get_session
from app.web.auth import login_required

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/incidents", response_class=HTMLResponse)
@login_required
async def incidents_list(request: Request):
    params = request.query_params

    host_filter = params.get("host", "")
    severity_filter = params.get("severity", "")
    status_filter = params.get("status", "")

    async with get_session() as session:
        rows = await session.execute(select(Incident.host).distinct())
        hosts = sorted([r[0] for r in rows.all()])

        query = select(Incident).order_by(Incident.created_at.desc())
        if host_filter:
            query = query.where(Incident.host == host_filter)
        if severity_filter:
            query = query.where(Incident.severity == severity_filter)
        if status_filter:
            query = query.where(Incident.status == status_filter)

        result = await session.execute(query.limit(200))
        incidents = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "incidents.html",
        {
            "incidents": incidents,
            "hosts": hosts,
            "filters": {
                "host": host_filter,
                "severity": severity_filter,
                "status": status_filter,
            },
            "active_page": "incidents",
        },
    )


@router.get("/incidents/{incident_id}", response_class=HTMLResponse)
@login_required
async def incident_detail(request: Request, incident_id: int):
    async with get_session() as session:
        incident = await session.get(Incident, incident_id)
        if not incident:
            return RedirectResponse("/incidents", status_code=302)

    return templates.TemplateResponse(
        request,
        "incident_detail.html",
        {"incident": incident, "active_page": "incidents"},
    )


@router.post("/incidents/{incident_id}/resolve")
@login_required
async def incident_resolve(request: Request, incident_id: int):
    async with get_session() as session:
        incident = await session.get(Incident, incident_id)
        if incident:
            from datetime import datetime
            incident.status = "resolved"
            incident.resolved_at = datetime.utcnow()

    return RedirectResponse(f"/incidents/{incident_id}", status_code=302)
