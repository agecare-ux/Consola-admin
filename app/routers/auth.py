"""Sección 3 — Autenticación y gestión del staff (esquema canónico `admin`)."""
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import audit, ip_de, tenant_de, user_agent_de
from app.config import get_settings
from app.database import fijar_contexto
from app.deps import CurrentAdmin, Db, permissions_for, require
from app.enums import AdminRole
from app.errors import ApiError, conflict, invalid, not_found, unauthorized
from app.schemas.auth import (AdminCreateIn, AdminCreateOut, AdminPatchIn, AdminUserOut,
                              LoginIn, LoginOut, MeOut, RefreshIn, RefreshOut)
from app.schemas.common import Page
from app.security import (as_utc, create_access_token, hash_refresh, new_refresh_token,
                          now_utc, verify_password, verify_totp)

router = APIRouter(tags=["Autenticación de staff"])

VENTANA_FALLOS = timedelta(minutes=10)  # spec 3.1: 5 fallos en 10 minutos
INVITACION_HORAS = 24                   # spec 3.5: enlace de un solo uso, 24 h
MSG_REFRESH = "La sesión no es válida o fue revocada. Inicia sesión de nuevo."


async def _revocar_sesiones(db, admin_id: UUID, motivo: str) -> None:
    """Revoca todas las sesiones vivas de un admin con el motivo indicado.

    El modelo exige que revoked_at y revoked_reason vayan siempre juntos.
    """
    sesiones = (await db.execute(select(M.AdminSession)
                                 .where(M.AdminSession.admin_id == admin_id,
                                        M.AdminSession.revoked_at.is_(None)))).scalars()
    ahora = now_utc()
    for s_ in sesiones:
        s_.revoked_at = ahora
        s_.revoked_reason = motivo


async def _fallos_recientes(db, admin: M.AdminUser) -> int:
    """Contraseñas incorrectas de esta cuenta dentro de la ventana de bloqueo.

    Se cuentan desde el más reciente de: hace 10 minutos, el último login correcto
    o el fin del último bloqueo. Así un bloqueo cumplido o un login exitoso dejan el
    contador a cero, igual que hacía el prototipo, pero el dato está persistido.
    """
    ultimo_ok = (await db.execute(
        select(func.max(M.AdminLoginAttempts.attempted_at))
        .where(M.AdminLoginAttempts.admin_id == admin.id,
               M.AdminLoginAttempts.succeeded.is_(True)))).scalar_one_or_none()
    desde = max(d for d in (now_utc() - VENTANA_FALLOS, as_utc(ultimo_ok),
                            as_utc(admin.locked_until)) if d is not None)
    return (await db.execute(
        select(func.count()).select_from(M.AdminLoginAttempts)
        .where(M.AdminLoginAttempts.admin_id == admin.id,
               M.AdminLoginAttempts.failure_code == "INVALID_CREDENTIALS",
               M.AdminLoginAttempts.attempted_at > desde))).scalar_one()


async def _dominios_permitidos(db, tenant: UUID) -> list[str]:
    """Dominios de correo admitidos para staff (parámetro allowed_email_domains).

    Si el tenant aún no tiene el parámetro sembrado, se usa el de la configuración.
    """
    valor = (await db.execute(select(M.SystemSetting.value)
                              .where(M.SystemSetting.tenant_id == tenant,
                                     M.SystemSetting.key == "allowed_email_domains"))
             ).scalar_one_or_none()
    if isinstance(valor, list) and valor:
        return [str(d).strip().lower() for d in valor]
    return get_settings().allowed_domains


async def _otros_admins_activos(db, tenant: UUID, excluir: UUID) -> int:
    return (await db.execute(
        select(func.count()).select_from(M.AdminUser)
        .where(M.AdminUser.tenant_id == tenant,
               M.AdminUser.role_code == AdminRole.admin.value,
               M.AdminUser.is_active.is_(True),
               M.AdminUser.password_hash.is_not(None),
               M.AdminUser.id != excluir))).scalar_one()


