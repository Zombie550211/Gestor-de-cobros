import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.payment_service import (
    expire_stale_payments,
    get_all_payments,
    get_dashboard_stats,
)
from app.utils.auth import require_admin_page

router = APIRouter(dependencies=[Depends(require_admin_page)])

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))


def _register_filters():
    def currency(v):
        if v is None:
            return "$0.00"
        return f"${float(v):,.2f}"

    def dt_fmt(v):
        if not v:
            return "—"
        return v.strftime("%m/%d/%Y %I:%M %p")

    def phone_fmt(v):
        if not v:
            return v
        digits = "".join(filter(str.isdigit, v))
        if len(digits) == 11 and digits[0] == "1":
            digits = digits[1:]
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        return v

    templates.env.filters["currency"] = currency
    templates.env.filters["dt"] = dt_fmt
    templates.env.filters["phone"] = phone_fmt


_register_filters()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    expire_stale_payments(db)
    stats = get_dashboard_stats(db)
    recent = get_all_payments(db, limit=10)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "recent_payments": recent, "active_page": "dashboard"},
    )


@router.get("/payments", response_class=HTMLResponse)
async def payment_list(request: Request, db: Session = Depends(get_db)):
    expire_stale_payments(db)
    payments = get_all_payments(db, limit=500)
    return templates.TemplateResponse(
        "payment_list.html",
        {"request": request, "payments": payments, "active_page": "payments"},
    )


@router.get("/payments/create", response_class=HTMLResponse)
async def create_form(request: Request):
    return templates.TemplateResponse(
        "create_payment.html",
        {"request": request, "active_page": "create"},
    )
