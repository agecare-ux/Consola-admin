"""Sección 7 — Uso por funcionalidad."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app import models_canonico as M
from app.audit import tenant_de
from app.deps import Db, require
from app.enums import AppRole
from app.errors import invalid
from app.schemas.metrics import (AdoptionAlert, AdoptionOut, AlertsOut, FeatureAdoptionRow,
                                 TopByRole, TopFeature, TopOut)
from app.security import now_utc

router = APIRouter(prefix="/metrics/features", tags=["Uso por funcionalidad"],
                   dependencies=[require("metrics")])
ROLE_ORDER = [AppRole.family, AppRole.caregiver, AppRole.elder, AppRole.doctor]
UMBRAL_POR_DEFECTO = 0.15  # spec 7.3, si el tenant no tiene el parámetro sembrado
U = M.FeatureUsageWindow


def _check_days(days: int) -> int:
    if days not in (7, 30, 90):
        raise invalid("INVALID_RANGE", "La ventana debe ser 7, 30 o 90 días.")
    return days


class _Matriz:
    """Catálogo de funciones y su adopción por perfil en una ventana.

    `rate` distingue los dos casos que la spec pide separar:
    None = la función no existe para ese perfil (sin fila en feature_roles);
    0.0  = existe pero nadie la usó (o el job aún no escribió la fila).
    """

    def __init__(self, features, aplica: set, adopcion: dict, computed: datetime):
        self.features, self._aplica, self._adopcion, self.computed = \
            features, aplica, adopcion, computed

    def rate(self, feature: M.Feature, role: AppRole) -> float | None:
        if (feature.key, role.value) not in self._aplica:
            return None
        return self._adopcion.get((feature.key, role.value), 0.0)


async def _matriz(db, tenant: UUID, days: int) -> _Matriz:
    features = (await db.execute(select(M.Feature).order_by(M.Feature.sort_order))
                ).scalars().all()
    T = M.t_feature_roles
    aplica = {(k, r) for k, r in (await db.execute(
        select(T.c.feature_key, T.c.app_role_code))).all()}
    filas = (await db.execute(select(U).where(U.tenant_id == tenant, U.days_window == days))
             ).scalars().all()
    # adoption la calcula la base (users / role_active_users, acotada a 1).
    adopcion = {(f.feature_key, f.app_role_code): round(float(f.adoption), 4) for f in filas}
    computed = max((f.computed_at for f in filas), default=now_utc())
    return _Matriz(features, aplica, adopcion, computed)


async def _umbral_del_tenant(db, tenant: UUID) -> float:
    """Umbral por defecto: parámetro feature_adoption_low_threshold de system_settings."""
    valor = (await db.execute(select(M.SystemSetting.value)
                              .where(M.SystemSetting.tenant_id == tenant,
                                     M.SystemSetting.key == "feature_adoption_low_threshold"))
             ).scalar_one_or_none()
    try:
        umbral = float(valor)
    except (TypeError, ValueError):
        return UMBRAL_POR_DEFECTO
    return umbral if 0.01 <= umbral <= 0.5 else UMBRAL_POR_DEFECTO


# ---------- 7.1 Adoption matrix ----------
@router.get("/adoption", response_model=AdoptionOut)
async def adoption(request: Request, db: Db, days: int = Query(default=30)):
    days = _check_days(days)
    m = await _matriz(db, tenant_de(request), days)
    return AdoptionOut(
        days=days, roles=ROLE_ORDER,
        features=[FeatureAdoptionRow(feature_key=f.key, name=f.name,
                                     adoption=[m.rate(f, r) for r in ROLE_ORDER])
                  for f in m.features],
        computed_at=m.computed)


# ---------- 7.2 Top per role ----------
@router.get("/top", response_model=TopOut)
async def top(request: Request, db: Db, days: int = Query(default=30),
              limit: int = Query(default=1, ge=1, le=5)):
    days = _check_days(days)
    m = await _matriz(db, tenant_de(request), days)
    out = []
    for role in ROLE_ORDER:
        scored = [(f, m.rate(f, role)) for f in m.features]
        scored = [(f, s) for f, s in scored if s is not None]
        scored.sort(key=lambda x: x[1], reverse=True)
        out.append(TopByRole(role=role,
                             features=[TopFeature(feature_key=f.key, name=f.name, adoption=s)
                                       for f, s in scored[:limit]]))
    return TopOut(top_by_role=out, computed_at=m.computed)


# ---------- 7.3 Adoption alerts ----------
@router.get("/alerts", response_model=AlertsOut)
async def alerts(request: Request, db: Db, days: int = Query(default=30),
                 threshold: float | None = Query(default=None)):
    days = _check_days(days)
    tenant = tenant_de(request)
    if threshold is None:
        threshold = await _umbral_del_tenant(db, tenant)
    elif not 0.01 <= threshold <= 0.5:
        raise invalid("INVALID_THRESHOLD", "El umbral debe estar entre 0.01 y 0.5.")
    m = await _matriz(db, tenant, days)
    result = []
    for f in m.features:
        low_roles, low_values = [], []
        for role in ROLE_ORDER:
            rate = m.rate(f, role)
            if rate is not None and rate < threshold:
                low_roles.append(role)
                low_values.append(rate)
        if low_roles:
            result.append(AdoptionAlert(feature_key=f.key, name=f.name,
                                        roles=low_roles, adoption=low_values,
                                        expected_low=f.expected_low, note=f.note))
    # las de baja adopción esperada (p. ej. emergencias) van al final
    result.sort(key=lambda a: (a.expected_low, min(a.adoption)))
    return AlertsOut(threshold=threshold, alerts=result, computed_at=m.computed)
