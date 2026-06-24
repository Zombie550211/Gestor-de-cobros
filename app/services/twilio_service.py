from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import settings


def format_expires_in(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes"
    if minutes == 60:
        return "1 hour"
    if minutes < 1440:
        hours = minutes // 60
        return f"{hours} hours"
    days = minutes // 1440
    return f"{days} day{'s' if days > 1 else ''}"


def send_payment_sms(
    to_number: str,
    customer_name: str,
    amount: float,
    payment_url: str,
    expires_in: str,
) -> bool:
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        first_name = customer_name.split()[0] if customer_name else "Customer"
        body = (
            f"{settings.FROM_NAME}\n\n"
            f"Hello {first_name},\n\n"
            f"You have a secure payment request.\n\n"
            f"Amount: ${amount:.2f}\n\n"
            f"Pay securely:\n{payment_url}\n\n"
            f"This payment link expires in {expires_in}.\n\n"
            f"Thank you."
        )
        message = client.messages.create(
            body=body,
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_number,
        )
        return bool(message.sid)
    except TwilioRestException as e:
        print(f"[Twilio] SMS error: {e}")
        return False
