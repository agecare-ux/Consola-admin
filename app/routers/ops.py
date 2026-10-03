"""Sección 5 — Estado operativo (esquema canónico)."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import audit, tenant_de
from app.deps import Db, require
from app.enums import COMPONENT_NAMES, ComponentKey, ComponentStatus, IncidentStatus
from app.errors import conflict, invalid, not_found
from app.schemas.common import Page
from app.schemas.ops import (ComponentOut, CriticalProcessesOut, CriticalProcessOut,
                             IncidentCreateIn, IncidentOut, IncidentPatchIn, LatencyOut,
                             LatencyRow, StatusOut)
from app.security import now_utc

router = APIRouter(prefix="/ops", tags=["Estado operativo"])

SYNC_COMPONENTS = [ComponentKey.database, ComponentKey.api_core, ComponentKey.auth,
                   ComponentKey.wearable_ingest, ComponentKey.storage,
                   ComponentKey.music_sync, ComponentKey.alert_engine]

_SEVERITY_ORDER = {ComponentStatus.operational: 0, ComponentStatus.degraded: 1, ComponentStatus.outage: 2}

# Sección 5.6: las transiciones permitidas viven en admin.incident_status_transitions
# (distintas para incidentes y mantenimientos). La API las lee de ahí, y el trigger
# trg_transition aplica la misma tabla en la base.


async def _transicion_valida(db, actual: str, destino: str, mantenimiento: bool) -> bool:
    T = M.IncidentStatusTransitions
    return (await db.execute(select(T.from_status).where(
        T.from_status == actual, T.to_status == destino,
        T.is_maintenance.is_(mantenimiento)))).first() is not None


# ---------- 5.1 Status ----------
@router.get("/status", response_model=StatusOut, dependencies=[require("ops")])
async def status(request: Request, db: Db):
    rows = (await db.execute(select(M.ComponentState)
                             .where(M.ComponentState.tenant_id == tenant_de(request)))).scalars().all()
    components = sorted(rows, key=lambda r: list(ComponentKey).index(ComponentKey(r.component_key)))
    overall = max((ComponentStatus(r.status) for r in rows),
                  key=lambda s: _SEVERITY_ORDER[s], default=ComponentStatus.operational)
    return StatusOut(
        overall=overall,
        checked_at=max((r.checked_at for r in rows), default=now_utc()),
        components=[ComponentOut(key=ComponentKey(r.component_key),
                                 name=COMPONENT_NAMES[ComponentKey(r.component_key)],
                                 status=ComponentStatus(r.status), uptime_30d=float(r.uptime_30d),
                                 latency_p50_ms=r.latency_p50_ms, latency_p95_ms=r.latency_p95_ms,
                                 note=r.note) for r in components])


# ---------- 5.2 Latency ----------
@router.get("/latency", response_model=LatencyOut, dependencies=[require("ops")])
async def latency(request: Request, db: Db,
                  window: str = Query(default="1h"),
                  components: list[ComponentKey] | None = Query(default=None)):
    if window not in ("1h", "24h", "7d"):
        raise invalid("INVALID_WINDOW", "La ventana indicada no es válida. Usa 1h, 24h o 7d.")
    keys = [c.value for c in (components or SYNC_COMPONENTS)]
    L = M.LatencyWindow
    rows = (await db.execute(select(L).where(L.tenant_id == tenant_de(request), L.window == window,
                                             L.component_key.in_(keys)))).scalars().all()
    rows.sort(key=lambda r: r.p95_ms)
    return LatencyOut(window=window,
                      components=[LatencyRow(key=ComponentKey(r.component_key),
                                             name=COMPONENT_NAMES[ComponentKey(r.component_key)],
                                             p50_ms=r.p50_ms, p95_ms=r.p95_ms,
                                             sample_count=r.sample_count) for r in rows],
                      computed_at=max((r.computed_at for r in rows), default=now_utc()))


# ---------- 5.3 Critical processes ----------
@router.get("/critical-processes", response_model=CriticalProcessesOut, dependencies=[require("ops")])
async def critical_processes(request: Request, db: Db):
    # Nombre y cadena vienen del catálogo critical_processes; el estado, del job.
    S, C = M.CriticalProcessState, M.CriticalProcesses
    rows = (await db.execute(select(S, C).join(C, C.key == S.process_key)
                             .where(S.tenant_id == tenant_de(request))
                             .order_by(C.sort_order))).all()
    return CriticalProcessesOut(
        processes=[CriticalProcessOut(key=s_.process_key, name=c.name, chain=c.chain,
                                      p95_seconds=float(s_.p95_seconds),
                                      success_24h=float(s_.success_24h),
                                      status=ComponentStatus(s_.status)) for s_, c in rows],
        computed_at=max((s_.computed_at for s_, _ in rows), default=now_utc()))


# ---------- 5.4 Listar incidentes ----------
@router.get("/incidents", response_model=Page[IncidentOut], dependencies=[require("ops")])
async def list_incidents(request: Request, db: Db,
                         days: int = Query(default=30, ge=1, le=365),
                         status_f: IncidentStatus | None = Query(default=None, alias="status"),
                         component: ComponentKey | None = None,
                         page: int = Query(default=1, ge=1),
                         page_size: int = Query(default=25, ge=1, le=100)):
    since = now_utc() - timedelta(days=days)
    I = M.Incident
    stmt = select(I).where(I.tenant_id == tenant_de(request), I.started_at >= since)
    if status_f:
        stmt = stmt.where(I.status == status_f.value)
    if component:
        stmt = stmt.where(I.component_key == component.value)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(I.started_at.desc(), I.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return Page(items=[IncidentOut.model_validate(r) for r in rows],
                page=page, page_size=page_size, total=total)


# ---------- 5.5 Crear incidente ----------
@router.post("/incidents", response_model=IncidentOut, status_code=201)
async def create_incident(body: IncidentCreateIn, request: Request, db: Db,
                          admin: M.AdminUser = require("ops", write=True)):
    if not body.is_maintenance and body.started_at > now_utc():
        raise invalid("STARTED_AT_FUTURE",
                      "La fecha de inicio no puede ser futura salvo en mantenimientos programados.")
    estado = IncidentStatus.observing if body.is_maintenance else IncidentStatus.investigating
    inc = M.Incident(tenant_id=tenant_de(request), title=body.title,
                     component_key=body.component_key.value if body.component_key else None,
                     severity=body.severity, description=body.description,
                     status=estado.value, is_maintenance=body.is_maintenance,
                     started_at=body.started_at, created_by=admin.id, updated_by=admin.id)
    db.add(inc)
    await db.flush()
    await db.refresh(inc)  # created_at / updated_at los pone la base
    # Aquí se notificaría al canal interno de operaciones (webhook Slack/Teams).
    await audit(db, request, "ops.incident_create", "incident", inc.id, after={"title": inc.title})
    return IncidentOut.model_validate(inc)


# ---------- 5.6 Actualizar incidente ----------
@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
async def patch_incident(incident_id: UUID, body: IncidentPatchIn, request: Request, db: Db,
                         admin: M.AdminUser = require("ops", write=True)):
    inc = await db.get(M.Incident, incident_id)
    if inc is None or inc.tenant_id != tenant_de(request):
        raise not_found()
    before = {"status": inc.status, "description": inc.description}
    if body.status is not None:
        target = body.status
        closing = target in (IncidentStatus.resolved, IncidentStatus.completed)
        if not await _transicion_valida(db, inc.status, target.value, inc.is_maintenance):
            raise conflict("INVALID_TRANSITION", "Transición de estado no permitida para este incidente.")
        if closing and not (body.resolution or inc.resolution):
            raise invalid("RESOLUTION_REQUIRED", "Para cerrar el incidente debes incluir la nota de resolución.")
        inc.status = target.value
        if closing:
            # Un mantenimiento programado puede cerrarse antes de su inicio previsto;
            # resolved_at no puede quedar antes de started_at (CHECK del modelo).
            inc.resolved_at = max(now_utc(), inc.started_at)
    if body.resolution is not None:
        inc.resolution = body.resolution
    if body.description is not None:
        inc.description = body.description
    inc.updated_by = admin.id
    await audit(db, request, "ops.incident_update", "incident", inc.id, before=before,
                after={"status": inc.status})
    await db.flush()
    await db.refresh(inc)  # updated_at lo pone el trigger
    return IncidentOut.model_validate(inc)
