from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.payment_link import PaymentLink, PaymentStatus
from app.schemas.payment_link import PaymentLinkCreate
from app.services.stripe_service import cancel_payment_intent, create_payment_intent
from app.services.twilio_service import format_expires_in, send_payment_sms
from app.utils.token import generate_token


async def create_payment(data: PaymentLinkCreate, db: Session) -> PaymentLink:
    token = generate_token(12)
    while db.query(PaymentLink).filter(PaymentLink.token == token).first():
        token = generate_token(12)

    expires_at = datetime.utcnow() + timedelta(minutes=data.expires_in_minutes)

    stripe_data = await create_payment_intent(
        amount=float(data.amount),
        currency="usd",
        customer_name=data.customer_name,
        description=data.description,
        token=token,
    )

    payment_link = PaymentLink(
        token=token,
        stripe_payment_intent_id=stripe_data["id"],
        stripe_client_secret=stripe_data["client_secret"],
        customer_name=data.customer_name,
        phone_number=data.phone_number,
        amount=data.amount,
        currency="usd",
        description=data.description,
        expires_at=expires_at,
        agent_name=data.agent_name,
        status=PaymentStatus.PENDING.value,
    )
    db.add(payment_link)
    db.commit()
    db.refresh(payment_link)

    payment_url = f"{settings.APP_URL}/pay/{token}"
    expires_in_text = format_expires_in(data.expires_in_minutes)
    sms_sent = send_payment_sms(
        to_number=data.phone_number,
        customer_name=data.customer_name,
        amount=float(data.amount),
        payment_url=payment_url,
        expires_in=expires_in_text,
    )

    if sms_sent:
        payment_link.status = PaymentStatus.SMS_SENT.value
        db.commit()

    return payment_link


def get_payment_by_token(token: str, db: Session) -> Optional[PaymentLink]:
    return db.query(PaymentLink).filter(PaymentLink.token == token).first()


def get_payment_by_id(payment_id: str, db: Session) -> Optional[PaymentLink]:
    return db.query(PaymentLink).filter(PaymentLink.id == payment_id).first()


def get_all_payments(
    db: Session, limit: int = 200, offset: int = 0
) -> List[PaymentLink]:
    return (
        db.query(PaymentLink)
        .order_by(PaymentLink.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def expire_stale_payments(db: Session) -> None:
    now = datetime.utcnow()
    active_statuses = [
        PaymentStatus.PENDING.value,
        PaymentStatus.SMS_SENT.value,
        PaymentStatus.OPENED.value,
        PaymentStatus.PROCESSING.value,
    ]
    db.query(PaymentLink).filter(
        and_(PaymentLink.expires_at <= now, PaymentLink.status.in_(active_statuses))
    ).update({"status": PaymentStatus.EXPIRED.value}, synchronize_session="fetch")
    db.commit()


async def cancel_payment(payment_id: str, db: Session) -> bool:
    payment = get_payment_by_id(payment_id, db)
    if not payment:
        return False
    if payment.status in [
        PaymentStatus.PAID.value,
        PaymentStatus.CANCELLED.value,
        PaymentStatus.EXPIRED.value,
    ]:
        return False

    if payment.stripe_payment_intent_id:
        await cancel_payment_intent(payment.stripe_payment_intent_id)

    payment.status = PaymentStatus.CANCELLED.value
    db.commit()
    return True


def get_dashboard_stats(db: Session) -> dict:
    expire_stale_payments(db)

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    total_today = (
        db.query(func.sum(PaymentLink.amount))
        .filter(
            and_(
                PaymentLink.paid_at >= today_start,
                PaymentLink.status == PaymentStatus.PAID.value,
            )
        )
        .scalar()
        or 0
    )

    total_month = (
        db.query(func.sum(PaymentLink.amount))
        .filter(
            and_(
                PaymentLink.paid_at >= month_start,
                PaymentLink.status == PaymentStatus.PAID.value,
            )
        )
        .scalar()
        or 0
    )

    status_counts = {}
    for s in PaymentStatus:
        status_counts[s.value] = (
            db.query(PaymentLink).filter(PaymentLink.status == s.value).count()
        )

    total_sent = db.query(PaymentLink).count()
    total_opened = (
        db.query(PaymentLink).filter(PaymentLink.opened_at.isnot(None)).count()
    )
    total_paid = status_counts.get(PaymentStatus.PAID.value, 0)

    conversion_rate = round((total_paid / total_sent * 100) if total_sent > 0 else 0, 1)
    open_rate = round((total_opened / total_sent * 100) if total_sent > 0 else 0, 1)

    hourly_data = []
    for i in range(24):
        h_start = today_start + timedelta(hours=i)
        h_end = h_start + timedelta(hours=1)
        created = db.query(PaymentLink).filter(
            and_(PaymentLink.created_at >= h_start, PaymentLink.created_at < h_end)
        ).count()
        paid = db.query(PaymentLink).filter(
            and_(
                PaymentLink.paid_at >= h_start,
                PaymentLink.paid_at < h_end,
                PaymentLink.status == PaymentStatus.PAID.value,
            )
        ).count()
        hourly_data.append(
            {"hour": h_start.strftime("%I %p"), "created": created, "paid": paid}
        )

    agent_rows = (
        db.query(PaymentLink.agent_name, func.count(PaymentLink.id))
        .group_by(PaymentLink.agent_name)
        .all()
    )

    return {
        "total_today": float(total_today),
        "total_month": float(total_month),
        "status_counts": status_counts,
        "total_sent": total_sent,
        "total_opened": total_opened,
        "total_paid": total_paid,
        "conversion_rate": conversion_rate,
        "open_rate": open_rate,
        "hourly_data": hourly_data,
        "agent_data": [
            {"name": row[0] or "Unknown", "count": row[1]} for row in agent_rows
        ],
    }
