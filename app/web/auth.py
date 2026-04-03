"""Authentication for the web panel."""

from functools import wraps

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.db.session import get_session
from app.services.auth import verify_credentials_db


def login_required(func):
    """Decorator that redirects to /login if not authenticated."""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("logged_in"):
            return RedirectResponse("/login", status_code=302)
        return await func(request, *args, **kwargs)

    return wrapper


async def verify_credentials(username: str, password: str) -> bool:
    """Check credentials: DB first, then .env fallback."""
    async with get_session() as session:
        if await verify_credentials_db(session, username, password):
            return True
    # Fallback to .env (emergency access when no DB users exist)
    return username == settings.admin_username and password == settings.admin_password
