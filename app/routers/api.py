from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas.payment_link import ActivityUpdate, PaymentLinkCreate, RechargeCreate
from app.utils.auth import require_admin_api
from app.services.payment_service import (
    backfill_from_stripe,
    cancel_payment,
    expire_stale_payments,
    get_all_payments,
    get_card_charges,
    get_dashboard_stats,
    get_payment_by_id,
    get_payment_by_token,
    create_payment,
    recharge_saved_card,
)

router = APIRouter(prefix="/api")


@router.post("/payments", dependencies=[Depends(require_admin_api)])
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
        # No exponer detalles internos al cliente; registrarlos en el servidor.
        print(f"[api] Error creando pago: {e}")
        raise HTTPException(
            status_code=500, detail="Could not create the payment. Please try again."
        )


@router.get("/payments", dependencies=[Depends(require_admin_api)])
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


@router.post("/payments/{payment_id}/cancel", dependencies=[Depends(require_admin_api)])
async def cancel_payment_endpoint(payment_id: str, db: Session = Depends(get_db)):
    success = await cancel_payment(payment_id, db)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this payment")
    return {"success": True}


@router.post("/data-center/backfill", dependencies=[Depends(require_admin_api)])
async def backfill_endpoint(db: Session = Depends(get_db)):
    """Recupera de Stripe los clientes y tarjetas de pagos anteriores."""
    try:
        return await backfill_from_stripe(db)
    except Exception as e:  # noqa: BLE001
        print(f"[api] Error recuperando historial: {e}")
        raise HTTPException(
            status_code=500, detail="Could not recover the payment history."
        )


@router.post(
    "/data-center/{payment_id}/charge", dependencies=[Depends(require_admin_api)]
)
async def charge_saved_card_endpoint(
    payment_id: str, data: RechargeCreate, db: Session = Depends(get_db)
):
    """Cobra de nuevo la tarjeta guardada, sin pedirle los datos al cliente."""
    result = await recharge_saved_card(
        payment_id=payment_id,
        amount=data.amount,
        description=data.description,
        agent_name=data.agent_name,
        db=db,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get(
    "/data-center/{payment_id}/charges", dependencies=[Depends(require_admin_api)]
)
async def list_card_charges(payment_id: str, db: Session = Depends(get_db)):
    payment = get_payment_by_id(payment_id, db)
    if not payment:
        raise HTTPException(status_code=404, detail="Record not found")

    charges = get_card_charges(payment_id, db)
    return {
        "customer_name": payment.customer_name,
        "card_last4": payment.card_last4,
        "charges": [
            {
                "id": c.id,
                "amount": float(c.amount),
                "status": c.status,
                "description": c.description,
                "agent_name": c.agent_name,
                "failure_message": c.failure_message,
                "created_at": c.created_at.isoformat(),
            }
            for c in charges
        ],
    }


@router.get("/stats", dependencies=[Depends(require_admin_api)])
async def stats(db: Session = Depends(get_db)):
    return get_dashboard_stats(db)


@router.post("/payments/{token}/activity")
async def track_activity(token: str, body: ActivityUpdate, db: Session = Depends(get_db)):
    from datetime import datetime
    from app.models.payment_link import PaymentStatus

    payment = get_payment_by_token(token, db)
    if payment and payment.status not in [
        PaymentStatus.PAID.value,
        PaymentStatus.EXPIRED.value,
        PaymentStatus.CANCELLED.value,
    ]:
        payment.last_activity = datetime.utcnow()
        if body.status == "processing":
            payment.status = PaymentStatus.PROCESSING.value
        if body.time_spent is not None:
            payment.time_spent = body.time_spent
        db.commit()
    return {"ok": True}
