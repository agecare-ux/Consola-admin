"""Sección 3: reglas de cuentas y sesiones.

Cubre cuentas pendientes, bloqueo persistido, familias de sesiones, revocación con
motivo, segundo factor y trazabilidad en audit_log. Las comprobaciones de base se hacen como propietario,
que ve las tablas sin filtro de tenant.
"""
import os
import uuid

import pyotp
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from scripts.datos_demo import MFA_SECRET_DEMO

BASE = "/api/v1/admin"
pytestmark = pytest.mark.asyncio


async def _sql(consulta: str, **params):
    eng = create_async_engine(os.environ["ADMIN_DATABASE_URL"], poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            return (await conn.execute(text(consulta), params)).all()
    finally:
        await eng.dispose()


async def _login(client, email, password, otp=None):
    body = {"email": email, "password": password}
    if otp:
        body["otp_code"] = otp
    return await client.post(f"{BASE}/auth/login", json=body)


async def test_cuenta_pendiente_crea_invitacion_y_login_da_admin_disabled(client, admin_headers):
    email = f"pend{uuid.uuid4().hex[:6]}@wellq.co.uk"
    r = await client.post(f"{BASE}/users", headers=admin_headers,
                          json={"full_name": "Pendiente Prueba", "email": email, "role": "admin"})
    assert r.status_code == 201, r.text
    nuevo = r.json()

    filas = await _sql("select u.mfa_required, u.mfa_enabled, u.password_hash, i.expires_at "
                       "from admin.admin_users u join admin.admin_invitations i on i.admin_id = u.id "
                       "where u.id = :id", id=nuevo["id"])
    assert len(filas) == 1
    mfa_required, mfa_enabled, password_hash, _ = filas[0]
    assert mfa_required is True and mfa_enabled is False  # admin => MFA exigido al activar
    assert password_hash is None

    r = await _login(client, email, "Cualquiera123!")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ADMIN_DISABLED"


async def test_dominio_validado_contra_parametro_de_la_base(client, admin_headers):
    # wellq.co está en la configuración por defecto, pero el parámetro sembrado en
    # system_settings solo admite wellq.co.uk: manda la base.
    r = await client.post(f"{BASE}/users", headers=admin_headers,
                          json={"full_name": "Otro Dominio", "email": "x@wellq.co", "role": "support"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "DOMAIN_NOT_ALLOWED"


async def test_bloqueo_tras_cinco_fallos_persistido(client):
    email = "moderador@wellq.co.uk"
    for _ in range(5):
        r = await _login(client, email, "MalaClave1!")
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    r = await _login(client, email, "Moderador123!")  # incluso con la clave correcta
    assert r.status_code == 423
    assert r.json()["error"]["code"] == "ACCOUNT_LOCKED"

    intentos = await _sql("select failure_code from admin.admin_login_attempts "
                          "where email = :e order by id", e=email)
    codigos = [c for (c,) in intentos]
    assert codigos[-6:] == ["INVALID_CREDENTIALS"] * 5 + ["ACCOUNT_LOCKED"]


async def test_rotacion_mantiene_familia_y_reuso_revoca_todo(client):
    l1 = (await _login(client, "editora@wellq.co.uk", "Editora123!")).json()
    l2 = (await _login(client, "editora@wellq.co.uk", "Editora123!")).json()  # otra sesión
    r = await client.post(f"{BASE}/auth/refresh", json={"refresh_token": l1["refresh_token"]})
    assert r.status_code == 200

    filas = await _sql("select family_id, rotated_from, revoked_reason from admin.admin_sessions s "
                       "join admin.admin_users u on u.id = s.admin_id "
                       "where u.email = 'editora@wellq.co.uk' order by s.created_at, s.id")
    familias = {f for f, _, _ in filas}
    assert len(familias) == 2  # dos logins, dos familias; la rotación no crea otra
    assert any(rf is not None for _, rf, _ in filas)

    # Reusar el token ya rotado revoca todas las sesiones del admin (spec 3.2).
    r = await client.post(f"{BASE}/auth/refresh", json={"refresh_token": l1["refresh_token"]})
    assert r.json()["error"]["code"] == "INVALID_REFRESH"
    r = await client.post(f"{BASE}/auth/refresh", json={"refresh_token": l2["refresh_token"]})
    assert r.status_code == 401
    vivas = await _sql("select count(*) from admin.admin_sessions s join admin.admin_users u "
                       "on u.id = s.admin_id where u.email = 'editora@wellq.co.uk' "
                       "and s.revoked_at is null")
    assert vivas[0][0] == 0


async def test_segundo_factor(client):
    email, clave = "admin.mfa@wellq.co.uk", "AdminMfa123!"
    r = await _login(client, email, clave)
    assert r.json()["error"]["code"] == "OTP_REQUIRED"
    r = await _login(client, email, clave, otp="000000")
    assert r.json()["error"]["code"] == "OTP_INVALID"
    r = await _login(client, email, clave, otp=pyotp.TOTP(MFA_SECRET_DEMO).now())
    assert r.status_code == 200, r.text


async def test_desactivar_revoca_sesiones_con_motivo_y_audita(client, admin_headers):
    r = await _login(client, "soporte@wellq.co.uk", "Soporte123!")
    assert r.status_code == 200
    soporte_id = r.json()["admin"]["id"]
    r = await client.patch(f"{BASE}/users/{soporte_id}", headers=admin_headers,
                           json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False

    motivos = await _sql("select distinct revoked_reason from admin.admin_sessions "
                         "where admin_id = :id and revoked_at is not null", id=soporte_id)
    assert ("admin_disabled",) in motivos
    auditoria = await _sql("select tenant_id, actor_role, request_id from admin.audit_log "
                           "where action = 'staff.update' and entity_id = :id", id=soporte_id)
    assert auditoria and all(t is not None and rid is not None for t, _, rid in auditoria)
    assert auditoria[0][1] == "admin"

    r = await client.patch(f"{BASE}/users/{soporte_id}", headers=admin_headers,
                           json={"is_active": True})
    assert r.status_code == 200
