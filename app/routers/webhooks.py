from datetime import datetime

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.payment_link import PaymentLink, PaymentStatus
from app.services.stripe_service import verify_webhook_signature

router = APIRouter()


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
    token = data_obj.get("metadata", {}).get("payment_token")

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

    elif event["type"] == "payment_intent.payment_failed":
        if payment.status != PaymentStatus.PAID.value:
            payment.status = PaymentStatus.FAILED.value
            payment.last_activity = datetime.utcnow()
            db.commit()

    return JSONResponse({"received": True})
