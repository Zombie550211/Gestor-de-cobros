"""Borra los registros creados en un dia concreto: payment_links y sus charges.

Por defecto NO borra nada: solo lista lo que borraria. Hay que pasar
--confirmar para que escriba. Usa la DATABASE_URL de la app, asi que corriendolo
en el shell de Render apunta directo a la base de produccion.

    python borrar_datos_del_dia.py                       # dry-run del dia de hoy (UTC)
    python borrar_datos_del_dia.py --offset-horas -6     # dry-run del dia en UTC-6
    python borrar_datos_del_dia.py --confirmar           # borra de verdad

Ojo: created_at se guarda en UTC. Si tu dia no es el dia UTC, pasa
--offset-horas con tu zona (El Salvador / CST = -6) para que la ventana cuadre.

Esto borra el registro local; NO cancela ni reembolsa nada en Stripe.
"""

import argparse
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select

from app.database import SessionLocal
from app.models.charge import Charge
from app.models.payment_link import PaymentLink


def ventana_utc(dia, offset_horas):
    """Rango [inicio, fin) en UTC que cubre `dia` completo en una zona UTC+offset."""
    inicio_local = datetime.combine(dia, datetime.min.time())
    inicio = inicio_local - timedelta(hours=offset_horas)
    return inicio, inicio + timedelta(days=1)


def recolectar(db, inicio, fin):
    """Devuelve (links, charges) a borrar.

    Incluye los charges creados en la ventana y tambien los que cuelgan de un
    link creado en la ventana, para no dejar huerfanos ni romper la foreign key.
    """
    links = db.scalars(
        select(PaymentLink).where(
            PaymentLink.created_at >= inicio, PaymentLink.created_at < fin
        )
    ).all()

    condiciones = [(Charge.created_at >= inicio) & (Charge.created_at < fin)]
    ids_links = [link.id for link in links]
    if ids_links:
        condiciones.append(Charge.payment_link_id.in_(ids_links))
    charges = db.scalars(select(Charge).where(or_(*condiciones))).all()

    return links, charges


def main():
    parser = argparse.ArgumentParser(
        description="Borra los payment_links y charges creados en un dia."
    )
    parser.add_argument(
        "--fecha", help="Dia a borrar en formato YYYY-MM-DD (por defecto: hoy en UTC)."
    )
    parser.add_argument(
        "--offset-horas",
        type=float,
        default=0.0,
        help="Tu zona horaria respecto de UTC. Ej: -6 para El Salvador. Default 0 (UTC).",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Sin este flag solo se muestra lo que se borraria.",
    )
    args = parser.parse_args()

    dia = date.fromisoformat(args.fecha) if args.fecha else datetime.utcnow().date()
    inicio, fin = ventana_utc(dia, args.offset_horas)

    db = SessionLocal()
    try:
        links, charges = recolectar(db, inicio, fin)

        print(f"Dia objetivo: {dia} (offset {args.offset_horas:+g}h)")
        print(f"Ventana UTC:  {inicio} -> {fin}")
        print()

        print(f"charges a borrar: {len(charges)}")
        for c in charges:
            print(f"  {c.created_at}  {c.amount} {c.currency}  {c.status}  {c.id}")

        print(f"payment_links a borrar: {len(links)}")
        for link in links:
            tarjeta = f"{link.card_brand} ...{link.card_last4}" if link.card_last4 else "sin tarjeta"
            print(
                f"  {link.created_at}  {link.amount} {link.currency}  {link.status}"
                f"  {link.customer_name}  {tarjeta}  {link.id}"
            )

        if not links and not charges:
            print("\nNo hay nada que borrar en esa ventana.")
            return

        if not args.confirmar:
            print("\nDRY-RUN: no se borro nada. Repeti el comando con --confirmar.")
            return

        for c in charges:
            db.delete(c)
        db.flush()  # los hijos primero, si no la foreign key se queja
        for link in links:
            db.delete(link)
        db.commit()
        print(f"\nBorrado: {len(charges)} charges y {len(links)} payment_links.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
