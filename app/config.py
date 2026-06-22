from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://spectrum:spectrum123@localhost:5432/spectrum_payments"
    STRIPE_SECRET_KEY: str = "sk_test_placeholder"
    STRIPE_WEBHOOK_SECRET: str = "whsec_placeholder"
    STRIPE_PUBLISHABLE_KEY: str = "pk_test_placeholder"
    TWILIO_ACCOUNT_SID: str = "placeholder_sid"
    TWILIO_AUTH_TOKEN: str = "placeholder_token"
    TWILIO_FROM_NUMBER: str = "+10000000000"
    # Envío del link por correo (SMTP). Sirve para Gmail, Outlook, SendGrid, etc.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = ""
    FROM_NAME: str = "Spectrum Internet"
    APP_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "change-me-in-production"

    class Config:
        env_file = ".env"


settings = Settings()
