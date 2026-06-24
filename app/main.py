import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import Base, engine
from app.routers import admin, api, auth, client, webhooks

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_light_migrations():
    """Para bases ya existentes: agrega columnas nuevas sin borrar datos.
    Idempotente. Soporta PostgreSQL y SQLite."""
    dialect = engine.dialect.name

    if dialect == "postgresql":
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

    elif dialect == "sqlite":
        _migrate_sqlite()


def _migrate_sqlite():
    """SQLite no soporta ALTER COLUMN ni ADD COLUMN IF NOT EXISTS.
    Detecta desfases del esquema (columna faltante o NOT NULL obsoleto) y,
    si es necesario, reconstruye la tabla con el esquema del modelo sin perder datos.
    """
    from app.models.payment_link import PaymentLink

    with engine.begin() as conn:
        # Limpia cualquier resto de una migración anterior interrumpida.
        conn.execute(text("DROP TABLE IF EXISTS payment_links_old"))

        info = list(conn.execute(text("PRAGMA table_info(payment_links)")))
        if not info:
            return  # tabla aún no existe; create_all ya la creó con el esquema correcto

        old_cols = [row[1] for row in info]  # row = (cid, name, type, notnull, dflt, pk)
        notnull = {row[1]: row[3] for row in info}

        missing_email = "customer_email" not in old_cols
        phone_is_notnull = notnull.get("phone_number", 0) == 1

        if not missing_email and not phone_is_notnull:
            return  # esquema al día

        # Reconstrucción: renombrar, crear tabla nueva (esquema del modelo), copiar, borrar.
        new_cols = [c.name for c in PaymentLink.__table__.columns]
        common = [c for c in old_cols if c in new_cols]
        col_list = ", ".join(common)

        conn.execute(text("ALTER TABLE payment_links RENAME TO payment_links_old"))
        # Los índices nombrados siguen a la tabla renombrada: hay que soltarlos
        # antes de recrear la tabla para evitar choques de nombre.
        conn.execute(text("DROP INDEX IF EXISTS ix_payment_links_token"))
        PaymentLink.__table__.create(bind=conn)
        conn.execute(
            text(
                f"INSERT INTO payment_links ({col_list}) "
                f"SELECT {col_list} FROM payment_links_old"
            )
        )
        conn.execute(text("DROP TABLE payment_links_old"))
        print("[migration] tabla payment_links reconstruida (sqlite): phone_number opcional + customer_email")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_light_migrations()
    yield


app = FastAPI(
    title="Secure Payment",
    description="Secure payment link generation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_BASE_DIR, "static")),
    name="static",
)

app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(api.router)
app.include_router(admin.router)
app.include_router(client.router)
