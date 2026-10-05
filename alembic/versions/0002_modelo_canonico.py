"""Modelo de datos canónico: crea el esquema admin con sus 58 tablas.

Revision ID: 0002
Revises: —
Create Date: 2026-09-24

Aplica modelo/agecare_admin_ddl.sql tal cual, sin traducirlo a operaciones de
Alembic. La razón es que el DDL no es solo tablas: trae 45 triggers, 45 políticas
de seguridad por fila, 19 funciones, particiones y roles. Reescribir todo eso en
Python sería duplicar la fuente de verdad y garantizar que las dos versiones se
desincronicen. El documento del modelo lo deja claro: el DDL manda y el código se
adapta.

El DDL es idempotente, así que esta migración se puede aplicar sobre una base que
ya lo tenga sin romper nada.

Es la primera revisión: la 0001, que creaba las tablas del prototipo en `public`,
se eliminó al cerrar la fase 3 (la API ya no las usa). Las bases que la tenían
aplicada siguen en la 0002 y no requieren nada; para borrar esas tablas está
scripts/retirar_prototipo.py.
"""
from pathlib import Path

from alembic import op
from sqlalchemy.util import await_only

revision = "0002"
down_revision = None
branch_labels = None
depends_on = None

DDL = Path(__file__).resolve().parent.parent.parent / "modelo" / "agecare_admin_ddl.sql"


def _sin_metacomandos(sql: str) -> str:
    """Quita las directivas de psql (\\set, \\echo), que no son SQL."""
    return "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("\\"))


def upgrade() -> None:
    if not DDL.exists():
        raise FileNotFoundError(
            f"No se encuentra {DDL}. La migración necesita el DDL canónico del "
            "directorio modelo/, que va versionado con el proyecto.")
    sql = _sin_metacomandos(DDL.read_text(encoding="utf-8"))

    # exec_driver_sql() no vale aquí: usa sentencias preparadas y asyncpg no admite
    # varias sentencias en una sola. Hay que pasarle el script a la conexión cruda de
    # asyncpg, que usa el protocolo simple. await_only() permite llamarla desde este
    # contexto síncrono, porque Alembic ya corre dentro del greenlet de SQLAlchemy.
    cruda = op.get_bind().connection.driver_connection
    await_only(cruda.execute(sql))


def downgrade() -> None:
    # Se lleva por delante tablas, triggers, funciones y políticas del esquema.
    # Los roles son globales al servidor y no cuelgan del esquema, así que quedan.
    op.get_bind().exec_driver_sql("DROP SCHEMA IF EXISTS admin CASCADE")
