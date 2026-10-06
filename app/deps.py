"""Dependencias de seguridad: administrador autenticado y control por rol."""
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models_canonico as M
from app.database import fijar_contexto, get_db
from app.errors import forbidden, unauthorized
from app.security import decode_access_token


# Declara el esquema Bearer en OpenAPI (botón «Authorize» de /docs). auto_error=False
# para que la ausencia o el formato incorrecto del token respondan con el error
# estándar de la API (401 UNAUTHENTICATED) y no con el de FastAPI.
_bearer = HTTPBearer(auto_error=False, description="Access token de POST /auth/login")


async def get_current_admin(request: Request,
                            db: Annotated[AsyncSession, Depends(get_db)],
                            cred: Annotated[HTTPAuthorizationCredentials | None,
                                            Depends(_bearer)] = None) -> M.AdminUser:
    if cred is None or cred.scheme.lower() != "bearer":
        raise unauthorized()
    try:
        payload = decode_access_token(cred.credentials.strip())
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


async def permisos_del_rol(db: AsyncSession, role_code: str) -> dict[str, str]:
    """{módulo: 'read' | 'write'} del rol, leído de admin.admin_role_permissions.

    La matriz de la spec (2.3) vive en la base; scripts/audit_roles.py comprueba que
    la API la respete. 'write' incluye la lectura.
    """
    P = M.AdminRolePermissions
    filas = await db.execute(select(P.module, P.access).where(P.role_code == role_code))
    return dict(filas.all())


def require(module: str, write: bool = False):
    """Factoría de dependencia: exige acceso de lectura o escritura sobre un módulo."""

    async def checker(request: Request, admin: CurrentAdmin, db: Db) -> M.AdminUser:
        permisos = getattr(request.state, "permisos", None)
        if permisos is None:  # una consulta por petición, aunque haya varias comprobaciones
            permisos = request.state.permisos = await permisos_del_rol(db, admin.role_code)
        acceso = permisos.get(module)
        if acceso is None or (write and acceso != "write"):
            raise forbidden()
        return admin

    return Depends(checker)
