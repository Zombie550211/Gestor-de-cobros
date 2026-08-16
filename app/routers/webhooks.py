from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.charge import Charge, ChargeStatus
from app.models.payment_link import PaymentLink, PaymentStatus
from app.services.payment_service import save_card_from_payment
from app.services.stripe_service import verify_webhook_signature

router = APIRouter()


def _handle_recharge_event(event_type: str, charge_id: str, db: Session) -> None:
    """Cobros del Data Center: actualizan su propia fila, no el link original."""
    charge = db.query(Charge).filter(Charge.id == charge_id).first()
    if not charge:
        return

    if event_type == "payment_intent.succeeded":
        charge.status = ChargeStatus.SUCCEEDED.value
        charge.failure_message = None
        db.commit()
    elif event_type == "payment_intent.payment_failed":
        if charge.status != ChargeStatus.SUCCEEDED.value:
            charge.status = ChargeStatus.FAILED.value
            db.commit()


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(payload, sig)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    data_obj = event["data"]["object"]
    metadata = data_obj.get("metadata", {})
    token = metadata.get("payment_token")

    charge_id = metadata.get("charge_id")
    if charge_id:
        _handle_recharge_event(event["type"], charge_id, db)
        return JSONResponse({"received": True})

    if not token:
        return JSONResponse({"received": True})

    payment = db.query(PaymentLink).filter(PaymentLink.token == token).first()
    if not payment:
        return JSONResponse({"received": True})

    if event["type"] == "payment_intent.succeeded":
        payment.status = PaymentStatus.PAID.value
        payment.paid_at = datetime.utcnow()
        payment.last_activity = datetime.utcnow()
        db.commit()
        # Registra la tarjeta para poder volver a cobrarla desde el Data Center.
        await save_card_from_payment(payment, db)

    elif event["type"] == "payment_intent.payment_failed":
        if payment.status != PaymentStatus.PAID.value:
            payment.status = PaymentStatus.FAILED.value
            payment.last_activity = datetime.utcnow()
            db.commit()

    return JSONResponse({"received": True})
