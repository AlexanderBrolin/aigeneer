"""AI recommendations view."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.db.models import Server
from app.db.session import get_session
from app.web.auth import login_required

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/recommendations", response_class=HTMLResponse)
@login_required
async def recommendations_page(request: Request):
    params = request.query_params
    days = int(params.get("days", 7))

    async with get_session() as session:
        result = await session.execute(select(Server).where(Server.enabled.is_(True)))
        servers = result.scalars().all()

    return templates.TemplateResponse(
        "recommendations.html",
        {
            "request": request,
            "servers": servers,
            "days": days,
            "active_page": "recommendations",
        },
    )


@router.get("/api/recommendations/generate")
@login_required
async def generate_recs_api(request: Request, days: int = 7):
    """Generate recommendations via LLM — called async from the UI."""
    from app.services.recommendations import generate_recommendations

    recs = await generate_recommendations(days=days)
    return {"recommendations": recs, "days": days}


@router.post("/recommendations/apply")
@login_required
async def apply_rec(request: Request):
    form = await request.form()
    server_id = int(form.get("server_id", 0))
    check_name = (form.get("check_name") or "").strip()
    params_raw = (form.get("params") or "{}").strip()

    import json
    try:
        params = json.loads(params_raw)
    except json.JSONDecodeError:
        params = {}

    from app.services.recommendations import apply_recommendation
    await apply_recommendation(server_id, check_name, params)

    return RedirectResponse(f"/servers/{server_id}/checks?saved=1", status_code=302)
