"""Secciones 6 (KPIs de soporte) y 8 — Tickets de soporte (esquema canónico)."""
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import audit, tenant_de
from app.deps import Db, require
from app.enums import (CATEGORY_NAMES, AppRole, TicketCategory, TicketChannel, TicketPriority,
                       TicketStatus)
from app.errors import ApiError, conflict, not_found
from app.schemas.common import Page
from app.schemas.support import (Assignee, ByCategoryOut, CategoryRow, Csat, ReplyCreateIn,
                                 ReplyOut, Requester, SupportDeltas, SupportSummaryOut,
                                 TicketCreateIn, TicketDetailOut, TicketOut, TicketPatchIn)
from app.security import now_utc
from app.staff import nombres_de_staff

router = APIRouter(prefix="/support", tags=["Soporte"])
T, R, C = M.Ticket, M.TicketReply, M.SupportCsatSurveys

# La máquina de estados (8.4) vive en admin.ticket_status_transitions y la aplica el
# trigger trg_transition, que además fija resolved_at / closed_at y cuenta las
# reaperturas. La API consulta la misma tabla para responder el error de la spec.
# first_response_at también lo fija un trigger, con la primera respuesta pública.


async def _transicion_valida(db, actual: str, destino: str) -> bool:
    S = M.TicketStatusTransitions
    return (await db.execute(select(S.from_status).where(
        S.from_status == actual, S.to_status == destino))).first() is not None


async def _nombres_agentes(db, tickets) -> dict:
    """{admin_id: nombre} de los agentes asignados (una consulta para toda la página)."""
    return await nombres_de_staff(db, [t.assigned_to for t in tickets])


def _ticket_out(t: M.Ticket, agentes: dict) -> TicketOut:
    return TicketOut(
        id=t.id, number=t.number, subject=t.subject,
        requester=Requester(user_id=t.requester_user_id, name=t.requester_name,
                            role=AppRole(t.requester_role_code) if t.requester_role_code else None,
                            email=t.requester_email),
        category=TicketCategory(t.category_code), priority=TicketPriority(t.priority),
        status=TicketStatus(t.status),
        assigned_to=Assignee(admin_id=t.assigned_to, name=agentes.get(t.assigned_to, ""))
        if t.assigned_to else None,
        channel=TicketChannel(t.channel), created_at=t.created_at, updated_at=t.updated_at,
        first_response_at=t.first_response_at)


def _reply_out(r: M.TicketReply) -> ReplyOut:
    return ReplyOut(id=r.id, ticket_id=r.ticket_id, author_type=r.author_type,
                    author_name=r.author_name, body=r.body, internal=r.is_internal,
                    created_at=r.created_at)


# ---------- 6.3 KPIs ----------
@router.get("/summary", response_model=SupportSummaryOut, dependencies=[require("support")])
async def support_summary(request: Request, db: Db):
    tenant = tenant_de(request)
    now = now_utc()
    d30, d60 = now - timedelta(days=30), now - timedelta(days=60)

    async def count_status(status: TicketStatus) -> int:
        return (await db.execute(select(func.count()).select_from(T)
                                 .where(T.tenant_id == tenant, T.status == status.value))).scalar_one()

    resolved_30 = (await db.execute(select(func.count()).select_from(T)
                                    .where(T.tenant_id == tenant, T.resolved_at >= d30))).scalar_one()
    resolved_prev = (await db.execute(select(func.count()).select_from(T)
                                      .where(T.tenant_id == tenant,
                                             T.resolved_at.between(d60, d30)))).scalar_one()

    async def avg_first_response(since, until) -> float | None:
        segundos = (await db.execute(
            select(func.avg(func.extract("epoch", T.first_response_at - T.created_at)))
            .where(T.tenant_id == tenant, T.first_response_at.isnot(None),
                   T.created_at.between(since, until)))).scalar_one()
        return round(float(segundos) / 3600, 1) if segundos is not None else None

    fr_now = await avg_first_response(d30, now)
    fr_prev = await avg_first_response(d60, d30)

    # CSAT: encuestas respondidas de tickets resueltos en los últimos 30 días.
    csat_q = (await db.execute(select(func.avg(C.score), func.count(C.score))
                               .join(T, T.id == C.ticket_id)
                               .where(C.tenant_id == tenant, C.score.isnot(None),
                                      T.resolved_at >= d30))).one()
    open_now = await count_status(TicketStatus.open)
    # Aproximación de demo: el modelo no guarda cuántos tickets estaban abiertos hace
    # una semana (support_metrics_daily registra flujos, no stock).
    week_ago_open = open_now - 6

    return SupportSummaryOut(
        open=open_now,
        in_progress=await count_status(TicketStatus.in_progress),
        waiting_user=await count_status(TicketStatus.waiting_user),
        resolved_30d=resolved_30,
        first_response_hours_avg=fr_now or 0.0,
        csat_avg=round(float(csat_q[0]), 1) if csat_q[0] is not None else None,
        csat_count=csat_q[1],
        deltas=SupportDeltas(
            open_wow=open_now - week_ago_open,
            resolved_mom_pct=round((resolved_30 - resolved_prev) / resolved_prev, 4) if resolved_prev else None,
            first_response_mom_hours=round(fr_now - fr_prev, 1) if fr_now and fr_prev else None),
        computed_at=now)


