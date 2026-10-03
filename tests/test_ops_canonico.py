"""Incidentes (5.5–5.6) sobre el esquema canónico: transiciones según el tipo."""
from datetime import datetime, timedelta, timezone

import pytest

BASE = "/api/v1/admin/ops/incidents"
pytestmark = pytest.mark.asyncio


async def _crear(client, headers, mantenimiento: bool):
    inicio = datetime.now(timezone.utc) + (timedelta(hours=2) if mantenimiento else -timedelta(minutes=5))
    r = await client.post(BASE, headers=headers, json={
        "title": "Prueba de incidente", "component_key": "push", "severity": "degraded",
        "description": "Creado por la suite.", "is_maintenance": mantenimiento,
        "started_at": inicio.isoformat()})
    assert r.status_code == 201, r.text
    return r.json()


async def test_incidente_normal_no_se_completa_y_se_resuelve(client, admin_headers):
    inc = await _crear(client, admin_headers, mantenimiento=False)
    assert inc["status"] == "investigating"
    r = await client.patch(f"{BASE}/{inc['id']}", headers=admin_headers,
                           json={"status": "completed", "resolution": "x"})
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"
    r = await client.patch(f"{BASE}/{inc['id']}", headers=admin_headers, json={"status": "resolved"})
    assert r.json()["error"]["code"] == "RESOLUTION_REQUIRED"
    r = await client.patch(f"{BASE}/{inc['id']}", headers=admin_headers,
                           json={"status": "resolved", "resolution": "Se reinició el servicio."})
    assert r.status_code == 200, r.text
    assert r.json()["resolved_at"] is not None


async def test_mantenimiento_futuro_se_completa_pero_no_se_resuelve(client, admin_headers):
    inc = await _crear(client, admin_headers, mantenimiento=True)
    assert inc["status"] == "observing"
    r = await client.patch(f"{BASE}/{inc['id']}", headers=admin_headers,
                           json={"status": "resolved", "resolution": "x"})
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"
    # se cierra antes de su inicio previsto: resolved_at no puede quedar antes de started_at
    r = await client.patch(f"{BASE}/{inc['id']}", headers=admin_headers,
                           json={"status": "completed", "resolution": "Ventana cancelada."})
    assert r.status_code == 200, r.text
    def leer(v):
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    assert leer(r.json()["resolved_at"]) >= leer(r.json()["started_at"])
