from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import Base, engine
from app.routers import admin, api, client, webhooks


def _run_light_migrations():
    """Para bases ya existentes: agrega columnas nuevas sin borrar datos.
    Idempotente y solo aplica en PostgreSQL."""
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE payment_links ADD COLUMN IF NOT EXISTS customer_email VARCHAR(255)",
        "ALTER TABLE payment_links ALTER COLUMN phone_number DROP NOT NULL",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:  # noqa: BLE001
                print(f"[migration] omitido: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_light_migrations()
    yield


app = FastAPI(
    title="Spectrum Payment Center",
    description="Secure payment link generation for Spectrum Internet services",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(webhooks.router)
app.include_router(api.router)
app.include_router(admin.router)
app.include_router(client.router)