# ---------- 6.4 Por categoría ----------
@router.get("/tickets/by-category", response_model=ByCategoryOut, dependencies=[require("support")])
async def by_category(request: Request, db: Db, days: int = Query(default=30, ge=1, le=365)):
    since = now_utc() - timedelta(days=days)
    rows = (await db.execute(select(T.category_code, func.count())
                             .where(T.tenant_id == tenant_de(request), T.created_at >= since)
                             .group_by(T.category_code)
                             .order_by(func.count().desc(), T.category_code))).all()
    total = sum(c for _, c in rows)
    return ByCategoryOut(days=days, total=total,
                         categories=[CategoryRow(category=TicketCategory(cat),
                                                 name=CATEGORY_NAMES[TicketCategory(cat)],
                                                 count=c, share=round(c / total, 4) if total else 0.0)
                                     for cat, c in rows])


# ---------- 8.1 Listar ----------
@router.get("/tickets", response_model=Page[TicketOut], dependencies=[require("support")])
async def list_tickets(request: Request, db: Db,
                       status_f: TicketStatus | None = Query(default=None, alias="status"),
                       priority: TicketPriority | None = None,
                       category: TicketCategory | None = None,
                       role: AppRole | None = None,
                       assigned_to: UUID | None = None,
                       q: str | None = Query(default=None, max_length=120),
                       order: str = Query(default="-created_at"),
                       page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(T).where(T.tenant_id == tenant_de(request))
    if status_f:
        stmt = stmt.where(T.status == status_f.value)
    if priority:
        stmt = stmt.where(T.priority == priority.value)
    if category:
        stmt = stmt.where(T.category_code == category.value)
    if role:
        stmt = stmt.where(T.requester_role_code == role.value)
    if assigned_to:
        stmt = stmt.where(T.assigned_to == assigned_to)
    if q:
        like = f"%{q.lstrip('#')}%"
        cond = T.subject.ilike(like) | T.requester_email.ilike(like)
        if q.lstrip("#").isdigit():
            cond = cond | (T.number == int(q.lstrip("#")))
        stmt = stmt.where(cond)
    field = order.lstrip("-")
    col = {"created_at": T.created_at, "updated_at": T.updated_at,
           "priority": T.priority}.get(field, T.created_at)
    stmt = stmt.order_by(col.desc() if order.startswith("-") else col.asc(), T.number)
    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    agentes = await _nombres_agentes(db, rows)
    return Page(items=[_ticket_out(t, agentes) for t in rows],
                page=page, page_size=page_size, total=total)


async def _get_ticket(db, request: Request, ticket_id: str) -> M.Ticket:
    tenant = tenant_de(request)
    t = None
    raw = ticket_id.lstrip("#")
    if raw.isdigit():
        t = (await db.execute(select(T).where(T.tenant_id == tenant, T.number == int(raw)))
             ).scalar_one_or_none()
    else:
        try:
            t = await db.get(T, UUID(raw))
        except ValueError:
            t = None
        if t is not None and t.tenant_id != tenant:
            t = None
    if t is None:
        raise not_found()
    return t


# ---------- 8.2 Detalle ----------
@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut, dependencies=[require("support")])
async def ticket_detail(ticket_id: str, request: Request, db: Db):
    t = await _get_ticket(db, request, ticket_id)
    replies = (await db.execute(select(func.count()).select_from(R)
                                .where(R.ticket_id == t.id))).scalar_one()
    encuesta = (await db.execute(select(C).where(C.ticket_id == t.id))).scalar_one_or_none()
    base = _ticket_out(t, await _nombres_agentes(db, [t])).model_dump()
    return TicketDetailOut(**base, description=t.description,
                           requester_context=t.requester_context, replies_count=replies,
                           csat=Csat(score=encuesta.score, comment=encuesta.comment)
                           if encuesta is not None and encuesta.score is not None else None)


