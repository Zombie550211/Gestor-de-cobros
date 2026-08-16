import stripe

from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


async def create_customer(
    name: str, email: str | None = None, phone: str | None = None
) -> str | None:
    """Crea el Customer de Stripe al que se asociará la tarjeta guardada.

    Sin Customer no se puede volver a cobrar después, así que se crea siempre
    junto con el link de pago. Devuelve None si Stripe falla (el link se sigue
    generando, pero esa tarjeta no quedará disponible en el Data Center).
    """
    try:
        customer = stripe.Customer.create(
            name=name,
            email=email or None,
            phone=phone or None,
        )
        return customer.id
    except stripe.error.StripeError as e:
        print(f"[stripe] no se pudo crear el Customer: {e}")
        return None


async def create_payment_intent(
    amount: float,
    currency: str,
    customer_name: str,
    description: str,
    token: str,
    customer_id: str | None = None,
) -> dict:
    params = {
        "amount": int(round(amount * 100)),
        "currency": currency,
        "description": description,
        "metadata": {"customer_name": customer_name, "payment_token": token},
        "automatic_payment_methods": {"enabled": True},
    }

    # setup_future_usage guarda la tarjeta en el Customer y muestra al cliente
    # el aviso de que quedará registrada para cobros futuros.
    if customer_id:
        params["customer"] = customer_id
        params["setup_future_usage"] = "off_session"

    intent = stripe.PaymentIntent.create(**params)
    return {"id": intent.id, "client_secret": intent.client_secret}


async def charge_saved_card(
    customer_id: str,
    payment_method_id: str,
    amount: float,
    currency: str,
    description: str,
    metadata: dict,
    idempotency_key: str | None = None,
) -> dict:
    """Cobra una tarjeta ya guardada, sin intervención del cliente.

    Devuelve siempre un dict; los rechazos de tarjeta llegan como CardError y se
    traducen a {"ok": False, "error": mensaje} en vez de propagar la excepción.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(round(amount * 100)),
            currency=currency,
            customer=customer_id,
            payment_method=payment_method_id,
            description=description,
            metadata=metadata,
            off_session=True,
            confirm=True,
            idempotency_key=idempotency_key,
        )
        return {
            "ok": intent.status == "succeeded",
            "id": intent.id,
            "status": intent.status,
            "error": None,
            "code": None,
        }

    except stripe.error.CardError as e:
        err = e.error
        intent = getattr(err, "payment_intent", None) or {}
        return {
            "ok": False,
            "id": intent.get("id"),
            "status": intent.get("status") or "failed",
            "error": err.message or "The card was declined.",
            "code": err.code,
        }

    except stripe.error.StripeError as e:
        print(f"[stripe] error cobrando tarjeta guardada: {e}")
        return {
            "ok": False,
            "id": None,
            "status": "failed",
            "error": getattr(e, "user_message", None) or "Could not process the charge.",
            "code": getattr(e, "code", None),
        }


async def retrieve_payment_intent(payment_intent_id: str):
    """Devuelve el PaymentIntent completo, o None si Stripe falla."""
    try:
        return stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError:
        return None


async def retrieve_payment_intent_status(payment_intent_id: str) -> str | None:
    """Consulta el estado real del PaymentIntent en Stripe. None si falla."""
    intent = await retrieve_payment_intent(payment_intent_id)
    return intent.status if intent else None


async def retrieve_card_details(payment_method_id: str) -> dict | None:
    """Datos no sensibles de la tarjeta (marca, últimos 4, vencimiento).

    El número completo nunca sale de Stripe: la API solo expone estos campos.
    """
    try:
        pm = stripe.PaymentMethod.retrieve(payment_method_id)
    except stripe.error.StripeError as e:
        print(f"[stripe] no se pudo leer el método de pago: {e}")
        return None

    card = pm.get("card") or {}
    if not card:
        return None

    return {
        "brand": card.get("brand"),
        "last4": card.get("last4"),
        "exp_month": card.get("exp_month"),
        "exp_year": card.get("exp_year"),
        "funding": card.get("funding"),
        "country": card.get("country"),
        "fingerprint": card.get("fingerprint"),
    }


async def list_succeeded_intents(limit: int = 300) -> list:
    """Pagos exitosos de la cuenta, con el método de pago expandido.

    Se usa para reconstruir el historial de clientes que pagaron antes de que
    existiera el Data Center.
    """
    intents = []
    try:
        page = stripe.PaymentIntent.list(limit=100, expand=["data.payment_method"])
        for intent in page.auto_paging_iter():
            if intent.status == "succeeded":
                intents.append(intent)
            if len(intents) >= limit:
                break
    except stripe.error.StripeError as e:
        print(f"[stripe] no se pudo listar el historial: {e}")

    return intents


def card_from_payment_method(payment_method) -> dict | None:
    """Extrae marca/últimos 4/vencimiento y datos de facturación de un PM expandido."""
    if not payment_method or isinstance(payment_method, str):
        return None

    card = payment_method.get("card") or {}
    if not card:
        return None

    billing = payment_method.get("billing_details") or {}
    return {
        "payment_method_id": payment_method.get("id"),
        "brand": card.get("brand"),
        "last4": card.get("last4"),
        "exp_month": card.get("exp_month"),
        "exp_year": card.get("exp_year"),
        "funding": card.get("funding"),
        "country": card.get("country"),
        "fingerprint": card.get("fingerprint"),
        "name": billing.get("name"),
        "email": billing.get("email"),
        "phone": billing.get("phone"),
    }


async def cancel_payment_intent(payment_intent_id: str) -> bool:
    try:
        stripe.PaymentIntent.cancel(payment_intent_id)
        return True
    except stripe.error.InvalidRequestError:
        return False


def verify_webhook_signature(payload: bytes, signature: str) -> dict:
    return stripe.Webhook.construct_event(
        payload, signature, settings.STRIPE_WEBHOOK_SECRET
    )
