import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.payment_link import PaymentLink, PaymentStatus
from app.services.stripe_service import retrieve_payment_intent_status

router = APIRouter()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))


@router.get("/pay/{token}", response_class=HTMLResponse)
async def payment_page(request: Request, token: str, db: Session = Depends(get_db)):
    payment = db.query(PaymentLink).filter(PaymentLink.token == token).first()

    if not payment:
        return templates.TemplateResponse(
            "payment_expired.html",
            {"request": request, "reason": "not_found"},
            status_code=404,
        )

    if payment.expires_at <= datetime.utcnow() and payment.status not in [
        PaymentStatus.PAID.value,
        PaymentStatus.CANCELLED.value,
        PaymentStatus.EXPIRED.value,
    ]:
        payment.status = PaymentStatus.EXPIRED.value
        db.commit()

    if payment.status == PaymentStatus.PAID.value:
        return templates.TemplateResponse(
            "payment_success.html", {"request": request, "payment": payment}
        )

    if payment.status in [PaymentStatus.EXPIRED.value, PaymentStatus.CANCELLED.value]:
        return templates.TemplateResponse(
            "payment_expired.html",
            {"request": request, "payment": payment, "reason": payment.status.lower()},
        )

    if payment.status in [
        PaymentStatus.PENDING.value,
        PaymentStatus.SMS_SENT.value,
        PaymentStatus.EMAIL_SENT.value,
    ]:
        payment.status = PaymentStatus.OPENED.value
        payment.opened_at = datetime.utcnow()
        payment.client_ip = request.client.host if request.client else None
        payment.user_agent = request.headers.get("user-agent", "")

    payment.last_activity = datetime.utcnow()
    db.commit()

    return templates.TemplateResponse(
        "pay.html",
        {
            "request": request,
            "payment": payment,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "return_url": f"{settings.APP_URL}/pay/{token}/result",
        },
    )


@router.get("/pay/{token}/result", response_class=HTMLResponse)
async def payment_result(request: Request, token: str, db: Session = Depends(get_db)):
    payment = db.query(PaymentLink).filter(PaymentLink.token == token).first()

    if not payment:
        return templates.TemplateResponse(
            "payment_expired.html", {"request": request, "reason": "not_found"}
        )

    if payment.status == PaymentStatus.PAID.value:
        return templates.TemplateResponse(
            "payment_success.html", {"request": request, "payment": payment}
        )

    # NUNCA confiar en el query param redirect_status para marcar PAID:
    # es controlable por el cliente. Verificar el estado real con Stripe.
    redirect_status = request.query_params.get("redirect_status", "")
    if redirect_status == "succeeded" and payment.stripe_payment_intent_id:
        real_status = await retrieve_payment_intent_status(
            payment.stripe_payment_intent_id
        )
        if real_status == "succeeded":
            payment.status = PaymentStatus.PAID.value
            payment.paid_at = datetime.utcnow()
            db.commit()
            return templates.TemplateResponse(
                "payment_success.html", {"request": request, "payment": payment}
            )

    return templates.TemplateResponse(
        "pay.html",
        {
            "request": request,
            "payment": payment,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "return_url": f"{settings.APP_URL}/pay/{token}/result",
            "processing": True,
        },
    )
