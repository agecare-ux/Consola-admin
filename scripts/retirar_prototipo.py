"""Borra de una base las tablas del prototipo que quedaron en el esquema `public`.

La API solo usa el esquema `admin`. Las bases creadas con la primera versión de la
consola conservan en `public` las 22 tablas de entonces, que ya no se usan; este
script las elimina.

    python -m scripts.retirar_prototipo             # solo muestra qué borraría
    python -m scripts.retirar_prototipo --confirmar # las borra

CUIDADO: no ejecutarlo sobre la base de producción mientras `main` siga corriendo
el código del prototipo, porque esa versión todavía lee estas tablas.

Usa la URL de ADMIN_DATABASE_URL (o --url) y conviene la del propietario: el rol de
la API no tiene permisos sobre `public`. Nunca toca el esquema `admin`.
"""
import argparse
import asyncio
import os
import sys

import asyncpg

from scripts.aplicar_modelo import normalizar, ssl_para

# Nombres exactos de las tablas que creaba la revisión 0001 (app/models.py).
TABLAS_PROTOTIPO = [
    "support_ticket_replies", "support_tickets", "feature_usage_window", "features",
    "legal_versions", "system_settings", "moderation_queue", "marketplace_products",
    "marketplace_caregivers", "content_items", "ops_incidents", "ops_critical_process_state",
    "ops_latency_window", "ops_component_state", "role_weekly_active", "role_activity_window",
    "metrics_plan_snapshot", "metrics_hourly_users", "metrics_daily_users", "audit_log",
    "admin_sessions", "admin_users",
]


async def principal(url: str, confirmar: bool) -> int:
    conn = await asyncpg.connect(normalizar(url), ssl=ssl_para(url), timeout=30)
    try:
        existentes = [r["tablename"] for r in await conn.fetch(
            "select tablename from pg_tables where schemaname = 'public' and tablename = any($1)",
            TABLAS_PROTOTIPO)]
        version = await conn.fetchval(
            "select to_regclass('public.alembic_version') is not null")
        if not existentes:
            print("No quedan tablas del prototipo en public. Nada que hacer.")
            return 0
        print(f"Tablas del prototipo en public: {len(existentes)}")
        for t in existentes:
            print("  -", t)
        if not confirmar:
            print("\nNo se borró nada. Repite con --confirmar para eliminarlas.")
            return 0
        async with conn.transaction():
            await conn.execute("DROP TABLE IF EXISTS "
                               + ", ".join(f"public.{t}" for t in existentes) + " CASCADE")
            if version:
                # La revisión 0001 ya no existe: se deja registrada la 0002, la actual.
                await conn.execute("UPDATE public.alembic_version SET version_num = '0002'")
        print(f"\nListo: {len(existentes)} tablas eliminadas. El esquema admin no se tocó.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Elimina las tablas del prototipo en public.")
    ap.add_argument("--url", help="URL de conexión. Si no se indica, se usa ADMIN_DATABASE_URL.")
    ap.add_argument("--confirmar", action="store_true", help="Borrar de verdad (sin esto, solo informa).")
    a = ap.parse_args()
    destino = a.url or os.environ.get("ADMIN_DATABASE_URL")
    if not destino:
        print("Define ADMIN_DATABASE_URL o usa --url.", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(principal(destino, a.confirmar)))
