from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.payment_link import PaymentLinkCreate
from app.services.payment_service import (
    cancel_payment,
    expire_stale_payments,
    get_all_payments,
    get_dashboard_stats,
    get_payment_by_token,
    create_payment,
)

router = APIRouter(prefix="/api")


@router.post("/payments")
async def create_payment_endpoint(data: PaymentLinkCreate, db: Session = Depends(get_db)):
    try:
        payment = await create_payment(data, db)
        return {
            "success": True,
            "token": payment.token,
            "payment_url": f"{settings.APP_URL}/pay/{payment.token}",
            "status": payment.status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payments")
async def list_payments(db: Session = Depends(get_db)):
    expire_stale_payments(db)
    payments = get_all_payments(db)
    return [
        {
            "id": str(p.id),
            "token": p.token,
            "customer_name": p.customer_name,
            "phone_number": p.phone_number,
            "amount": float(p.amount),
            "status": p.status,
            "created_at": p.created_at.isoformat(),
            "expires_at": p.expires_at.isoformat(),
            "agent_name": p.agent_name,
        }
        for p in payments
    ]


@router.post("/payments/{payment_id}/cancel")
async def cancel_payment_endpoint(payment_id: str, db: Session = Depends(get_db)):
    success = await cancel_payment(payment_id, db)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this payment")
    return {"success": True}


@router.get("/stats")
async def stats(db: Session = Depends(get_db)):
    return get_dashboard_stats(db)


@router.post("/payments/{token}/activity")
async def track_activity(token: str, body: dict, db: Session = Depends(get_db)):
    from datetime import datetime
    from app.models.payment_link import PaymentLink, PaymentStatus

    payment = get_payment_by_token(token, db)
    if payment and payment.status not in [
        PaymentStatus.PAID.value,
        PaymentStatus.EXPIRED.value,
        PaymentStatus.CANCELLED.value,
    ]:
        payment.last_activity = datetime.utcnow()
        if body.get("status") == "processing":
            payment.status = PaymentStatus.PROCESSING.value
        if body.get("time_spent") is not None:
            payment.time_spent = body["time_spent"]
        db.commit()
    return {"ok": True}
