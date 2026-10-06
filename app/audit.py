"""Escritura del registro de auditoría (sección 14)."""
import ipaddress
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import models_canonico as M
from app.config import get_settings

SENSITIVE_KEYS = {"password", "password_hash", "mfa_secret", "mfa_secret_enc",
                  "refresh_hash", "refresh_token_hash", "token", "token_hash"}


def _mask(data: dict | None) -> dict | None:
    if data is None:
        return None
    return {k: ("***" if k in SENSITIVE_KEYS else v) for k, v in data.items()}


def ip_de(request: Request) -> str | None:
    """IP del cliente, solo si es una dirección válida.

    La columna es `inet` y PostgreSQL rechaza cualquier otra cosa. Detrás de algunos
    proxies o en tests el host puede venir como un nombre; se guarda NULL antes que
    hacer fallar la petición por un dato de trazabilidad.
    """
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def user_agent_de(request: Request) -> str | None:
    return (request.headers.get("user-agent") or "")[:300] or None


def tenant_de(request: Request) -> UUID:
    """Tenant de la petición: el del token si hay sesión, si no el configurado."""
    return UUID(str(getattr(request.state, "tenant_id", None) or get_settings().tenant_id))


def _request_id(request: Request) -> UUID | None:
    try:
        return UUID(str(getattr(request.state, "request_id", "")))
    except ValueError:
        return None  # un X-Request-Id externo que no es UUID no se guarda


async def audit(db: AsyncSession, request: Request, action: str,
                entity_type: str | None = None, entity_id: UUID | None = None,
                before: dict | None = None, after: dict | None = None,
                actor: M.AdminUser | None = None) -> None:
    actor = actor or getattr(request.state, "actor", None)
    db.add(M.AuditLog(
        tenant_id=tenant_de(request),
        actor_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
        actor_role=actor.role_code if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=_mask(before),
        after=_mask(after),
        ip=ip_de(request),
        user_agent=user_agent_de(request),
        request_id=_request_id(request),
    ))
