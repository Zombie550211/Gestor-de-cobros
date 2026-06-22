import smtplib
from email.message import EmailMessage

from app.config import settings


def send_payment_email(
    to_email: str,
    customer_name: str,
    amount: float,
    payment_url: str,
    expires_in: str,
) -> bool:
    """Envía el link de pago por correo (SMTP). Devuelve True si se envió."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        print("[Email] SMTP no configurado (SMTP_USER/SMTP_PASSWORD vacíos)")
        return False

    first_name = customer_name.split()[0] if customer_name else "Customer"
    from_email = settings.FROM_EMAIL or settings.SMTP_USER

    msg = EmailMessage()
    msg["Subject"] = f"Secure payment request — ${amount:.2f}"
    msg["From"] = f"{settings.FROM_NAME} <{from_email}>"
    msg["To"] = to_email

    # Versión de texto plano (respaldo)
    msg.set_content(
        f"{settings.FROM_NAME}\n\n"
        f"Hello {first_name},\n\n"
        f"You have a secure payment request.\n\n"
        f"Amount: ${amount:.2f}\n\n"
        f"Pay securely:\n{payment_url}\n\n"
        f"This payment link expires in {expires_in}.\n\n"
        f"Thank you."
    )

    # Versión HTML con botón
    msg.add_alternative(
        f"""\
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
            <p style="font-size:13px;color:#6b7280;margin:0 0 6px;">Or copy this link:</p>
            <p style="font-size:13px;color:#0a84ff;word-break:break-all;margin:0 0 18px;">{payment_url}</p>
            <p style="font-size:13px;color:#6b7280;margin:0;">This payment link expires in {expires_in}.</p>
          </td></tr>
          <tr><td style="background:#f4f6f9;padding:16px 28px;font-size:12px;color:#9ca3af;">
            Powered by Stripe. Your card information is never stored by us.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>""",
        subtype="html",
    )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Email] Error al enviar: {e}")
        return False
