"""Check runs history view."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.db.models import CheckRun
from app.db.session import get_session
from app.web.auth import login_required

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/check-runs", response_class=HTMLResponse)
@login_required
async def check_runs_list(request: Request):
    params = request.query_params
    host_filter = params.get("host", "")
    status_filter = params.get("status", "")

    async with get_session() as session:
        hosts_rows = await session.execute(select(CheckRun.host).distinct())
        hosts = sorted([r[0] for r in hosts_rows.all()])

        query = select(CheckRun).order_by(CheckRun.started_at.desc())
        if host_filter:
            query = query.where(CheckRun.host == host_filter)
        if status_filter:
            query = query.where(CheckRun.status == status_filter)

        result = await session.execute(query.limit(200))
        check_runs = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "check_runs.html",
        {
            "check_runs": check_runs,
            "hosts": hosts,
            "filters": {"host": host_filter, "status": status_filter},
            "active_page": "check_runs",
        },
    )
