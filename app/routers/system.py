"""Secciones 12, 13 y 14 — Configuración, legales y auditoría (esquema canónico)."""
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request
from jsonschema import Draft202012Validator
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import audit, tenant_de
from app.deps import Db, require
from app.enums import LegalDocType
from app.errors import ApiError, conflict, invalid, not_found
from app.schemas.common import Page
from app.schemas.system import (AuditEntryOut, LegalCurrentOut, LegalDocumentOut,
                                LegalDocumentsOut, LegalDraftOut, LegalVersionCreateIn,
                                LegalVersionOut, SettingOut, SettingPutIn, SettingsOut)
from app.security import now_utc
from app.staff import nombres_de_staff

router = APIRouter(tags=["Sistema"])

MAJOR_NOTICE_DAYS = 15
S, D, L, A = M.SystemSetting, M.SettingDefinitions, M.LegalVersion, M.AuditLog
UNKNOWN_SETTING = (404, "UNKNOWN_SETTING", "No existe ningún parámetro con esa clave.")


def _setting_out(s: M.SystemSetting, d: M.SettingDefinitions, nombres: dict) -> SettingOut:
    # El esquema y la descripción son del catálogo (setting_definitions), común a
    # todos los tenants; el valor y su versión, del tenant.
    return SettingOut(key=s.key, value=s.value, schema=d.value_schema, description=d.description,
                      updated_by={"admin_id": str(s.updated_by), "name": nombres.get(s.updated_by)}
                      if s.updated_by else None,
                      updated_at=s.updated_at, version=s.version)


# ---------- 12.1 Leer configuración ----------
@router.get("/settings", response_model=SettingsOut, dependencies=[require("settings")])
async def get_settings_endpoint(request: Request, db: Db, key: str | None = Query(default=None)):
    stmt = select(S, D).join(D, D.key == S.key).where(S.tenant_id == tenant_de(request))
    if key:
        stmt = stmt.where(S.key == key)
    rows = (await db.execute(stmt.order_by(S.key))).all()
    if key and not rows:
        raise ApiError(*UNKNOWN_SETTING)
    nombres = await nombres_de_staff(db, [s.updated_by for s, _ in rows])
    return SettingsOut(settings=[_setting_out(s, d, nombres) for s, d in rows])


# ---------- 12.2 Modificar parámetro ----------
@router.put("/settings/{key}", response_model=SettingOut)
async def put_setting(key: str, body: SettingPutIn, request: Request, db: Db,
                      admin: M.AdminUser = require("settings", write=True)):
    fila = (await db.execute(select(S, D).join(D, D.key == S.key)
                             .where(S.tenant_id == tenant_de(request), S.key == key))).first()
    if fila is None:
        raise ApiError(*UNKNOWN_SETTING)
    s, d = fila
    if body.version != s.version:
        raise conflict("VERSION_CONFLICT", "El parámetro fue modificado por otra persona. Recarga y aplica de nuevo.")
    errors = sorted(Draft202012Validator(d.value_schema).iter_errors(body.value), key=str)
    if errors:
        details = [{"field": "/".join(str(p) for p in e.path) or key, "issue": e.message} for e in errors]
        raise invalid("INVALID_VALUE", "El valor no cumple el esquema del parámetro. Revisa error.details.", details)
    before = {"value": s.value, "version": s.version}
    s.value = body.value
    s.version += 1  # el trigger trg_settings_version exige exactamente +1
    s.change_note = body.change_note
    s.updated_by = admin.id
    await db.flush()
    await db.refresh(s)  # updated_at lo pone el trigger
    # La propagación real usa caché con TTL de 60 s; los servicios no requieren reinicio.
    await audit(db, request, "settings.update", "system_setting", None,
                before=before, after={"key": key, "value": s.value, "version": s.version,
                                      "note": body.change_note})
    return _setting_out(s, d, {admin.id: admin.full_name})


# ---------- 13.1 Documentos legales ----------
def _semver_tuple(v: str) -> tuple[int, int]:
    major, minor = v.split(".")
    return int(major), int(minor)


@router.get("/legal/documents", response_model=LegalDocumentsOut, dependencies=[require("legal")])
async def legal_documents(request: Request, db: Db, doc_type: LegalDocType | None = Query(default=None)):
    tenant = tenant_de(request)
    types = [doc_type] if doc_type else list(LegalDocType)
    rows = (await db.execute(select(L).where(L.tenant_id == tenant,
                                             L.doc_type.in_([t.value for t in types]))
                             .order_by(L.created_at.desc()))).scalars().all()
    nombres = await nombres_de_staff(db, [r.created_by for r in rows if r.status == "draft"])
    docs = []
    for t in types:
        del_tipo = [r for r in rows if r.doc_type == t.value]
        published = [r for r in del_tipo if r.status == "published"]
        current = max(published, key=lambda r: (r.semver_major, r.semver_minor)) if published else None
        docs.append(LegalDocumentOut(
            doc_type=t,
            current=LegalCurrentOut(version_id=current.id, semver=current.semver,
                                    published_at=current.published_at,
                                    effective_date=current.effective_date,
                                    requires_reacceptance=current.requires_reacceptance)
            if current else None,
            drafts=[LegalDraftOut(version_id=r.id, semver=r.semver,
                                  created_by_name=nombres.get(r.created_by), updated_at=r.updated_at)
                    for r in del_tipo if r.status == "draft"]))
    return LegalDocumentsOut(documents=docs)


