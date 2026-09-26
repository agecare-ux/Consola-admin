"""Aplica el modelo de datos canónico a una base PostgreSQL, sin necesitar psql.

El instalador de PostgreSQL en Windows no añade psql al PATH, y pelearse con eso
cada vez que alguien del equipo necesita levantar el esquema no aporta nada. Este
script usa asyncpg, que ya es una dependencia del proyecto, así que funciona igual
en Windows, macOS y Linux.

Uso:
    set ADMIN_DATABASE_URL=postgresql+asyncpg://usuario:clave@host/neondb?ssl=require
    python -m scripts.aplicar_modelo            # aplica el DDL
    python -m scripts.aplicar_modelo --tests    # aplica el DDL y luego sus pruebas
    python -m scripts.aplicar_modelo --solo-tests
    python -m scripts.aplicar_modelo --url "postgresql://..."

Acepta la URL en cualquiera de las dos formas: la de asyncpg (`postgresql+asyncpg://`
con `ssl=require`) o la que entrega Neon para psql (`postgresql://` con `sslmode` y
`channel_binding`). Se normaliza sola.

El DDL es idempotente: aplicarlo dos veces no da error ni duplica nada.
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

RAIZ = Path(__file__).resolve().parent.parent
DDL = RAIZ / "modelo" / "agecare_admin_ddl.sql"
PRUEBAS = RAIZ / "modelo" / "agecare_admin_ddl_tests.sql"


def normalizar(url: str) -> str:
    """Deja la URL en la forma que entiende asyncpg.

    Quita el sufijo +asyncpg del esquema y descarta los parámetros de consulta:
    sslmode y channel_binding hacen fallar a asyncpg con un TypeError, y el cifrado
    se pide aparte con ssl='require' al conectar.
    """
    url = url.strip().strip('"').strip("'")
    url = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


def sin_metacomandos(sql: str) -> str:
    """Quita las directivas de psql, que empiezan por barra invertida.

    Los archivos traen \\set ON_ERROR_STOP, \\set QUIET y \\echo. Son instrucciones
    para el cliente psql, no SQL, y asyncpg las rechaza con un error de sintaxis.
    Ninguna afecta al esquema: la parada ante el primer error ya la damos nosotros
    al no capturar la excepción.
    """
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("\\"))


async def ejecutar(conn: asyncpg.Connection, archivo: Path, etiqueta: str,
                   deshacer: bool = False) -> list[str]:
    """Ejecuta un archivo .sql entero y devuelve los avisos que emitió.

    Con deshacer=True todo ocurre dentro de una transacción que se revierte al
    terminar. Es lo que se usa para las pruebas del DDL: comprueban las reglas
    insertando tenants, cuentas y tickets de mentira, y sin revertir dejarían esas
    filas en la base. Revirtiendo, las pruebas se pueden repetir cuantas veces haga
    falta y son seguras incluso sobre una base que ya tiene datos.
    """
    avisos: list[str] = []
    # asyncpg entrega los RAISE NOTICE como PostgresLogMessage; el texto está en
    # .message, no en str(), que devuelve la representación del objeto.
    conn.add_log_listener(lambda _c, msg: avisos.append(getattr(msg, "message", str(msg))))
    print(f"  aplicando {etiqueta} ({archivo.stat().st_size // 1024} KB)...", flush=True)
    sql = sin_metacomandos(archivo.read_text(encoding="utf-8"))
    if not deshacer:
        await conn.execute(sql)
        return avisos
    tr = conn.transaction()
    await tr.start()
    try:
        await conn.execute(sql)
    finally:
        await tr.rollback()
    return avisos


async def principal(url: str, con_pruebas: bool, solo_pruebas: bool) -> int:
    destino = normalizar(url)
    visible = re.sub(r"://[^:]+:[^@]+@", "://***:***@", destino)
    print(f"Destino: {visible}")

    try:
        conn = await asyncpg.connect(destino, ssl="require", timeout=30)
    except Exception as e:
        print(f"\nNo se pudo conectar.\n  {type(e).__name__}: {e}", file=sys.stderr)
        print("  Revisa que ADMIN_DATABASE_URL apunte al endpoint directo (sin -pooler)"
              " y que la contraseña sea la correcta.", file=sys.stderr)
        return 1

    try:
        if not solo_pruebas:
            await ejecutar(conn, DDL, "el DDL canónico")
            tablas = await conn.fetchval(
                "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'admin' and c.relkind in ('r','p') and not c.relispartition")
            politicas = await conn.fetchval("select count(*) from pg_policies where schemaname = 'admin'")
            print(f"  hecho: {tablas} tablas y {politicas} políticas de seguridad en el esquema admin")

        if con_pruebas or solo_pruebas:
            avisos = await ejecutar(conn, PRUEBAS, "las pruebas del DDL", deshacer=True)
            ok = [a for a in avisos if a.startswith("OK")]
            mal = [a for a in avisos if "FALLO" in a.upper()]
            for a in ok:
                print(f"    {a}")
            for a in mal:
                print(f"    {a}")
            print(f"  pruebas: {len(ok)} correctas, {len(mal)} fallidas "
                  f"(los datos de prueba se revirtieron)")
            if mal:
                return 1
    except asyncpg.PostgresError as e:
        print(f"\nError de PostgreSQL:\n  {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        await conn.close()

    print("\nListo.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Aplica el modelo canónico a una base PostgreSQL.")
    ap.add_argument("--url", help="URL de conexión. Si no se indica, se usa ADMIN_DATABASE_URL.")
    ap.add_argument("--tests", action="store_true", help="Ejecutar las pruebas después del DDL.")
    ap.add_argument("--solo-tests", action="store_true", help="Ejecutar solo las pruebas.")
    args = ap.parse_args()

    import os
    destino = args.url or os.environ.get("ADMIN_DATABASE_URL")
    if not destino:
        print("Falta la URL. Define ADMIN_DATABASE_URL o pasa --url.", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(principal(destino, args.tests, args.solo_tests)))