# ---------- 3.1 Login ----------
@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request, db: Db):
    s = get_settings()
    tenant = tenant_de(request)
    email = body.email.lower()
    admin = (await db.execute(select(M.AdminUser)
                              .where(M.AdminUser.tenant_id == tenant,
                                     M.AdminUser.email == email))).scalar_one_or_none()
    if admin is not None:
        await fijar_contexto(db, actor_id=str(admin.id))  # para los triggers de historial

    def registrar_intento(ok: bool, codigo: str | None = None) -> None:
        db.add(M.AdminLoginAttempts(
            tenant_id=tenant, email=email, succeeded=ok, failure_code=codigo,
            admin_id=admin.id if admin else None,
            ip=ip_de(request), user_agent=user_agent_de(request)))

    async def fallar(codigo: str, mensaje: str, http: int):
        registrar_intento(False, codigo)
        await audit(db, request, "auth.login_failed", "admin_user",
                    admin.id if admin else None, actor=admin, after={"reason": codigo})
        await db.commit()  # el intento y la auditoría persisten aunque se responda error
        raise ApiError(http, codigo, mensaje)

    if admin is None:  # mismo error que contraseña incorrecta: no revela existencia
        await fallar("INVALID_CREDENTIALS", "Correo o contraseña incorrectos.", 401)
    if admin.locked_until and as_utc(admin.locked_until) > now_utc():
        await fallar("ACCOUNT_LOCKED",
                     "Cuenta bloqueada 15 minutos por intentos fallidos repetidos.", 423)
    if admin.password_hash is None or not admin.is_active:
        # password_hash NULL = cuenta pendiente de activación (spec 3.5 y modelo).
        await fallar("ADMIN_DISABLED",
                     "Esta cuenta de administración está desactivada. Contacta a un admin.", 403)
    if not verify_password(body.password, admin.password_hash):
        fallos = await _fallos_recientes(db, admin) + 1
        if fallos >= s.max_login_attempts:
            admin.locked_until = now_utc() + timedelta(minutes=s.lockout_minutes)
            admin.failed_attempts = 0
        else:
            admin.failed_attempts = fallos
        await fallar("INVALID_CREDENTIALS", "Correo o contraseña incorrectos.", 401)
    if admin.mfa_enabled:
        if not body.otp_code:
            await fallar("OTP_REQUIRED", "Esta cuenta exige segundo factor. Envía tu código TOTP.", 401)
        # Demo: el secreto se guarda sin cifrar (ver modelo/README.md, "Secreto MFA").
        secreto = (admin.mfa_secret_enc or b"").decode()
        if not verify_totp(secreto, body.otp_code):
            await fallar("OTP_INVALID", "El código de verificación no es válido o expiró.", 401)

    admin.failed_attempts = 0
    admin.locked_until = None
    admin.last_login_at = now_utc()
    registrar_intento(True)

    token, refresh_hash, expira = new_refresh_token()
    db.add(M.AdminSession(tenant_id=tenant, admin_id=admin.id, refresh_token_hash=refresh_hash,
                          family_id=uuid4(), expires_at=expira,
                          ip=ip_de(request), user_agent=user_agent_de(request)))
    await audit(db, request, "auth.login", "admin_user", admin.id, actor=admin)
    return LoginOut(access_token=create_access_token(admin.id, admin.role_code, str(tenant)),
                    refresh_token=token, admin=admin)


# ---------- 3.2 Refresh ----------
@router.post("/auth/refresh", response_model=RefreshOut)
async def refresh(body: RefreshIn, request: Request, db: Db):
    sesion = (await db.execute(select(M.AdminSession)
                               .where(M.AdminSession.refresh_token_hash ==
                                      hash_refresh(body.refresh_token)))).scalar_one_or_none()
    if sesion is None or as_utc(sesion.expires_at) < now_utc():
        raise unauthorized(MSG_REFRESH, "INVALID_REFRESH")
    if sesion.revoked_at is not None:
        if sesion.revoked_reason == "rotated":
            # Reutilización de un token ya rotado: posible robo. La spec 3.2 pide
            # revocar todas las sesiones del admin (el modelo habla de la familia;
            # todas las sesiones la incluyen). Se confirma antes de responder el
            # error, o el rollback de la petición desharía la revocación.
            await _revocar_sesiones(db, sesion.admin_id, "reuse_detected")
            await db.commit()
        raise unauthorized(MSG_REFRESH, "INVALID_REFRESH")

    admin = await db.get(M.AdminUser, sesion.admin_id)
    if admin is None or not admin.is_active or admin.password_hash is None:
        raise unauthorized(MSG_REFRESH, "INVALID_REFRESH")

    token, refresh_hash, expira = new_refresh_token()
    sesion.revoked_at = now_utc()
    sesion.revoked_reason = "rotated"
    db.add(M.AdminSession(tenant_id=sesion.tenant_id, admin_id=admin.id,
                          refresh_token_hash=refresh_hash, family_id=sesion.family_id,
                          rotated_from=sesion.id, expires_at=expira,
                          ip=ip_de(request), user_agent=user_agent_de(request)))
    return RefreshOut(access_token=create_access_token(admin.id, admin.role_code,
                                                       str(sesion.tenant_id)),
                      refresh_token=token)


# ---------- 3.3 Logout ----------
@router.post("/auth/logout", status_code=204)
async def logout(body: RefreshIn, request: Request, db: Db, admin: CurrentAdmin):
    sesion = (await db.execute(select(M.AdminSession)
                               .where(M.AdminSession.refresh_token_hash ==
                                      hash_refresh(body.refresh_token),
                                      M.AdminSession.admin_id == admin.id))).scalar_one_or_none()
    if sesion is not None and sesion.revoked_at is None:
        sesion.revoked_at = now_utc()
        sesion.revoked_reason = "logout"
    await audit(db, request, "auth.logout", "admin_user", admin.id)
    return Response(status_code=204)


