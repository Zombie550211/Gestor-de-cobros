import stripe

from app.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


async def create_payment_intent(
    amount: float,
    currency: str,
    customer_name: str,
    description: str,
    token: str,
) -> dict:
    intent = stripe.PaymentIntent.create(
        amount=int(round(amount * 100)),
        currency=currency,
        description=description,
        metadata={"customer_name": customer_name, "payment_token": token},
        automatic_payment_methods={"enabled": True},
    )
    return {"id": intent.id, "client_secret": intent.client_secret}


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
