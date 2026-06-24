import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.utils.auth import COOKIE_NAME, make_session_token, verify_password

router = APIRouter()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

_COOKIE_SECURE = settings.APP_URL.startswith("https")
_COOKIE_MAX_AGE = 60 * 60 * 8  # 8 horas


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_submit(request: Request, password: str = Form("")):
    if not verify_password(password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect password"},
            status_code=401,
        )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=make_session_token(),
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