# ---------- 3.4 Me ----------
@router.get("/auth/me", response_model=MeOut)
async def me(admin: CurrentAdmin):
    rol = AdminRole(admin.role_code)
    return MeOut(id=admin.id, full_name=admin.full_name, email=admin.email,
                 role=rol, mfa_enabled=admin.mfa_enabled,
                 permissions=permissions_for(rol), last_login_at=admin.last_login_at)


# ---------- 3.5 Crear staff ----------
@router.post("/users", response_model=AdminCreateOut, status_code=201)
async def create_staff(body: AdminCreateIn, request: Request, db: Db,
                       admin: M.AdminUser = require("staff", write=True)):
    tenant = tenant_de(request)
    email = body.email.lower()
    if email.split("@")[1] not in await _dominios_permitidos(db, tenant):
        raise invalid("DOMAIN_NOT_ALLOWED",
                      "El dominio del correo no está autorizado para cuentas de administración.")
    existe = (await db.execute(select(M.AdminUser.id)
                               .where(M.AdminUser.tenant_id == tenant,
                                      M.AdminUser.email == email))).scalar_one_or_none()
    if existe:
        raise conflict("EMAIL_IN_USE", "Ya existe una cuenta de staff con ese correo.")

    exige_mfa = body.require_mfa if body.require_mfa is not None else body.role == AdminRole.admin
    # Pendiente de activación = sin contraseña. El TOTP se configura al activar, por
    # eso aquí solo se marca mfa_required; mfa_enabled exige un secreto (CHECK).
    nuevo = M.AdminUser(tenant_id=tenant, full_name=body.full_name, email=email,
                        role_code=body.role.value, mfa_required=exige_mfa,
                        mfa_enabled=False, created_by=admin.id)
    db.add(nuevo)
    await db.flush()

    token_activacion, token_hash, _ = new_refresh_token()
    expira = now_utc() + timedelta(hours=INVITACION_HORAS)
    db.add(M.AdminInvitations(tenant_id=tenant, admin_id=nuevo.id, token_hash=token_hash,
                              expires_at=expira, created_by=admin.id))
    # Aquí se enviaría token_activacion por correo (fuera del alcance de esta API).
    await audit(db, request, "staff.create", "admin_user", nuevo.id,
                after={"email": email, "role": body.role.value, "mfa_required": exige_mfa})
    return AdminCreateOut(id=nuevo.id, email=nuevo.email, role=body.role,
                          invitation_expires_at=expira)


# ---------- 3.6 Listar staff ----------
@router.get("/users", response_model=Page[AdminUserOut])
async def list_staff(request: Request, db: Db,
                     admin: M.AdminUser = require("staff"),
                     role: AdminRole | None = None,
                     is_active: bool | None = None,
                     q: str | None = Query(default=None, max_length=120),
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(M.AdminUser).where(M.AdminUser.tenant_id == tenant_de(request))
    if role:
        stmt = stmt.where(M.AdminUser.role_code == role.value)
    if is_active is not None:
        stmt = stmt.where(M.AdminUser.is_active == is_active)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(M.AdminUser.full_name.ilike(like) | M.AdminUser.email.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(M.AdminUser.created_at.desc(), M.AdminUser.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[AdminUserOut.model_validate(r) for r in rows],
                page=page, page_size=page_size, total=total)


# ---------- 3.7 Actualizar staff ----------
@router.patch("/users/{admin_id}", response_model=AdminUserOut)
async def patch_staff(admin_id: UUID, body: AdminPatchIn, request: Request, db: Db,
                      admin: M.AdminUser = require("staff", write=True)):
    tenant = tenant_de(request)
    target = await db.get(M.AdminUser, admin_id)
    if target is None or target.tenant_id != tenant:
        raise not_found()
    antes = {"full_name": target.full_name, "role": target.role_code, "is_active": target.is_active}
    es_admin_activo = target.role_code == AdminRole.admin.value and target.is_active
    if body.is_active is False and target.id == admin.id:
        raise conflict("CANNOT_DISABLE_SELF", "No puedes desactivar tu propia cuenta.")
    pierde_admin = (body.is_active is False or
                    (body.role is not None and body.role != AdminRole.admin))
    # El trigger trg_last_admin impone lo mismo en la base; se valida aquí para dar
    # el mensaje de la spec sin depender de la traducción del error.
    if es_admin_activo and pierde_admin and await _otros_admins_activos(db, tenant, target.id) == 0:
        raise conflict("LAST_ADMIN", "Debe existir al menos una cuenta activa con rol admin.")

    if body.full_name is not None:
        target.full_name = body.full_name
    if body.role is not None:
        target.role_code = body.role.value
    if body.is_active is not None:
        target.is_active = body.is_active
        if body.is_active is False:  # desactivar revoca de inmediato todas sus sesiones
            await _revocar_sesiones(db, target.id, "admin_disabled")
    await audit(db, request, "staff.update", "admin_user", target.id, before=antes,
                after={"full_name": target.full_name, "role": target.role_code,
                       "is_active": target.is_active})
    await db.flush()
    await db.refresh(target)  # updated_at lo pone el trigger
    return AdminUserOut.model_validate(target)
