"""Autenticación simple del panel de administración mediante cookie firmada.

No requiere dependencias extra: usa HMAC-SHA256 con SECRET_KEY de la stdlib.
La cookie no guarda datos sensibles, solo un token firmado que prueba el login.
"""
import hashlib
import hmac

from fastapi import HTTPException, Request, status

from app.config import settings

COOKIE_NAME = "spc_session"
_MARKER = b"authenticated-admin"


def _expected_token() -> str:
    return hmac.new(settings.SECRET_KEY.encode(), _MARKER, hashlib.sha256).hexdigest()


def make_session_token() -> str:
    return _expected_token()


def verify_password(password: str) -> bool:
    return hmac.compare_digest(password or "", settings.ADMIN_PASSWORD)


def is_authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    return hmac.compare_digest(token, _expected_token())


def require_admin_page(request: Request) -> None:
    """Dependencia para páginas HTML: redirige a /login si no hay sesión."""
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )


def require_admin_api(request: Request) -> None:
    """Dependencia para endpoints de la API admin: responde 401 si no hay sesión."""
    if not is_authenticated(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
