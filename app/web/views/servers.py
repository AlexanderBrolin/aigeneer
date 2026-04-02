"""Server CRUD views — list, create, edit, delete, checks config."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.checks import CHECK_REGISTRY
from app.db.models import Server, ServerCheck
from app.db.session import get_session
from app.web.auth import login_required

router = APIRouter(prefix="/servers")
templates = Jinja2Templates(directory="app/web/templates")


@router.get("", response_class=HTMLResponse)
@login_required
async def servers_list(request: Request):
    async with get_session() as session:
        result = await session.execute(select(Server).order_by(Server.name))
        servers = result.scalars().all()

    return templates.TemplateResponse(
        request, "servers.html", {"servers": servers, "active_page": "servers"}
    )


@router.get("/create", response_class=HTMLResponse)
@login_required
async def server_create_form(request: Request):
    return templates.TemplateResponse(
        request,
        "server_edit.html",
        {
            "server": None,
            "active_page": "servers",
            "action": "/servers/create",
            "title": "Добавить сервер",
        },
    )


@router.post("/create")
@login_required
async def server_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    host = (form.get("host") or "").strip()

    if not name or not host:
        return templates.TemplateResponse(
            request,
            "server_edit.html",
            {
                "server": None,
                "active_page": "servers",
                "action": "/servers/create",
                "title": "Добавить сервер",
                "error": "Имя и хост обязательны",
            },
        )

    async with get_session() as session:
        server = Server(
            name=name,
            host=host,
            ssh_user=(form.get("ssh_user") or "deploy").strip(),
            ssh_key_path=(form.get("ssh_key_path") or "").strip() or None,
            ssh_password=(form.get("ssh_password") or "").strip() or None,
            ssh_port=int(form.get("ssh_port") or 22),
            enabled=form.get("enabled") == "on",
        )
        session.add(server)
        await session.flush()
        server_id = server.id

    return RedirectResponse(f"/servers/{server_id}/checks", status_code=302)


@router.get("/{server_id}/edit", response_class=HTMLResponse)
@login_required
async def server_edit_form(request: Request, server_id: int):
    async with get_session() as session:
        server = await session.get(Server, server_id)
        if not server:
            return RedirectResponse("/servers", status_code=302)

    return templates.TemplateResponse(
        request,
        "server_edit.html",
        {
            "server": server,
            "active_page": "servers",
            "action": f"/servers/{server_id}/edit",
            "title": f"Редактировать {server.name}",
        },
    )


@router.post("/{server_id}/edit")
@login_required
async def server_edit(request: Request, server_id: int):
    form = await request.form()
    name = (form.get("name") or "").strip()
    host = (form.get("host") or "").strip()

    if not name or not host:
        async with get_session() as session:
            server = await session.get(Server, server_id)
        return templates.TemplateResponse(
            request,
            "server_edit.html",
            {
                "server": server,
                "active_page": "servers",
                "action": f"/servers/{server_id}/edit",
                "title": f"Редактировать {server.name}",
                "error": "Имя и хост обязательны",
            },
        )

    async with get_session() as session:
        server = await session.get(Server, server_id)
        if not server:
            return RedirectResponse("/servers", status_code=302)

        server.name = name
        server.host = host
        server.ssh_user = (form.get("ssh_user") or "deploy").strip()
        server.ssh_key_path = (form.get("ssh_key_path") or "").strip() or None
        server.ssh_password = (form.get("ssh_password") or "").strip() or None
        server.ssh_port = int(form.get("ssh_port") or 22)
        server.enabled = form.get("enabled") == "on"

    return RedirectResponse(f"/servers/{server_id}/checks", status_code=302)


@router.post("/{server_id}/delete")
@login_required
async def server_delete(request: Request, server_id: int):
    async with get_session() as session:
        server = await session.get(Server, server_id)
        if server:
            await session.delete(server)

    return RedirectResponse("/servers", status_code=302)


@router.get("/{server_id}/checks", response_class=HTMLResponse)
@login_required
async def server_checks_form(request: Request, server_id: int):
    async with get_session() as session:
        server = await session.get(Server, server_id)
        if not server:
            return RedirectResponse("/servers", status_code=302)

        result = await session.execute(
            select(ServerCheck).where(ServerCheck.server_id == server_id)
        )
        existing_checks = {sc.check_name: sc for sc in result.scalars().all()}

    return templates.TemplateResponse(
        request,
        "server_checks.html",
        {
            "server": server,
            "active_page": "servers",
            "check_registry": list(CHECK_REGISTRY.keys()),
            "existing_checks": existing_checks,
        },
    )


@router.post("/{server_id}/checks")
@login_required
async def server_checks_update(request: Request, server_id: int):
    form = await request.form()

    async with get_session() as session:
        server = await session.get(Server, server_id)
        if not server:
            return RedirectResponse("/servers", status_code=302)

        result = await session.execute(
            select(ServerCheck).where(ServerCheck.server_id == server_id)
        )
        for sc in result.scalars().all():
            await session.delete(sc)

        for check_name in CHECK_REGISTRY:
            enabled = form.get(f"check_{check_name}_enabled") == "on"
            if not enabled:
                continue

            params_raw = form.get(f"check_{check_name}_params") or "{}"
            try:
                params = json.loads(params_raw)
            except json.JSONDecodeError:
                params = {}

            sc = ServerCheck(
                server_id=server_id,
                check_name=check_name,
                params=params,
                enabled=True,
            )
            session.add(sc)

    return RedirectResponse(f"/servers/{server_id}/checks?saved=1", status_code=302)
