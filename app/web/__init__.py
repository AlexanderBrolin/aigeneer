"""Web panel — FastAPI + Jinja2 + Tailwind + Alpine.js."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.web.auth import verify_credentials

templates = Jinja2Templates(directory="app/web/templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("logged_in"):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    if verify_credentials(username, password):
        request.session["logged_in"] = True
        request.session["username"] = username
        return RedirectResponse("/dashboard", status_code=302)

    return templates.TemplateResponse(
        request, "login.html", {"error": "Неверные логин или пароль"}
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
