"""Sección 11 — Moderación (esquema canónico)."""
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import audit, tenant_de
from app.deps import Db, require
from app.enums import ModerationItemType, ModerationStatus, RejectReason
from app.errors import conflict, invalid, not_found
from app.schemas.common import Page
from app.schemas.operation import ApproveIn, ModerationItemOut, RejectIn
from app.security import now_utc
from app.staff import nombres_de_staff

router = APIRouter(prefix="/moderation", tags=["Moderación"])
MI = M.ModerationItem


def _out(m: M.ModerationItem, nombres: dict) -> ModerationItemOut:
    reportante = None
    if m.reported_by_user_id or m.reported_by_name:
        reportante = {"user_id": str(m.reported_by_user_id) if m.reported_by_user_id else None,
                      "name": m.reported_by_name}
    return ModerationItemOut(
        id=m.id, type=ModerationItemType(m.item_type), content=m.content_snapshot,
        author={"user_id": str(m.author_user_id), "name": m.author_name, "role": m.author_role_code},
        reported_by=reportante, report_reason=m.report_reason,
        status=ModerationStatus(m.status), decided_by_name=nombres.get(m.decided_by),
        decided_at=m.decided_at, created_at=m.created_at)


async def _get_pending(db, request: Request, item_id: UUID) -> M.ModerationItem:
    m = await db.get(MI, item_id)
    if m is None or m.tenant_id != tenant_de(request):
        raise not_found()
    if m.status != ModerationStatus.pending.value:
        raise conflict("ALREADY_MODERATED", "Este elemento ya fue moderado por otra persona. Recarga la cola.")
    return m


async def _decidir(db, m: M.ModerationItem, admin: M.AdminUser) -> ModerationItemOut:
    # El trigger trg_moderation_once impide cambiar una decisión ya tomada, incluso
    # si dos moderadores deciden el mismo elemento a la vez.
    m.decided_by = admin.id
    m.decided_at = now_utc()
    await db.flush()
    await db.refresh(m)
    return _out(m, {admin.id: admin.full_name})


# ---------- 11.1 Cola ----------
@router.get("/queue", response_model=Page[ModerationItemOut], dependencies=[require("moderation")])
async def queue(request: Request, db: Db,
                type_f: ModerationItemType | None = Query(default=None, alias="type"),
                status_f: ModerationStatus = Query(default=ModerationStatus.pending, alias="status"),
                page: int = Query(default=1, ge=1),
                page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(MI).where(MI.tenant_id == tenant_de(request), MI.status == status_f.value)
    if type_f:
        stmt = stmt.where(MI.item_type == type_f.value)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    # reportes de seguridad primero, luego por antigüedad
    rows = (await db.execute(stmt.order_by(MI.is_safety_report.desc(), MI.created_at.asc(), MI.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    nombres = await nombres_de_staff(db, [m.decided_by for m in rows])
    return Page(items=[_out(m, nombres) for m in rows], page=page, page_size=page_size, total=total)


# ---------- 11.2 Aprobar ----------
@router.post("/queue/{item_id}/approve", response_model=ModerationItemOut)
async def approve(item_id: UUID, body: ApproveIn, request: Request, db: Db,
                  admin: M.AdminUser = require("moderation", write=True)):
    m = await _get_pending(db, request, item_id)
    m.status = ModerationStatus.approved.value
    m.decision_note = body.note
    # Una reseña aprobada pasaría a publicada en el marketplace; un reporte se cierra sin acción.
    await audit(db, request, "moderation.approve", "moderation_item", m.id)
    return await _decidir(db, m, admin)


# ---------- 11.3 Rechazar ----------
@router.post("/queue/{item_id}/reject", response_model=ModerationItemOut)
async def reject(item_id: UUID, body: RejectIn, request: Request, db: Db,
                 admin: M.AdminUser = require("moderation", write=True)):
    if body.reason_code == RejectReason.other and not body.note:
        raise invalid("NOTE_REQUIRED", "Con motivo «other» debes detallar la razón del rechazo.")
    m = await _get_pending(db, request, item_id)
    m.status = ModerationStatus.rejected.value
    m.reject_reason_code = body.reason_code.value
    m.decision_note = body.note
    # El autor recibiría una notificación con el motivo; 3 rechazos "offensive" en 90 días
    # escalan un caso al admin (job de reglas, fuera de esta API).
    await audit(db, request, "moderation.reject", "moderation_item", m.id,
                after={"reason": body.reason_code.value})
    return await _decidir(db, m, admin)
