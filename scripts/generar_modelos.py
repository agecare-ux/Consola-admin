"""Regenera app/models_canonico.py a partir de una base con el modelo canónico aplicado.

El DDL es la fuente de verdad. Estos modelos lo reflejan, así que no se editan a
mano: si el DDL cambia, se aplica a una base limpia y se vuelve a ejecutar esto.

Uso:
    python -m scripts.generar_modelos                     # usa ADMIN_CANONICO_URL o la local
    python -m scripts.generar_modelos --url "postgresql://..."

Requiere sqlacodegen y psycopg2-binary, que están en requirements-dev.txt.

Qué hace además de generar:
  - mapea solo las 58 tablas lógicas, dejando fuera las particiones;
  - renombra quince clases a los nombres que ya usan los routers, para que la fase 3
    sean cambios de columna y no de nombre;
  - declara una Base propia, separada de la del prototipo, para que las dos metadatas
    no se mezclen mientras conviven.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "app" / "models_canonico.py"
POR_DEFECTO = "postgresql://postgres:postgres@127.0.0.1:5432/canonico"

# Tabla canónica -> nombre de clase que ya usan los routers del prototipo.
RENOMBRES = {
    "admin_sessions": "AdminSession",
    "admin_users": "AdminUser",
    "content_items": "ContentItem",
    "features": "Feature",
    "legal_versions": "LegalVersion",
    "marketplace_caregivers": "CaregiverProfile",
    "marketplace_products": "Product",
    "moderation_items": "ModerationItem",
    "ops_component_state": "ComponentState",
    "ops_critical_process_state": "CriticalProcessState",
    "ops_incidents": "Incident",
    "ops_latency_window": "LatencyWindow",
    "support_ticket_replies": "TicketReply",
    "support_tickets": "Ticket",
    "system_settings": "SystemSetting",
}

CABECERA = '''"""Modelos del esquema canónico `admin` (58 tablas).

ARCHIVO GENERADO. No editar a mano: se regenera con

    python -m scripts.generar_modelos

a partir de la base creada por modelo/agecare_admin_ddl.sql, que es la fuente de
verdad. Los modelos la reflejan, no al revés.

Estado: fase 1 de la migración. Todavía NO lo usa la aplicación, que sigue sobre
app/models.py (esquema del prototipo, 22 tablas sin tenant). El cambio de uno a otro
se hace en la fase 3, junto con la adaptación de los routers, para que la rama siga
funcionando mientras tanto.

Quince clases llevan el nombre que ya usa el código (AdminUser, Ticket, TicketReply,
ContentItem, Product, CaregiverProfile, ModerationItem, SystemSetting, LegalVersion,
Incident, Feature, ComponentState, LatencyWindow, CriticalProcessState, AdminSession)
para que la fase 3 sea sobre todo cambios de columna y no de nombre.

Diferencia principal con el prototipo: casi todas las tablas llevan tenant_id, y el
esquema impone por trigger las reglas que hoy validamos en Python (transiciones de
estado, bloqueo optimista, inmutabilidad del registro de auditoría, moderación única).
"""
'''


def tablas_logicas(url: str) -> list[str]:
    """Las tablas del esquema admin, excluyendo las particiones."""
    import psycopg2
    with psycopg2.connect(url.replace("postgresql+psycopg2", "postgresql")) as cn, cn.cursor() as cur:
        cur.execute(
            "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'admin' and c.relkind in ('r','p') and not c.relispartition "
            "order by 1")
        return [f[0] for f in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="URL de la base con el modelo canónico aplicado.")
    args = ap.parse_args()
    url = args.url or os.environ.get("ADMIN_CANONICO_URL") or POR_DEFECTO
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", url)

    tablas = tablas_logicas(url)
    if len(tablas) != 58:
        print(f"Aviso: se esperaban 58 tablas y hay {len(tablas)}. "
              "¿Está el DDL aplicado del todo?", file=sys.stderr)

    print(f"Generando desde {len(tablas)} tablas...")
    r = subprocess.run(
        ["sqlacodegen", "--generator", "declarative", "--schemas", "admin",
         "--tables", ",".join(tablas), url.replace("postgresql://", "postgresql+psycopg2://")],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return 1
    codigo = r.stdout

    # Nombre que sqlacodegen dio a cada tabla, para poder renombrar sus clases.
    generadas = dict(re.findall(r"class (\w+)\(Base\):\s*\n\s*__tablename__ = '([a-z_]+)'", codigo))
    cambios = {clase: RENOMBRES[tabla] for clase, tabla in generadas.items() if tabla in RENOMBRES}
    for viejo, nuevo in sorted(cambios.items(), key=lambda kv: -len(kv[0])):
        codigo = re.sub(rf"\b{viejo}\b", nuevo, codigo)

    codigo = codigo.replace(
        """from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

""",
        '''from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base propia, separada de la de app/models.py.

    Compartirla mezclaría las 22 tablas del prototipo con las 58 canónicas en una
    sola metadata, y create_all() intentaría crear ambas. Se unifican en la fase 3,
    cuando el prototipo desaparezca.
    """


metadata = Base.metadata

''')

    DESTINO.write_text(CABECERA + codigo, encoding="utf-8")
    print(f"  {DESTINO.relative_to(RAIZ)}: {len(codigo.splitlines())} líneas, "
          f"{len(generadas)} clases, {len(cambios)} renombradas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
