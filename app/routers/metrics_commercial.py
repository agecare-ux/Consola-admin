"""Sección 4 — Uso comercial (lectura de tablas agregadas)."""
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import tenant_de
from app.deps import Db, require
from app.enums import PLAN_NAMES, PeriodKey, PlanCode
from app.errors import invalid
from app.periods import Period, buckets_for, resolve, zona_del_tenant
from app.schemas.metrics import (BucketOut, CommercialDeltas, CommercialSummaryOut, FunnelOut,
                                 FunnelStage, PeriodOut, PlanRow, PlansOut, PlanTotals,
                                 RegistrationsOut)
from app.security import now_utc

router = APIRouter(prefix="/metrics/commercial", tags=["Uso comercial"],
                   dependencies=[require("metrics")])

INVALID_PERIOD = ("INVALID_PERIOD", "El periodo indicado no es válido. Usa uno de los valores de PeriodKey.")
D = M.MetricsDailyUsers


def _period_out(p: Period) -> PeriodOut:
    return PeriodOut(key=p.key, start_date=p.start, end_date=p.end)


async def _periodo(db, request: Request, period: PeriodKey):
    """Resuelve el periodo con el 'hoy' de la zona horaria del tenant."""
    tenant = tenant_de(request)
    tz = await zona_del_tenant(db, tenant)
    return tenant, tz, resolve(period, today=datetime.now(tz).date())


async def _range_sums(db, tenant: UUID, start: date, end: date) -> tuple[int, int, int]:
    """(signups, churned_users, downloads) en el rango [start, end].

    churned_users es la definición de churn de la spec 4.1 (bajas explícitas más
    inactivos), que el modelo guarda aparte de las bajas explícitas (cancellations).
    """
    q = await db.execute(
        select(func.coalesce(func.sum(D.signups), 0),
               func.coalesce(func.sum(D.churned_users), 0),
               func.coalesce(func.sum(D.downloads), 0))
        .where(D.tenant_id == tenant, D.day.between(start, end)))
    return tuple(q.one())


async def _latest_row(db, tenant: UUID, on_or_before: date) -> M.MetricsDailyUsers | None:
    q = await db.execute(select(D).where(D.tenant_id == tenant, D.day <= on_or_before)
                         .order_by(D.day.desc()).limit(1))
    return q.scalar_one_or_none()


def _pct(cur: float, prev: float) -> float | None:
    if prev <= 0:
        return None
    return round((cur - prev) / prev, 4)


# ---------- 4.1 Summary ----------
@router.get("/summary", response_model=CommercialSummaryOut)
async def commercial_summary(request: Request, db: Db, period: PeriodKey = Query(...)):
    tenant, _, p = await _periodo(db, request, period)
    signups, churned, downloads = await _range_sums(db, tenant, p.start, p.end)
    latest = await _latest_row(db, tenant, p.end)
    if latest is None:
        raise invalid(*INVALID_PERIOD)

    prev = p.previous()
    prev_signups, _, _ = await _range_sums(db, tenant, prev.start, prev.end)
    prev_latest = await _latest_row(db, tenant, prev.end)
    start_row = await _latest_row(db, tenant, p.start - timedelta(days=1))
    active_at_start = start_row.active_users_eod if start_row else latest.active_users_eod

    return CommercialSummaryOut(
        period=_period_out(p),
        downloads=downloads,
        new_users=signups,
        churned_users=churned,
        churn_rate=round(churned / active_at_start, 4) if active_at_start else 0.0,
        active_users=latest.active_users_eod,
        paying_users=latest.paying_users_eod,
        paying_share=round(latest.paying_users_eod / latest.active_users_eod, 4)
        if latest.active_users_eod else 0.0,
        mrr_clp=latest.mrr_amount,  # la API conserva el nombre mrr_clp (modelo, 7.1)
        deltas=CommercialDeltas(
            new_users_pct=_pct(signups, prev_signups),
            mrr_pct=_pct(latest.mrr_amount, prev_latest.mrr_amount) if prev_latest else None,
            active_users_pct=_pct(latest.active_users_eod, prev_latest.active_users_eod)
            if prev_latest else None,
        ),
        computed_at=latest.computed_at,
    )


