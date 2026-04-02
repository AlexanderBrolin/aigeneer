"""Authentication for the web panel."""

from functools import wraps

from fastapi import Request
from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeSerializer

from app.config import settings

serializer = URLSafeSerializer(settings.secret_key)


def login_required(func):
    """Decorator that redirects to /login if not authenticated."""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if not request.session.get("logged_in"):
            return RedirectResponse("/login", status_code=302)
        return await func(request, *args, **kwargs)

    return wrapper


def verify_credentials(username: str, password: str) -> bool:
    """Check credentials against config (for initial setup) or DB."""
    # Simple config-based auth for now; DB-based AdminUser comes in E11
    return username == settings.admin_username and password == settings.admin_password
