"""Settings views — LLM, Telegram, SSH keys, Schedule, Users."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.config import settings as env_settings
from app.db.models import AdminUser, Setting, SshKey
from app.db.session import get_session
from app.services.auth import hash_password
from app.services.crypto import decrypt_value, encrypt_value
from app.services.settings import SETTINGS_DEFS, SettingsService
from app.web.auth import login_required

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="app/web/templates")

_svc = SettingsService(secret_key=env_settings.secret_key)


def _mask_secret(value: str | None) -> str:
    """Show first 4 + '***' + last 3 chars for secret display."""
    if not value:
        return ""
    if len(value) <= 7:
        return "***"
    return value[:4] + "***" + value[-3:]


def _is_masked(value: str) -> bool:
    """Check if value looks like a masked secret (contains ***)."""
    return "***" in value


# ---------------------------------------------------------------------------
# Settings page (GET)
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
@login_required
async def settings_page(request: Request):
    async with get_session() as session:
        all_settings = await _svc.get_all(session)

        # Build masked dict for secret fields
        masked: dict[str, str] = {}
        for key, (category, is_secret, _) in SETTINGS_DEFS.items():
            val = all_settings.get(key, "")
            masked[key] = _mask_secret(val) if is_secret else val

        # SSH keys
        result = await session.execute(select(SshKey).order_by(SshKey.created_at.desc()))
        ssh_keys = result.scalars().all()

        # Users
        result = await session.execute(select(AdminUser).order_by(AdminUser.created_at))
        users = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "settings": all_settings,
            "masked": masked,
            "ssh_keys": ssh_keys,
            "users": users,
            "defs": SETTINGS_DEFS,
        },
    )


# ---------------------------------------------------------------------------
# Settings save (POST) — one form per category tab
# ---------------------------------------------------------------------------
@router.post("")
@login_required
async def settings_save(request: Request):
    form = await request.form()
    category = (form.get("category") or "").strip()

    if not category:
        return RedirectResponse("/settings?msg=Категория не указана", status_code=302)

    # Collect keys that belong to this category
    keys_for_category = [k for k, (cat, _, _) in SETTINGS_DEFS.items() if cat == category]

    updates: dict[str, str] = {}
    for key in keys_for_category:
        value = (form.get(key) or "").strip()
        _, is_secret, _ = SETTINGS_DEFS[key]
        # Skip secret fields that still contain mask characters
        if is_secret and _is_masked(value):
            continue
        updates[key] = value

    if updates:
        async with get_session() as session:
            needs_restart = await _svc.bulk_update(session, updates)

        msg = "Настройки сохранены"
        if needs_restart:
            msg += " (требуется перезапуск)"
    else:
        msg = "Нет изменений"

    return RedirectResponse(f"/settings?msg={msg}#{category}", status_code=302)


# ---------------------------------------------------------------------------
# SSH Keys — JSON list
# ---------------------------------------------------------------------------
@router.get("/ssh-keys")
@login_required
async def ssh_keys_list(request: Request):
    async with get_session() as session:
        result = await session.execute(select(SshKey).order_by(SshKey.created_at.desc()))
        keys = result.scalars().all()

    return [
        {
            "id": k.id,
            "name": k.name,
            "is_default": k.is_default,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]


# ---------------------------------------------------------------------------
# SSH Keys — Create
# ---------------------------------------------------------------------------
@router.post("/ssh-keys")
@login_required
async def ssh_key_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    private_key = (form.get("private_key") or "").strip()
    is_default = form.get("is_default") == "on"

    if not name or not private_key:
        return RedirectResponse("/settings?msg=Имя и ключ обязательны#ssh", status_code=302)

    encrypted_key = encrypt_value(private_key, env_settings.secret_key)

    async with get_session() as session:
        if is_default:
            # Unset all other defaults
            result = await session.execute(select(SshKey).where(SshKey.is_default.is_(True)))
            for existing in result.scalars().all():
                existing.is_default = False

        key = SshKey(name=name, private_key=encrypted_key, is_default=is_default)
        session.add(key)

    return RedirectResponse("/settings?msg=SSH ключ добавлен#ssh", status_code=302)


# ---------------------------------------------------------------------------
# SSH Keys — Update
# ---------------------------------------------------------------------------
@router.post("/ssh-keys/{key_id}")
@login_required
async def ssh_key_update(request: Request, key_id: int):
    form = await request.form()
    name = (form.get("name") or "").strip()
    is_default = form.get("is_default") == "on"
    private_key = (form.get("private_key") or "").strip()

    async with get_session() as session:
        key = await session.get(SshKey, key_id)
        if not key:
            return RedirectResponse("/settings?msg=Ключ не найден#ssh", status_code=302)

        if name:
            key.name = name
        if private_key and not _is_masked(private_key):
            key.private_key = encrypt_value(private_key, env_settings.secret_key)

        if is_default and not key.is_default:
            # Unset all other defaults
            result = await session.execute(select(SshKey).where(SshKey.is_default.is_(True)))
            for existing in result.scalars().all():
                existing.is_default = False
        key.is_default = is_default

    return RedirectResponse("/settings?msg=SSH ключ обновлён#ssh", status_code=302)


# ---------------------------------------------------------------------------
# SSH Keys — Delete
# ---------------------------------------------------------------------------
@router.post("/ssh-keys/{key_id}/delete")
@login_required
async def ssh_key_delete(request: Request, key_id: int):
    async with get_session() as session:
        key = await session.get(SshKey, key_id)
        if key:
            await session.delete(key)

    return RedirectResponse("/settings?msg=SSH ключ удалён#ssh", status_code=302)


# ---------------------------------------------------------------------------
# Users — Create
# ---------------------------------------------------------------------------
@router.post("/users")
@login_required
async def user_create(request: Request):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = (form.get("password") or "").strip()

    if not username or not password:
        return RedirectResponse(
            "/settings?msg=Логин и пароль обязательны#users", status_code=302
        )

    async with get_session() as session:
        # Check if username already exists
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == username)
        )
        if result.scalar_one_or_none():
            return RedirectResponse(
                "/settings?msg=Пользователь уже существует#users", status_code=302
            )

        user = AdminUser(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(user)

    return RedirectResponse("/settings?msg=Пользователь создан#users", status_code=302)


# ---------------------------------------------------------------------------
# Users — Update
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}")
@login_required
async def user_update(request: Request, user_id: int):
    form = await request.form()
    password = (form.get("password") or "").strip()
    is_active = form.get("is_active") == "on"

    async with get_session() as session:
        user = await session.get(AdminUser, user_id)
        if not user:
            return RedirectResponse("/settings?msg=Пользователь не найден#users", status_code=302)

        if password:
            user.password_hash = hash_password(password)
        user.is_active = is_active

    return RedirectResponse("/settings?msg=Пользователь обновлён#users", status_code=302)


# ---------------------------------------------------------------------------
# Users — Delete
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/delete")
@login_required
async def user_delete(request: Request, user_id: int):
    current_username = request.session.get("username", "")

    async with get_session() as session:
        user = await session.get(AdminUser, user_id)
        if not user:
            return RedirectResponse("/settings?msg=Пользователь не найден#users", status_code=302)

        # Cannot delete self
        if user.username == current_username:
            return RedirectResponse(
                "/settings?msg=Нельзя удалить самого себя#users", status_code=302
            )

        # Cannot delete last active user
        result = await session.execute(
            select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True))
        )
        active_count = result.scalar() or 0

        if active_count <= 1 and user.is_active:
            return RedirectResponse(
                "/settings?msg=Нельзя удалить последнего активного пользователя#users",
                status_code=302,
            )

        await session.delete(user)

    return RedirectResponse("/settings?msg=Пользователь удалён#users", status_code=302)
