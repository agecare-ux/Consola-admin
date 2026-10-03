"""Revisa, sin modificar nada, en qué estado está una base respecto del modelo canónico.

Sirve para saber si a una base (por ejemplo la de Neon) le falta aplicar el DDL,
sembrar el esquema canónico o crear el rol de la API, antes de desplegar.

Uso (PowerShell):
    $env:ADMIN_DATABASE_URL = "postgresql://neondb_owner:CLAVE@HOST/neondb?sslmode=require"
    python -m scripts.verificar_base

Solo ejecuta SELECT. Conviene usar la URL del propietario: con el rol de la API
la seguridad por fila ocultaría filas y los conteos saldrían en cero.
"""
import asyncio
import os
import sys

import asyncpg

from scripts.aplicar_modelo import normalizar, ssl_para

ESPERADO_TABLAS = 58
ESPERADO_POLITICAS = 45


async def contar(conn, sql: str):
    try:
        return await conn.fetchval(sql)
    except asyncpg.PostgresError:
        return None


async def main(url: str) -> int:
    try:
        conn = await asyncpg.connect(normalizar(url), ssl=ssl_para(url), timeout=30)
    except Exception as e:
        print(f"No se pudo conectar: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    try:
        usuario = await conn.fetchval("select current_user")
        esquema = await conn.fetchval("select count(*) from pg_namespace where nspname = 'admin'")
        tablas = await contar(conn, "select count(*) from pg_class c join pg_namespace n "
                              "on n.oid = c.relnamespace where n.nspname = 'admin' "
                              "and c.relkind in ('r','p') and not c.relispartition")
        politicas = await contar(conn, "select count(*) from pg_policies where schemaname = 'admin'")
        tenants = await contar(conn, "select count(*) from admin.tenants") if esquema else None
        staff = await contar(conn, "select count(*) from admin.admin_users") if esquema else None
        tickets = await contar(conn, "select count(*) from admin.support_tickets") if esquema else None
        rol_grupo = await conn.fetchval("select count(*) from pg_roles where rolname = 'agecare_admin_api'")
        logins_api = await conn.fetch(
            "select r.rolname from pg_roles r join pg_auth_members m on m.member = r.oid "
            "join pg_roles g on g.oid = m.roleid where g.rolname = 'agecare_admin_api' and r.rolcanlogin")
        transicion = await contar(conn, "select has_schema_privilege('agecare_admin_api','public','USAGE')") \
            if rol_grupo else None
    finally:
        await conn.close()

    def linea(ok, texto):
        print(f"  [{'ok' if ok else '--'}] {texto}")

    print(f"Conectado como: {usuario}\n")
    linea(esquema == 1, f"Esquema admin: {'existe' if esquema else 'NO existe'}")
    linea(tablas == ESPERADO_TABLAS, f"Tablas en admin: {tablas} (esperadas {ESPERADO_TABLAS})")
    linea(politicas == ESPERADO_POLITICAS, f"Políticas RLS: {politicas} (esperadas {ESPERADO_POLITICAS})")
    linea(bool(tenants), f"Tenants: {tenants}")
    linea(bool(staff), f"Cuentas de staff en admin.admin_users: {staff}")
    linea(bool(tickets), f"Tickets en admin.support_tickets: {tickets}")
    linea(bool(logins_api), "Rol de login de la API: "
          + (", ".join(r["rolname"] for r in logins_api) if logins_api else "no existe"))
    linea(bool(transicion), f"Permisos de transición sobre public: {'sí' if transicion else 'no'}")

    print()
    if not esquema or tablas != ESPERADO_TABLAS:
        print("Falta el DDL:      python -m scripts.aplicar_modelo")
    if esquema and not staff:
        print("Falta el seed:     python -m scripts.seed_canonico")
    if not logins_api or not transicion:
        print('Falta rol/permisos: python -m scripts.aplicar_modelo --rol-api "agecare_api:CLAVE"')
    if esquema and tablas == ESPERADO_TABLAS and staff and logins_api and transicion:
        print("La base está lista para la versión con auth migrada.")
    return 0


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ADMIN_DATABASE_URL")
    if not destino:
        print("Define ADMIN_DATABASE_URL o pasa la URL como argumento.", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(destino)))
