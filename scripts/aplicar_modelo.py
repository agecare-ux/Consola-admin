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
from urllib.parse import parse_qsl, urlsplit, urlunsplit

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


def ssl_para(url: str):
    """Cifrado según el destino: obligatorio en la nube, opcional en local.

    1. Si la URL lo dice (sslmode= o ssl=, como en las cadenas de Neon), manda eso.
    2. Si no, en local (localhost o un servicio de Docker como `db`, sin punto en el
       nombre) se deja que asyncpg negocie: el PostgreSQL de Windows y la imagen de
       Docker vienen sin SSL, y pedir `require` haría fallar la conexión.
    3. Cualquier otro host remoto exige SSL.
    """
    url = url.strip().strip('"').strip("'")
    consulta = dict(parse_qsl(urlsplit(url).query))
    pedido = consulta.get("sslmode") or consulta.get("ssl")
    if pedido in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
        return pedido
    host = (urlsplit(normalizar(url)).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or "." not in host:
        return "prefer"
    return "require"


def sin_metacomandos(sql: str) -> str:
    """Quita las directivas de psql, que empiezan por barra invertida.

    Los archivos traen \\set ON_ERROR_STOP, \\set QUIET y \\echo. Son instrucciones
    para el cliente psql, no SQL, y asyncpg las rechaza con un error de sintaxis.
    Ninguna afecta al esquema; la parada ante el primer error la asegura este script
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


# Los tres roles que usan las pruebas, con los MISMOS atributos con que las pruebas
# los crearían. Importa replicarlos exactos: el fichero usa IF NOT EXISTS, así que si
# aquí se crea job_test sin BYPASSRLS, las pruebas lo dan por bueno y luego fallan al
# insertar en una tabla con seguridad por fila.
ROLES_DE_PRUEBA = [
    ("api_test", "LOGIN IN ROLE agecare_admin_api"),
    ("ro_test", "LOGIN IN ROLE agecare_admin_ro"),
    ("job_test", "LOGIN BYPASSRLS IN ROLE agecare_admin_jobs"),
]


async def preparar_roles_de_prueba(conn: asyncpg.Connection) -> None:
    """Crea los tres roles de prueba y se concede el permiso para conmutar a ellos.

    Las pruebas hacen SET ROLE api_test para comprobar que la seguridad por fila y
    los permisos por rol funcionan. En un PostgreSQL local uno suele ser superusuario
    y SET ROLE vale para cualquiera, pero en Neon el rol propietario no lo es: puede
    crear roles (tiene CREATEROLE) pero no conmutar a ellos sin que se le conceda
    explícitamente el permiso SET, que PostgreSQL 16 separa de ADMIN.

    Es best-effort: si algo falla se sigue adelante y el error real, si lo hay,
    aparecerá al ejecutar las pruebas con un mensaje más concreto.
    """
    for rol, atributos in ROLES_DE_PRUEBA:
        try:
            await conn.execute(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{rol}') "
                f"THEN CREATE ROLE {rol} {atributos}; END IF; END $$;")
            await conn.execute(f"GRANT {rol} TO CURRENT_USER WITH SET TRUE")
        except asyncpg.PostgresError:
            pass


async def crear_rol_api(conn: asyncpg.Connection, usuario: str, clave: str) -> None:
    """Crea el rol de login con el que debe conectarse la aplicación.

    El DDL activa la seguridad por fila pero no la fuerza, y en PostgreSQL el
    propietario de una tabla queda exento de sus políticas. Conectando la API como
    propietario, las 45 políticas de aislamiento no filtran nada. Este rol hereda de
    agecare_admin_api, que sí está sujeto a ellas.
    """
    await conn.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{usuario}') "
        f"THEN CREATE ROLE {usuario} LOGIN PASSWORD '{clave}' IN ROLE agecare_admin_api; "
        f"ELSE ALTER ROLE {usuario} LOGIN PASSWORD '{clave}'; END IF; END $$;")
    await conn.execute(f"GRANT agecare_admin_api TO {usuario}")
    await retirar_transicion(conn)
    print(f"  rol {usuario} listo (miembro de agecare_admin_api)")
    print("  apunta ADMIN_DATABASE_URL a ese usuario para que el aislamiento actúe")


async def retirar_transicion(conn: asyncpg.Connection) -> None:
    """Retira permisos de la API sobre `public` que pudieran quedar de versiones previas.

    La API solo debe acceder al esquema `admin`. Es idempotente: en una base sin esos
    permisos no hace nada.
    """
    await conn.execute(
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM agecare_admin_api;"
        "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM agecare_admin_api;"
        "REVOKE USAGE ON SCHEMA public FROM agecare_admin_api;")


async def preparar_particiones(conn: asyncpg.Connection, meses: int = 12) -> str:
    """Deja creadas las particiones mensuales de audit_log para el próximo año.

    El DDL solo prepara el mes anterior, el actual y dos más; sin un job que corra
    admin.partition_maintenance() cada mes, el registro de auditoría deja de aceptar
    filas al acabarse y con él fallan el login y toda acción auditada. Volver a
    ejecutar aplicar_modelo extiende el plazo. Devuelve el último mes cubierto.
    """
    await conn.execute(f"CALL admin.ensure_partitions('audit_log', 'month', {int(meses)})")
    return await conn.fetchval(
        "select to_char(max(to_date(substring(c.relname from '_p(\\d{6})$'), 'YYYYMM')), 'YYYY-MM') "
        "from pg_inherits i join pg_class c on c.oid = i.inhrelid "
        "join pg_class p on p.oid = i.inhparent join pg_namespace n on n.oid = p.relnamespace "
        "where n.nspname = 'admin' and p.relname = 'audit_log'")


async def principal(url: str, con_pruebas: bool, solo_pruebas: bool, rol_api: str | None = None) -> int:
    destino = normalizar(url)
    visible = re.sub(r"://[^:]+:[^@]+@", "://***:***@", destino)
    print(f"Destino: {visible}")

    try:
        conn = await asyncpg.connect(destino, ssl=ssl_para(destino), timeout=30)
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
            hasta = await preparar_particiones(conn)
            print(f"  registro de auditoría preparado hasta {hasta}")

        if rol_api:
            usuario, _, clave = rol_api.partition(":")
            if not clave:
                print("  --rol-api necesita el formato usuario:clave", file=sys.stderr)
                return 2
            await crear_rol_api(conn, usuario, clave)

        if con_pruebas or solo_pruebas:
            await preparar_roles_de_prueba(conn)
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
        if "set role" in str(e).lower() or "grant role" in str(e).lower():
            print("\n  Las pruebas necesitan conmutar de rol para comprobar la seguridad por fila,\n"
                  "  y el usuario de esta base no tiene ese permiso. El DDL sí se aplicó: lo que\n"
                  "  no se pudo ejecutar son las comprobaciones. Córrelas contra un PostgreSQL\n"
                  "  local, donde eres superusuario; validan el mismo SQL.", file=sys.stderr)
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
    ap.add_argument("--rol-api", metavar="USUARIO:CLAVE",
                    help="Crea un rol de login miembro de agecare_admin_api. La aplicación "
                         "debe conectarse con él: el propietario de las tablas queda exento "
                         "de la seguridad por fila y el aislamiento entre tenants no actuaría.")
    args = ap.parse_args()

    # El orden es: --url, luego la variable de entorno, y por último la configuración
    # de la aplicación, que es la única que lee el archivo .env. Sin este último paso
    # el script ignoraba el .env y pedía la URL aunque estuviera definida ahí.
    destino = args.url
    if not destino:
        import os
        destino = os.environ.get("ADMIN_DATABASE_URL")
    if not destino:
        try:
            from app.config import get_settings
            destino = get_settings().database_url
        except Exception:
            destino = None
    if not destino:
        print("Falta la URL. Pásala con --url, define ADMIN_DATABASE_URL, o ponla "
              "como ADMIN_DATABASE_URL en el archivo .env del proyecto.", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(principal(destino, args.tests, args.solo_tests, args.rol_api)))
