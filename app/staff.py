"""Consultas de apoyo sobre el staff (esquema canónico)."""
from sqlalchemy import select

from app import models_canonico as M


async def nombres_de_staff(db, ids) -> dict:
    """{admin_id: nombre} para mostrar quién creó, revisó o decidió algo.

    El modelo guarda solo el id (sin copiar el nombre en cada tabla); una consulta
    resuelve los nombres de toda una página de resultados.
    """
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict((await db.execute(select(M.AdminUser.id, M.AdminUser.full_name)
                                  .where(M.AdminUser.id.in_(ids)))).all())