# ---------- 13.2 Crear versión ----------
@router.post("/legal/documents/{doc_type}/versions", response_model=LegalVersionOut, status_code=201)
async def create_legal_version(doc_type: LegalDocType, body: LegalVersionCreateIn,
                               request: Request, db: Db,
                               admin: M.AdminUser = require("legal", write=True)):
    tenant = tenant_de(request)
    rows = (await db.execute(select(L).where(L.tenant_id == tenant, L.doc_type == doc_type.value))
            ).scalars().all()
    nueva = _semver_tuple(body.semver)
    published = [r for r in rows if r.status in ("published", "superseded")]
    current = max(published, key=lambda r: (r.semver_major, r.semver_minor)) if published else None
    vigente = (current.semver_major, current.semver_minor) if current else None
    if (vigente and nueva <= vigente) or any((r.semver_major, r.semver_minor) == nueva for r in rows):
        raise conflict("SEMVER_NOT_GREATER", "La versión debe ser mayor que la vigente.")
    requires_reacceptance = vigente is None or nueva[0] > vigente[0]
    if requires_reacceptance and body.effective_date < date.today() + timedelta(days=MAJOR_NOTICE_DAYS):
        raise invalid("NOTICE_PERIOD",
                      "Un cambio mayor exige una fecha de vigencia con al menos 15 días de aviso.")
    v = L(tenant_id=tenant, doc_type=doc_type.value, semver_major=nueva[0], semver_minor=nueva[1],
          content_md=body.content_md, changelog=body.changelog, effective_date=body.effective_date,
          requires_reacceptance=requires_reacceptance, created_by=admin.id)
    db.add(v)
    await db.flush()
    await db.refresh(v)  # semver es columna calculada
    await audit(db, request, "legal.version_create", "legal_version", v.id,
                after={"doc_type": doc_type.value, "semver": v.semver})
    return LegalVersionOut(version_id=v.id, doc_type=doc_type, semver=v.semver,
                           effective_date=v.effective_date,
                           requires_reacceptance=v.requires_reacceptance, status=v.status)


# ---------- 13.3 Publicar versión ----------
@router.post("/legal/versions/{version_id}/publish", response_model=LegalVersionOut)
async def publish_legal_version(version_id: UUID, request: Request, db: Db,
                                admin: M.AdminUser = require("legal", write=True)):
    v = await db.get(L, version_id)
    if v is None or v.tenant_id != tenant_de(request):
        raise not_found()
    if v.status != "draft":
        raise conflict("ALREADY_PUBLISHED", "Esta versión ya está publicada.")
    if v.effective_date < date.today():
        raise conflict("EFFECTIVE_DATE_PAST",
                       "La fecha de vigencia ya pasó; crea una versión nueva con fecha futura.")
    v.status = "published"
    v.published_at = now_utc()
    v.published_by = admin.id
    # La versión anterior sigue publicada hasta que esta entra en vigor (effective_date);
    # entonces pasa a superseded. Nunca se borra: los consentimientos la referencian.
    await db.flush()
    await db.refresh(v)  # semver y updated_at los recalcula la base
    await audit(db, request, "legal.version_publish", "legal_version", v.id,
                after={"semver": v.semver})
    return LegalVersionOut(version_id=v.id, doc_type=LegalDocType(v.doc_type), semver=v.semver,
                           effective_date=v.effective_date,
                           requires_reacceptance=v.requires_reacceptance,
                           status=v.status, published_at=v.published_at)


# ---------- 14.1 Auditoría ----------
@router.get("/audit-log", response_model=Page[AuditEntryOut], dependencies=[require("audit")])
async def audit_log(request: Request, db: Db,
                    actor_id: UUID | None = None,
                    action: str | None = None,
                    entity_type: str | None = None,
                    entity_id: UUID | None = None,
                    date_from: datetime | None = None,
                    date_to: datetime | None = None,
                    page: int = Query(default=1, ge=1),
                    page_size: int = Query(default=25, ge=1, le=100)):
    if date_from and date_to and (date_to - date_from).days > 90:
        raise invalid("RANGE_TOO_WIDE", "El rango temporal no puede superar 90 días. Acótalo.")
    stmt = select(A).where(A.tenant_id == tenant_de(request))
    if actor_id:
        stmt = stmt.where(A.actor_id == actor_id)
    if action:
        stmt = stmt.where(A.action == action)
    if entity_type:
        stmt = stmt.where(A.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(A.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(A.created_at >= date_from)
    if date_to:
        stmt = stmt.where(A.created_at <= date_to)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(A.created_at.desc(), A.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[AuditEntryOut(
        id=r.id,
        actor={"admin_id": str(r.actor_id) if r.actor_id else None,
               "name": r.actor_name, "role": r.actor_role},
        action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
        before=r.before, after=r.after, ip=str(r.ip) if r.ip is not None else None,
        user_agent=r.user_agent, created_at=r.created_at) for r in rows],
        page=page, page_size=page_size, total=total)
