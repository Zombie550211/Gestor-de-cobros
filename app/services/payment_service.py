from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.charge import Charge, ChargeStatus
from app.models.payment_link import PaymentLink, PaymentStatus
from app.schemas.payment_link import PaymentLinkCreate
from app.services.email_service import send_payment_email
from app.services.stripe_service import (
    cancel_payment_intent,
    card_from_payment_method,
    charge_saved_card,
    create_customer,
    create_payment_intent,
    list_succeeded_intents,
    retrieve_card_details,
    retrieve_payment_intent,
)
from app.services.twilio_service import format_expires_in, send_payment_sms
from app.utils.token import generate_token


async def create_payment(data: PaymentLinkCreate, db: Session) -> PaymentLink:
    token = generate_token(12)
    while db.query(PaymentLink).filter(PaymentLink.token == token).first():
        token = generate_token(12)

    expires_at = datetime.utcnow() + timedelta(minutes=data.expires_in_minutes)

    # El Customer se crea antes del intent para que la tarjeta quede guardada y
    # se pueda volver a cobrar desde el Data Center.
    customer_id = await create_customer(
        name=data.customer_name,
        email=data.customer_email,
        phone=data.phone_number,
    )

    stripe_data = await create_payment_intent(
        amount=float(data.amount),
        currency="usd",
        customer_name=data.customer_name,
        description=data.description,
        token=token,
        customer_id=customer_id,
    )

    payment_link = PaymentLink(
        token=token,
        stripe_payment_intent_id=stripe_data["id"],
        stripe_client_secret=stripe_data["client_secret"],
        stripe_customer_id=customer_id,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
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

    # Canal principal: correo (solo si se proporcionó un email).
    # Cuando el link se crea solo con el monto, no hay correo que enviar: el
    # agente copia el link y lo comparte por el medio que prefiera.
    email_sent = False
    if data.customer_email:
        email_sent = send_payment_email(
            to_email=data.customer_email,
            customer_name=data.customer_name,
            amount=float(data.amount),
            payment_url=payment_url,
            expires_in=expires_in_text,
        )

    # Canal secundario: SMS (solo si hay teléfono y Twilio configurado)
    sms_sent = False
    if data.phone_number:
        sms_sent = send_payment_sms(
            to_number=data.phone_number,
            customer_name=data.customer_name,
            amount=float(data.amount),
            payment_url=payment_url,
            expires_in=expires_in_text,
        )

    if email_sent:
        payment_link.status = PaymentStatus.EMAIL_SENT.value
        db.commit()
    elif sms_sent:
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
        PaymentStatus.EMAIL_SENT.value,
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


# ============================================================
#  DATA CENTER — tarjetas guardadas y cobros repetidos
# ============================================================

async def save_card_from_payment(payment: PaymentLink, db: Session) -> bool:
    """Guarda la referencia de la tarjeta usada en un pago exitoso.

    Solo se conservan el id del método de pago (que Stripe permite reutilizar)
    y los datos visibles: marca, últimos 4 dígitos y vencimiento. El número
    completo nunca llega al servidor.
    """
    if payment.stripe_payment_method_id or not payment.stripe_payment_intent_id:
        return False

    intent = await retrieve_payment_intent(payment.stripe_payment_intent_id)
    if not intent:
        return False

    payment_method_id = intent.get("payment_method")
    if not payment_method_id:
        return False

    card = await retrieve_card_details(payment_method_id)
    if not card:
        return False

    payment.stripe_payment_method_id = payment_method_id
    payment.stripe_customer_id = intent.get("customer") or payment.stripe_customer_id
    payment.card_brand = card["brand"]
    payment.card_last4 = card["last4"]
    payment.card_exp_month = card["exp_month"]
    payment.card_exp_year = card["exp_year"]
    payment.card_funding = card["funding"]
    payment.card_country = card["country"]
    payment.card_fingerprint = card["fingerprint"]
    payment.card_source = "checkout"
    db.commit()
    return True


async def backfill_from_stripe(db: Session, limit: int = 300) -> dict:
    """Reconstruye el Data Center con los pagos históricos de la cuenta Stripe.

    Recupera nombre, contacto y datos visibles de la tarjeta de cada pago
    exitoso, y crea el registro si se perdió de la base local. Estas tarjetas
    quedan como "recovered": se pueden consultar, pero no se les puede cobrar,
    porque el titular autorizó un pago único y no cobros posteriores.
    """
    intents = await list_succeeded_intents(limit=limit)
    stats = {"scanned": len(intents), "updated": 0, "imported": 0, "skipped": 0}

    for intent in intents:
        card = card_from_payment_method(intent.get("payment_method"))
        if not card:
            stats["skipped"] += 1
            continue

        metadata = intent.get("metadata") or {}
        payment = (
            db.query(PaymentLink)
            .filter(PaymentLink.stripe_payment_intent_id == intent["id"])
            .first()
        )
        if not payment and metadata.get("payment_token"):
            payment = get_payment_by_token(metadata["payment_token"], db)

        paid_at = datetime.utcfromtimestamp(intent["created"])

        if payment:
            if payment.stripe_payment_method_id:
                stats["skipped"] += 1
                continue
            # El estado local puede haber quedado desfasado si el webhook no
            # llegó: Stripe manda.
            payment.status = PaymentStatus.PAID.value
            payment.paid_at = payment.paid_at or paid_at
            stats["updated"] += 1
        else:
            payment = _import_payment_from_intent(intent, card, paid_at, db)
            stats["imported"] += 1

        payment.stripe_payment_method_id = card["payment_method_id"]
        payment.card_brand = card["brand"]
        payment.card_last4 = card["last4"]
        payment.card_exp_month = card["exp_month"]
        payment.card_exp_year = card["exp_year"]
        payment.card_funding = card["funding"]
        payment.card_country = card["country"]
        payment.card_fingerprint = card["fingerprint"]
        payment.card_source = "recovered"
        # Sin stripe_customer_id a propósito: no hay autorización del titular
        # para cobros futuros, así que el botón Cobro queda inhabilitado.
        db.commit()

    return stats


def _import_payment_from_intent(intent, card: dict, paid_at, db: Session) -> PaymentLink:
    """Crea el registro de un pago que existe en Stripe pero no en la base local."""
    metadata = intent.get("metadata") or {}

    token = metadata.get("payment_token") or generate_token(12)
    while db.query(PaymentLink).filter(PaymentLink.token == token).first():
        token = generate_token(12)

    payment = PaymentLink(
        token=token,
        stripe_payment_intent_id=intent["id"],
        customer_name=card["name"] or metadata.get("customer_name") or "Unknown customer",
        customer_email=card["email"],
        phone_number=card["phone"],
        amount=Decimal(intent["amount"]) / 100,
        currency=intent.get("currency") or "usd",
        description=intent.get("description") or "Recovered from Stripe",
        status=PaymentStatus.PAID.value,
        created_at=paid_at,
        expires_at=paid_at,
        paid_at=paid_at,
        last_activity=paid_at,
    )
    db.add(payment)
    db.flush()
    return payment


def _card_key(payment: PaymentLink) -> str:
    """Identidad de la tarjeta física.

    Stripe emite un payment_method distinto en cada cobro, así que la huella es
    lo que agrupa los pagos de un mismo cliente. Si falta, se cae al id del
    método de pago.
    """
    return payment.card_fingerprint or payment.stripe_payment_method_id


def _card_is_expired(payment: PaymentLink) -> bool:
    if not payment.card_exp_year or not payment.card_exp_month:
        return False
    now = datetime.utcnow()
    return (payment.card_exp_year, payment.card_exp_month) < (now.year, now.month)


def get_saved_cards(db: Session) -> List[dict]:
    """Una entrada por tarjeta guardada, con su historial de cobros agregado.

    Si el mismo cliente pagó varios links con la misma tarjeta, se agrupan en
    una sola entrada (la del link más reciente).
    """
    links = (
        db.query(PaymentLink)
        .filter(PaymentLink.stripe_payment_method_id.isnot(None))
        .order_by(PaymentLink.created_at.desc())
        .all()
    )
    if not links:
        return []

    charges_by_card = defaultdict(list)
    rows = (
        db.query(Charge, PaymentLink)
        .join(PaymentLink, Charge.payment_link_id == PaymentLink.id)
        .all()
    )
    for charge, link in rows:
        charges_by_card[_card_key(link)].append(charge)

    grouped: dict = {}
    for link in links:
        grouped.setdefault(_card_key(link), []).append(link)

    cards = []
    for card_key, group in grouped.items():
        primary = group[0]  # el link más reciente de esa tarjeta
        charges = charges_by_card.get(card_key, [])
        successful = [c for c in charges if c.status == ChargeStatus.SUCCEEDED.value]

        total = sum(
            float(link.amount)
            for link in group
            if link.status == PaymentStatus.PAID.value
        )
        total += sum(float(c.amount) for c in successful)

        timestamps = [c.created_at for c in successful]
        timestamps += [link.paid_at for link in group if link.paid_at]

        cards.append(
            {
                "payment": primary,
                "charges_count": len(successful),
                "total_collected": total,
                "last_activity": max(timestamps) if timestamps else primary.created_at,
                "card_expired": _card_is_expired(primary),
                # Solo se puede volver a cobrar si el cliente autorizó guardar la
                # tarjeta al pagar (eso es lo que crea el Customer en Stripe).
                "chargeable": bool(primary.stripe_customer_id)
                and primary.card_source != "recovered",
            }
        )

    cards.sort(key=lambda c: c["last_activity"], reverse=True)
    return cards


def get_card_charges(payment_id: str, db: Session) -> List[Charge]:
    """Cobros hechos a la tarjeta del registro indicado (de todos sus links)."""
    payment = get_payment_by_id(payment_id, db)
    if not payment or not payment.stripe_payment_method_id:
        return []

    if payment.card_fingerprint:
        card_filter = PaymentLink.card_fingerprint == payment.card_fingerprint
    else:
        card_filter = (
            PaymentLink.stripe_payment_method_id == payment.stripe_payment_method_id
        )

    return (
        db.query(Charge)
        .join(PaymentLink, Charge.payment_link_id == PaymentLink.id)
        .filter(card_filter)
        .order_by(Charge.created_at.desc())
        .all()
    )


def _charge_status_from_result(result: dict) -> str:
    if result["ok"]:
        return ChargeStatus.SUCCEEDED.value
    if result.get("code") == "authentication_required" or result.get("status") in (
        "requires_action",
        "requires_confirmation",
    ):
        return ChargeStatus.REQUIRES_ACTION.value
    if result.get("status") == "processing":
        return ChargeStatus.PROCESSING.value
    return ChargeStatus.FAILED.value


async def recharge_saved_card(
    payment_id: str,
    amount: Decimal,
    description: Optional[str],
    agent_name: Optional[str],
    db: Session,
) -> dict:
    """Vuelve a cobrar la tarjeta guardada de un cliente por el monto indicado."""
    payment = get_payment_by_id(payment_id, db)
    if not payment:
        return {"ok": False, "error": "Record not found."}
    if not payment.stripe_payment_method_id:
        return {"ok": False, "error": "This customer has no saved card yet."}
    if payment.card_source == "recovered" or not payment.stripe_customer_id:
        return {
            "ok": False,
            "error": (
                "This card comes from a one-time payment and Stripe does not "
                "allow reusing it. Send the customer a new payment link — once "
                "they pay, the card is saved and can be charged from here."
            ),
        }

    final_description = (description or "").strip() or (
        f"Additional charge — {payment.customer_name}"
    )

    charge = Charge(
        payment_link_id=payment.id,
        amount=amount,
        currency=payment.currency or "usd",
        description=final_description,
        agent_name=agent_name or payment.agent_name,
        status=ChargeStatus.PROCESSING.value,
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)

    result = await charge_saved_card(
        customer_id=payment.stripe_customer_id,
        payment_method_id=payment.stripe_payment_method_id,
        amount=float(amount),
        currency=payment.currency or "usd",
        description=final_description,
        metadata={
            "customer_name": payment.customer_name,
            "payment_token": payment.token,
            "charge_id": charge.id,
            "charge_type": "recharge",
        },
        # Evita cobrar dos veces si el agente hace doble clic o se reintenta.
        idempotency_key=f"recharge_{charge.id}",
    )

    charge.stripe_payment_intent_id = result["id"]
    charge.status = _charge_status_from_result(result)
    charge.failure_message = result["error"]
    db.commit()

    if charge.status == ChargeStatus.REQUIRES_ACTION.value:
        message = (
            "The bank requires the customer to authenticate this charge. "
            "Send a new payment link instead."
        )
    else:
        message = result["error"]

    return {
        "ok": result["ok"],
        "status": charge.status,
        "charge_id": charge.id,
        "amount": float(amount),
        "error": None if result["ok"] else message,
    }


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

    # Los cobros repetidos del Data Center también son dinero recaudado.
    def _charged_since(start):
        return (
            db.query(func.sum(Charge.amount))
            .filter(
                and_(
                    Charge.created_at >= start,
                    Charge.status == ChargeStatus.SUCCEEDED.value,
                )
            )
            .scalar()
            or 0
        )

    total_today += _charged_since(today_start)
    total_month += _charged_since(month_start)

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
