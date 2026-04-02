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

    error = request.query_params.get("error")
    error_check = request.query_params.get("check_name", "")
    error_msg = ""
    if error == "unknown_check":
        error_msg = (
            f"Проверка «{error_check}» не найдена в реестре. "
            "Обновите страницу и попробуйте снова — ИИ предложит корректные имена."
        )
    elif error == "missing_fields":
        error_msg = "Выберите сервер перед применением."

    return templates.TemplateResponse(
        request,
        "recommendations.html",
        {
            "servers": servers,
            "days": days,
            "active_page": "recommendations",
            "error_msg": error_msg,
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
    import json as _json
    from app.services.recommendations import apply_recommendation

    form = await request.form()
    server_id_raw = form.get("server_id", "0")
    check_name = (form.get("check_name") or "").strip()
    params_raw = (form.get("params") or "{}").strip()

    try:
        server_id = int(server_id_raw)
    except (ValueError, TypeError):
        server_id = 0

    try:
        params = _json.loads(params_raw)
    except _json.JSONDecodeError:
        params = {}

    if not server_id or not check_name:
        return RedirectResponse("/recommendations?error=missing_fields", status_code=302)

    ok = await apply_recommendation(server_id, check_name, params)

    if ok:
        return RedirectResponse(f"/servers/{server_id}/checks?saved=1", status_code=302)
    else:
        # check_name not in registry or server not found — redirect back with error
        return RedirectResponse(
            f"/recommendations?error=unknown_check&check_name={check_name}",
            status_code=302,
        )
