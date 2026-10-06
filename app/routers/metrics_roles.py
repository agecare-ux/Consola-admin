"""Sección 6 (parte analítica) — Estadísticas por perfil."""
from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app import models_canonico as M
from app.audit import tenant_de
from app.deps import Db, require
from app.enums import AppRole
from app.errors import invalid
from app.schemas.metrics import (RoleSummaryRow, RolesSummaryOut, WeeklyActiveOut,
                                 WeeklySeries)
from app.security import now_utc

router = APIRouter(prefix="/metrics/roles", tags=["Perfiles"], dependencies=[require("metrics")])
ROLE_ORDER = [AppRole.family, AppRole.caregiver, AppRole.elder, AppRole.doctor]
W = M.RoleActivityWindow


# ---------- 6.1 Summary ----------
@router.get("/summary", response_model=RolesSummaryOut)
async def roles_summary(request: Request, db: Db, days: int = Query(default=30, ge=7, le=90)):
    tenant = tenant_de(request)
    # Las ventanas están precalculadas (7, 14, 30, 60, 90 según el job). Se aplica la
    # menor que cubra lo pedido (modelo, punto 9.2) y la respuesta informa cuál fue.
    disponibles = sorted((await db.execute(select(W.days_window).distinct()
                                           .where(W.tenant_id == tenant))).scalars().all())
    aplicable = next((w for w in disponibles if w >= days), None)
    if aplicable is None:
        raise invalid("INVALID_RANGE", "La ventana debe estar entre 7 y 90 días.")
    rows = (await db.execute(select(W).where(W.tenant_id == tenant, W.days_window == aplicable))
            ).scalars().all()
    rows.sort(key=lambda r: ROLE_ORDER.index(AppRole(r.app_role_code)))
    return RolesSummaryOut(
        days=aplicable,
        roles=[RoleSummaryRow(role=AppRole(r.app_role_code), active_users=r.active_users,
                              growth_8w=float(r.growth_8w),
                              sessions_per_week=float(r.sessions_per_week),
                              avg_session_seconds=r.avg_session_seconds,
                              retention_30d=float(r.retention_30d)) for r in rows],
        computed_at=max(r.computed_at for r in rows))


# ---------- 6.2 Weekly active ----------
@router.get("/weekly-active", response_model=WeeklyActiveOut)
async def weekly_active(request: Request, db: Db, weeks: int = Query(default=8)):
    if not 2 <= weeks <= 26:
        raise invalid("INVALID_RANGE", "El número de semanas debe estar entre 2 y 26.")
    tenant = tenant_de(request)
    A = M.RoleWeeklyActive
    week_starts = (await db.execute(
        select(A.week_start).distinct().where(A.tenant_id == tenant)
        .order_by(A.week_start.desc()).limit(weeks))).scalars().all()
    week_starts = sorted(week_starts)
    rows = (await db.execute(select(A).where(A.tenant_id == tenant,
                                             A.week_start.in_(week_starts)))).scalars().all()
    by = {(r.week_start, r.app_role_code): r.active_users for r in rows}
    labels = [f"S{w.isocalendar()[1]}" for w in week_starts]
    series = [WeeklySeries(role=role, values=[by.get((w, role.value), 0) for w in week_starts])
              for role in ROLE_ORDER]
    return WeeklyActiveOut(weeks=labels, series=series,
                           computed_at=max((r.computed_at for r in rows), default=now_utc()))