# ---------- 4.2 Registrations ----------
@router.get("/registrations", response_model=RegistrationsOut)
async def registrations(request: Request, db: Db, period: PeriodKey = Query(...)):
    tenant, tz, p = await _periodo(db, request, period)

    if p.granularity == "hour":
        # El día en curso empieza a medianoche local del tenant; ts_hour está en UTC.
        inicio = datetime.combine(p.start, time.min, tzinfo=tz)
        H = M.MetricsHourlyUsers
        rows = (await db.execute(select(H).where(H.tenant_id == tenant, H.ts_hour >= inicio,
                                                 H.ts_hour < inicio + timedelta(days=1))
                                 .order_by(H.ts_hour))).scalars().all()
        buckets = [BucketOut(label=f"{r.ts_hour.astimezone(tz).hour:02d} h", start=r.ts_hour,
                             end=r.ts_hour + timedelta(hours=1)) for r in rows]
        return RegistrationsOut(period=_period_out(p), granularity="hour", buckets=buckets,
                                signups=[r.signups for r in rows],
                                cancellations=[r.cancellations for r in rows],
                                computed_at=max((r.computed_at for r in rows), default=inicio))

    rows = (await db.execute(select(D).where(D.tenant_id == tenant, D.day.between(p.start, p.end))
                             .order_by(D.day))).scalars().all()
    by_day = {r.day: r for r in rows}
    buckets, signups, cancellations = [], [], []
    for b_start, b_end, label in buckets_for(p):
        buckets.append(BucketOut(label=label,
                                 start=datetime.combine(b_start, time.min, tzinfo=tz),
                                 end=datetime.combine(b_end, time.max, tzinfo=tz)))
        days = [by_day[b_start + timedelta(days=i)]
                for i in range((b_end - b_start).days + 1)
                if (b_start + timedelta(days=i)) in by_day]
        signups.append(sum(d.signups for d in days))
        cancellations.append(sum(d.cancellations for d in days))
    computed = max((r.computed_at for r in rows), default=now_utc())
    return RegistrationsOut(period=_period_out(p), granularity=p.granularity, buckets=buckets,
                            signups=signups, cancellations=cancellations, computed_at=computed)


# ---------- 4.3 Plans ----------
@router.get("/plans", response_model=PlansOut)
async def plans(request: Request, db: Db):
    tenant = tenant_de(request)
    S = M.MetricsPlanSnapshot
    last_date = (await db.execute(select(func.max(S.as_of)).where(S.tenant_id == tenant))
                 ).scalar_one_or_none()
    if last_date is None:
        raise invalid("NO_DATA", "Aún no hay snapshots de planes calculados.")
    rows = (await db.execute(select(S).where(S.tenant_id == tenant, S.as_of == last_date))
            ).scalars().all()
    order = [PlanCode.free, PlanCode.gold, PlanCode.platinum, PlanCode.provider]
    rows.sort(key=lambda r: order.index(PlanCode(r.plan_code)))
    total_users = sum(r.users for r in rows)
    total_mrr = sum(r.mrr_amount for r in rows)
    # churn total ponderado por usuarios (monthly_churn es numeric: se pasa a float)
    total_churn = round(sum(float(r.monthly_churn) * r.users for r in rows) / total_users, 4) \
        if total_users else 0.0
    return PlansOut(
        as_of=last_date,
        plans=[PlanRow(plan_code=PlanCode(r.plan_code), name=PLAN_NAMES[PlanCode(r.plan_code)],
                       users=r.users, share=round(r.users / total_users, 4) if total_users else 0.0,
                       price_clp=r.price_amount, mrr_clp=r.mrr_amount,
                       monthly_churn=float(r.monthly_churn))
               for r in rows],
        totals=PlanTotals(users=total_users, mrr_clp=total_mrr, monthly_churn=total_churn),
        computed_at=max(r.computed_at for r in rows),
    )


# ---------- 4.4 Funnel ----------
@router.get("/funnel", response_model=FunnelOut)
async def funnel(request: Request, db: Db):
    """Embudo acumulado: último snapshot de metrics_funnel_snapshot (modelo, sección 6)."""
    tenant = tenant_de(request)
    F = M.MetricsFunnelSnapshot
    snap = (await db.execute(select(F).where(F.tenant_id == tenant)
                             .order_by(F.as_of.desc()).limit(1))).scalar_one_or_none()
    if snap is None:
        raise invalid("NO_DATA", "Aún no hay snapshots del embudo calculados.")
    stages_raw = [("downloads", "Descargas", snap.downloads_total),
                  ("accounts", "Cuentas creadas", snap.accounts_total),
                  ("active_30d", "Activos últimos 30 días", snap.active_30d),
                  ("paying", "En plan de pago", snap.paying)]
    first = stages_raw[0][2] or 1
    return FunnelOut(as_of=snap.as_of,
                     stages=[FunnelStage(stage=k, name=n, users=v,
                                         rate_vs_first=round(v / first, 4)) for k, n, v in stages_raw],
                     computed_at=snap.computed_at)
