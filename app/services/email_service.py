import base64
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings


def _build_subject(amount: float) -> str:
    return f"Secure payment request — ${amount:.2f}"


def _build_text(customer_name: str, amount: float, payment_url: str, expires_in: str) -> str:
    first_name = customer_name.split()[0] if customer_name else "Customer"
    return (
        f"{settings.FROM_NAME}\n\n"
        f"Hello {first_name},\n\n"
        f"You have a secure payment request.\n\n"
        f"Amount: ${amount:.2f}\n\n"
        f"Pay securely:\n{payment_url}\n\n"
        f"This payment link expires in {expires_in}.\n\n"
        f"Thank you."
    )


def _build_html(customer_name: str, amount: float, payment_url: str, expires_in: str) -> str:
    first_name = customer_name.split()[0] if customer_name else "Customer"
    return f"""\
<html>
  <body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:24px 0;">
      <tr><td align="center">
        <table width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.06);">
          <tr><td style="background:#003057;padding:20px 28px;color:#ffffff;font-size:18px;font-weight:bold;">
            {settings.FROM_NAME}
          </td></tr>
          <tr><td style="padding:28px;">
            <p style="font-size:15px;color:#1f2937;margin:0 0 14px;">Hello {first_name},</p>
            <p style="font-size:15px;color:#1f2937;margin:0 0 14px;">You have a secure payment request.</p>
            <p style="font-size:15px;color:#1f2937;margin:0 0 22px;">
              Amount: <strong style="font-size:18px;">${amount:.2f}</strong>
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 0 22px;">
              <tr><td style="border-radius:8px;background:#0a84ff;">
                <a href="{payment_url}" target="_blank"
                   style="display:inline-block;padding:14px 28px;color:#ffffff;font-size:16px;font-weight:bold;text-decoration:none;border-radius:8px;">
                  Pay securely
                </a>
              </td></tr>
            </table>
            <p style="font-size:13px;color:#6b7280;margin:0;">This payment link expires in {expires_in}.</p>
          </td></tr>
          <tr><td style="background:#f4f6f9;padding:16px 28px;font-size:12px;color:#9ca3af;">
            Powered by Stripe. Your card information is never stored by us.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def _send_via_brevo_api(to_email, customer_name, amount, payment_url, expires_in) -> bool:
    """Envía por la API HTTP de Brevo (puerto 443 — nunca bloqueado por Render)."""
    from_email = settings.FROM_EMAIL or settings.SMTP_USER
    payload = {
        "sender": {"name": settings.FROM_NAME, "email": from_email},
        "to": [{"email": to_email, "name": customer_name}],
        "subject": _build_subject(amount),
        "htmlContent": _build_html(customer_name, amount, payment_url, expires_in),
        "textContent": _build_text(customer_name, amount, payment_url, expires_in),
    }
    try:
        resp = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": settings.BREVO_API_KEY,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201):
            return True
        print(f"[Email] Brevo API rechazó ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[Email] Error API Brevo: {e}")
        return False


def _get_gmail_access_token() -> str:
    """Obtiene un access token temporal a partir del refresh token de Gmail."""
    try:
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "refresh_token": settings.GMAIL_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token", "")
        print(f"[Email] Gmail token error ({resp.status_code}): {resp.text}")
        return ""
    except Exception as e:  # noqa: BLE001
        print(f"[Email] Error obteniendo token Gmail: {e}")
        return ""


def _send_via_gmail_api(to_email, customer_name, amount, payment_url, expires_in) -> bool:
    """Envía por la API oficial de Gmail (puerto 443). Desde tu propia cuenta Gmail."""
    token = _get_gmail_access_token()
    if not token:
        return False
    from_email = settings.FROM_EMAIL or settings.SMTP_USER
    msg = EmailMessage()
    msg["Subject"] = _build_subject(amount)
    msg["From"] = f"{settings.FROM_NAME} <{from_email}>"
    msg["To"] = to_email
    msg.set_content(_build_text(customer_name, amount, payment_url, expires_in))
    msg.add_alternative(_build_html(customer_name, amount, payment_url, expires_in), subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        resp = httpx.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=20,
        )
        if resp.status_code in (200, 202):
            return True
        print(f"[Email] Gmail API rechazó ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[Email] Error API Gmail: {e}")
        return False


def _send_via_sendgrid(to_email, customer_name, amount, payment_url, expires_in) -> bool:
    """Envía por la API HTTP de SendGrid (puerto 443 — funciona en Render)."""
    from_email = settings.FROM_EMAIL or settings.SMTP_USER
    payload = {
        "personalizations": [
            {"to": [{"email": to_email, "name": customer_name}]}
        ],
        "from": {"email": from_email, "name": settings.FROM_NAME},
        "subject": _build_subject(amount),
        "content": [
            {"type": "text/plain", "value": _build_text(customer_name, amount, payment_url, expires_in)},
            {"type": "text/html", "value": _build_html(customer_name, amount, payment_url, expires_in)},
        ],
    }
    try:
        resp = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if resp.status_code in (200, 201, 202):
            return True
        print(f"[Email] SendGrid rechazó ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[Email] Error API SendGrid: {e}")
        return False


def _send_via_smtp(to_email, customer_name, amount, payment_url, expires_in) -> bool:
    """Respaldo: envío por SMTP (no funciona en Render por bloqueo de puertos)."""
    from_email = settings.FROM_EMAIL or settings.SMTP_USER
    msg = EmailMessage()
    msg["Subject"] = _build_subject(amount)
    msg["From"] = f"{settings.FROM_NAME} <{from_email}>"
    msg["To"] = to_email
    msg.set_content(_build_text(customer_name, amount, payment_url, expires_in))
    msg.add_alternative(_build_html(customer_name, amount, payment_url, expires_in), subtype="html")
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Email] Error SMTP: {e}")
        return False


def send_payment_email(
    to_email: str,
    customer_name: str,
    amount: float,
    payment_url: str,
    expires_in: str,
) -> bool:
    """Envía el link de pago por correo. Prioridad: Gmail API > SendGrid > Brevo > SMTP."""
    if settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET and settings.GMAIL_REFRESH_TOKEN:
        return _send_via_gmail_api(to_email, customer_name, amount, payment_url, expires_in)
    if settings.SENDGRID_API_KEY:
        return _send_via_sendgrid(to_email, customer_name, amount, payment_url, expires_in)
    if settings.BREVO_API_KEY:
        return _send_via_brevo_api(to_email, customer_name, amount, payment_url, expires_in)
    if settings.SMTP_USER and settings.SMTP_PASSWORD:
        return _send_via_smtp(to_email, customer_name, amount, payment_url, expires_in)
    print("[Email] No configurado: falta SENDGRID_API_KEY, BREVO_API_KEY o credenciales SMTP")
    return False
