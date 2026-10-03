"""Dependencias de seguridad: administrador autenticado y control por rol."""
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

import app.compat  # noqa: F401  (fase 3: AdminUser.role -> role_code; se elimina al cerrar)
from app import models_canonico as M
from app.database import fijar_contexto, get_db
from app.enums import READ, WRITE, AdminRole
from app.errors import forbidden, unauthorized
from app.security import decode_access_token


async def get_current_admin(request: Request,
                            db: Annotated[AsyncSession, Depends(get_db)]) -> M.AdminUser:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise unauthorized()
    try:
        payload = decode_access_token(auth.removeprefix("Bearer ").strip())
        admin_id = UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise unauthorized()
    # El tenant del token se declara antes de leer al admin: con el rol de la API,
    # la seguridad por fila solo deja ver las cuentas de ese tenant.
    request.state.tenant_id = payload.get("tenant")
    await fijar_contexto(db, tenant_id=request.state.tenant_id)
    admin = await db.get(M.AdminUser, admin_id)
    if admin is None or not admin.is_active or admin.password_hash is None:
        raise unauthorized()
    request.state.actor = admin
    # Ya se sabe quién pregunta: se declara para los triggers de historial.
    await fijar_contexto(db, actor_id=str(admin.id))
    return admin


CurrentAdmin = Annotated[M.AdminUser, Depends(get_current_admin)]
Db = Annotated[AsyncSession, Depends(get_db)]


def require(module: str, write: bool = False):
    """Factoría de dependencia: exige acceso de lectura o escritura sobre un módulo.

    La matriz sigue en app/enums.py (READ/WRITE), validada por scripts/audit_roles.py.
    Coincide con admin.admin_role_permissions; se pasará a leer de la base al migrar
    el módulo de configuración.
    """
    allowed = WRITE.get(module, set()) if write else READ.get(module, set())

    async def checker(admin: CurrentAdmin) -> M.AdminUser:
        if AdminRole(admin.role_code) not in allowed:
            raise forbidden()
        return admin

    return Depends(checker)


def permissions_for(role: AdminRole) -> list[str]:
    """Módulos accesibles (lectura) para un rol; alimenta el menú de la consola."""
    return sorted(m for m, roles in READ.items() if role in roles)
