"""Sección 10 — Catálogos del marketplace."""
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select, text

from app import models_canonico as M
from app.audit import audit, tenant_de
from app.deps import Db, require
from app.enums import CaregiverStatus, ContentStatus
from app.errors import conflict, invalid, not_found
from app.schemas.common import Page
from app.schemas.operation import (CaregiverOut, CaregiverPatchIn, ProductCreateIn, ProductOut,
                                   ProductPatchIn)
from app.security import now_utc
from app.staff import nombres_de_staff

router = APIRouter(prefix="/marketplace", tags=["Catálogos marketplace"])
CP, P = M.CaregiverProfile, M.Product


def _cg_out(c: M.CaregiverProfile, nombres: dict, include_note: bool = False) -> CaregiverOut:
    return CaregiverOut(caregiver_id=c.caregiver_id, name=c.display_name, zone=c.zone,
                        specialties=c.specialties or [], languages=c.languages or [],
                        certifications_count=c.certifications_count,
                        certifications_verified_count=c.certifications_verified_count,
                        rating_avg=float(c.rating_avg) if c.rating_avg is not None else None,
                        reviews_count=c.reviews_count, status=CaregiverStatus(c.status),
                        submitted_at=c.submitted_at, reviewed_by_name=nombres.get(c.reviewed_by),
                        internal_note=c.internal_note if include_note else None)


def _product_out(p: M.Product) -> ProductOut:
    # La API conserva el nombre price_clp (modelo, 7.1); la columna es price_amount.
    return ProductOut(id=p.id, name=p.name, category=p.category, vendor=p.vendor,
                      price_clp=p.price_amount, external_url=p.external_url,
                      image_url=p.image_url, status=ContentStatus(p.status), updated_at=p.updated_at)


# ---------- 10.1 Listar cuidadoras ----------
@router.get("/caregivers", response_model=Page[CaregiverOut], dependencies=[require("marketplace")])
async def list_caregivers(request: Request, db: Db,
                          status_f: CaregiverStatus | None = Query(default=None, alias="status"),
                          zone: str | None = None,
                          specialty: str | None = None,
                          q: str | None = Query(default=None, max_length=120),
                          page: int = Query(default=1, ge=1),
                          page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(CP).where(CP.tenant_id == tenant_de(request))
    if status_f:
        stmt = stmt.where(CP.status == status_f.value)
    if zone:
        stmt = stmt.where(CP.zone.ilike(f"%{zone}%"))
    if specialty:
        # specialties es text[]: se filtra en la base, antes de paginar (para que el
        # total sea correcto), sin distinguir mayúsculas.
        stmt = stmt.where(text("EXISTS (SELECT 1 FROM unnest(admin.marketplace_caregivers.specialties) s "
                               "WHERE lower(s) = lower(:especialidad))")
                          .bindparams(especialidad=specialty))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(CP.display_name.ilike(like) | CP.email.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(CP.submitted_at.desc(), CP.caregiver_id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    nombres = await nombres_de_staff(db, [c.reviewed_by for c in rows])
    return Page(items=[_cg_out(c, nombres) for c in rows], page=page, page_size=page_size, total=total)


# ---------- 10.2 Aprobar / suspender / anotar ----------
@router.patch("/caregivers/{caregiver_id}", response_model=CaregiverOut)
async def patch_caregiver(caregiver_id: UUID, body: CaregiverPatchIn, request: Request, db: Db,
                          admin: M.AdminUser = require("marketplace", write=True)):
    c = await db.get(CP, caregiver_id)
    if c is None or c.tenant_id != tenant_de(request):
        raise not_found()
    before = {"status": c.status}
    if body.status is not None:
        if body.status == CaregiverStatus.approved and c.certifications_verified_count < 1:
            raise conflict("CERTIFICATION_REQUIRED",
                           "No puede aprobarse un perfil sin certificación verificada.")
        if body.status == CaregiverStatus.suspended and not body.reason:
            raise invalid("REASON_REQUIRED", "Para suspender un perfil debes indicar el motivo.")
        c.status = body.status.value
        c.status_reason = body.reason
        c.reviewed_by = admin.id
        c.reviewed_at = now_utc()
        # Al suspender se notificaría a la cuidadora con el motivo.
    if body.internal_note is not None:
        c.internal_note = body.internal_note
    await audit(db, request, "marketplace.caregiver_update", "caregiver_profile", c.caregiver_id,
                before=before, after={"status": c.status})
    await db.flush()
    await db.refresh(c)
    return _cg_out(c, await nombres_de_staff(db, [c.reviewed_by]), include_note=True)


# ---------- 10.3 Listar artículos ----------
@router.get("/products", response_model=Page[ProductOut], dependencies=[require("marketplace")])
async def list_products(request: Request, db: Db,
                        category: str | None = None,
                        status_f: ContentStatus | None = Query(default=None, alias="status"),
                        q: str | None = Query(default=None, max_length=120),
                        page: int = Query(default=1, ge=1),
                        page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(P).where(P.tenant_id == tenant_de(request))
    if category:
        stmt = stmt.where(P.category.ilike(f"%{category}%"))
    if status_f:
        stmt = stmt.where(P.status == status_f.value)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(P.name.ilike(like) | P.vendor.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(P.updated_at.desc(), P.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[_product_out(p) for p in rows], page=page, page_size=page_size, total=total)


def _fijar_estado(p: M.Product, estado: ContentStatus) -> None:
    """El modelo exige published_at / archived_at según el estado."""
    p.status = estado.value
    if estado == ContentStatus.published and p.published_at is None:
        p.published_at = now_utc()
    if estado == ContentStatus.archived:
        p.archived_at = now_utc()
    else:
        p.archived_at = None


# ---------- 10.4 Crear artículo ----------
@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(body: ProductCreateIn, request: Request, db: Db,
                         admin: M.AdminUser = require("marketplace", write=True)):
    if body.external_url.scheme != "https":
        raise invalid("INSECURE_URL", "El enlace externo debe usar https.")
    p = P(tenant_id=tenant_de(request), name=body.name, category=body.category, vendor=body.vendor,
          price_amount=body.price_clp, external_url=str(body.external_url),
          image_url=str(body.image_url) if body.image_url else None,
          created_by=admin.id, updated_by=admin.id)
    db.add(p)
    await db.flush()
    await db.refresh(p)
    await audit(db, request, "marketplace.product_create", "product", p.id, after={"name": p.name})
    return _product_out(p)


# ---------- 10.5 Editar / archivar artículo ----------
@router.patch("/products/{product_id}", response_model=ProductOut)
async def patch_product(product_id: UUID, body: ProductPatchIn, request: Request, db: Db,
                        admin: M.AdminUser = require("marketplace", write=True)):
    p = await db.get(P, product_id)
    if p is None or p.tenant_id != tenant_de(request):
        raise not_found()
    before = {"status": p.status, "name": p.name}
    if body.external_url is not None:
        if body.external_url.scheme != "https":
            raise invalid("INSECURE_URL", "El enlace externo debe usar https.")
        p.external_url = str(body.external_url)
    for field in ("name", "category", "vendor"):
        v = getattr(body, field)
        if v is not None:
            setattr(p, field, v)
    if body.price_clp is not None:
        p.price_amount = body.price_clp
    if body.image_url is not None:
        p.image_url = str(body.image_url)
    if body.status is not None:
        _fijar_estado(p, body.status)
    p.updated_by = admin.id
    await db.flush()
    await db.refresh(p)  # updated_at lo pone el trigger
    await audit(db, request, "marketplace.product_update", "product", p.id, before=before,
                after={"status": p.status, "name": p.name})
    return _product_out(p)