# ---------- 8.3 Crear ----------
@router.post("/tickets", response_model=TicketOut, status_code=201)
async def create_ticket(body: TicketCreateIn, request: Request, db: Db,
                        admin: M.AdminUser = require("support", write=True)):
    tenant = tenant_de(request)
    email = body.user_email.lower()
    # La consola no tiene acceso a la tabla de usuarios de la app. Se reconoce al
    # usuario por un ticket previo enlazado a su cuenta (requester_user_id); un ticket
    # previo creado sin enlazar no prueba que la cuenta exista.
    prev = (await db.execute(select(T).where(T.tenant_id == tenant, T.requester_email == email,
                                             T.requester_user_id.isnot(None))
                             .order_by(T.created_at.desc()).limit(1))).scalar_one_or_none()
    if prev is None and not body.confirm_unlinked:
        raise ApiError(404, "USER_NOT_FOUND",
                       "No existe ningún usuario con ese correo. Verifícalo o crea el ticket sin enlazar "
                       "(confirm_unlinked = true).")
    t = T(tenant_id=tenant, subject=body.subject, description=body.description,
          requester_user_id=prev.requester_user_id if prev else None,
          requester_name=prev.requester_name if prev else email.split("@")[0],
          requester_email=email,
          requester_role_code=prev.requester_role_code if prev else None,
          requester_plan_code=prev.requester_plan_code if prev else None,
          category_code=body.category.value, priority=body.priority.value,
          status=TicketStatus.open.value, channel=body.channel.value,
          created_by=admin.id)  # el número lo asigna el trigger (correlativo por tenant)
    db.add(t)
    await db.flush()
    await db.refresh(t)
    await audit(db, request, "ticket.create", "ticket", t.id, after={"number": t.number})
    return _ticket_out(t, {})


# ---------- 8.4 Actualizar ----------
@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def patch_ticket(ticket_id: str, body: TicketPatchIn, request: Request, db: Db,
                       admin: M.AdminUser = require("support", write=True)):
    t = await _get_ticket(db, request, ticket_id)
    before = {"status": t.status, "priority": t.priority, "assigned_to": str(t.assigned_to)}
    if body.status is not None and body.status.value != t.status:
        if not await _transicion_valida(db, t.status, body.status.value):
            msg = ("Transición de estado no permitida (p. ej. un ticket cerrado no puede reabrirse; "
                   "crea uno nuevo).")
            raise conflict("INVALID_TRANSITION", msg)
        t.status = body.status.value
        # Aquí se enviaría la encuesta CSAT al usuario al resolver (push/correo).
    if body.priority is not None:
        t.priority = body.priority.value
    if body.category is not None:
        t.category_code = body.category.value
    if "assigned_to" in body.model_fields_set:
        if body.assigned_to is not None:
            agente = await db.get(M.AdminUser, body.assigned_to)
            if (agente is None or agente.tenant_id != t.tenant_id or not agente.is_active
                    or agente.password_hash is None):
                raise ApiError(404, "ASSIGNEE_NOT_FOUND", "El agente indicado no existe o está desactivado.")
        t.assigned_to = body.assigned_to
    await db.flush()
    await db.refresh(t)  # los triggers fijan fechas, reaperturas y updated_at
    await audit(db, request, "ticket.update", "ticket", t.id, before=before,
                after={"status": t.status, "priority": t.priority, "assigned_to": str(t.assigned_to)})
    return _ticket_out(t, await _nombres_agentes(db, [t]))


# ---------- 8.5 Responder ----------
@router.post("/tickets/{ticket_id}/replies", response_model=ReplyOut, status_code=201)
async def create_reply(ticket_id: str, body: ReplyCreateIn, request: Request, db: Db,
                       admin: M.AdminUser = require("support", write=True)):
    t = await _get_ticket(db, request, ticket_id)
    if t.status == TicketStatus.closed.value:
        raise conflict("TICKET_CLOSED", "El ticket está cerrado y no admite nuevas respuestas.")
    reply = R(tenant_id=t.tenant_id, ticket_id=t.id, author_type="admin", author_admin_id=admin.id,
              author_name=admin.full_name, body=body.body, is_internal=body.internal)
    db.add(reply)
    await db.flush()
    await db.refresh(reply)
    # Aquí se notificaría al usuario por push y correo si la respuesta es pública.
    await audit(db, request, "ticket.reply", "ticket", t.id, after={"internal": body.internal})
    return _reply_out(reply)


# ---------- 8.6 Conversación ----------
@router.get("/tickets/{ticket_id}/replies", response_model=Page[ReplyOut], dependencies=[require("support")])
async def list_replies(ticket_id: str, request: Request, db: Db,
                       page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=25, ge=1, le=100)):
    t = await _get_ticket(db, request, ticket_id)
    stmt = select(R).where(R.ticket_id == t.id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(R.created_at, R.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[_reply_out(r) for r in rows], page=page, page_size=page_size, total=total)
