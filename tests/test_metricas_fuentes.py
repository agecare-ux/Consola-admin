"""Métricas (secciones 4, 6 y 7): fuentes de datos, periodos y umbrales.

Cada prueba contrasta la respuesta de la API con una consulta directa a la base,
hecha como propietario (sin filtro de tenant), para no comprobar la API contra sí misma.
"""
import os
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

BASE = "/api/v1/admin/metrics"
pytestmark = pytest.mark.asyncio


async def _sql(consulta: str, **params):
    eng = create_async_engine(os.environ["ADMIN_DATABASE_URL"], poolclass=NullPool)
    try:
        async with eng.begin() as conn:
            res = await conn.execute(text(consulta), params)
            return res.all() if res.returns_rows else []
    finally:
        await eng.dispose()


async def test_embudo_sale_del_snapshot(client, analyst_headers):
    r = await client.get(f"{BASE}/commercial/funnel", headers=analyst_headers)
    assert r.status_code == 200, r.text
    (fila,) = await _sql("select as_of, downloads_total, accounts_total, active_30d, paying "
                         "from admin.metrics_funnel_snapshot order by as_of desc limit 1")
    cuerpo = r.json()
    assert cuerpo["as_of"] == fila[0].isoformat()
    assert [s["users"] for s in cuerpo["stages"]] == list(fila[1:])


async def test_periodos_en_hora_local_del_tenant(client, analyst_headers):
    r = await client.get(f"{BASE}/commercial/registrations?period=today", headers=analyst_headers)
    assert r.status_code == 200, r.text
    (tz,) = (await _sql("select timezone from admin.tenants limit 1"))[0]
    buckets = r.json()["buckets"]
    from zoneinfo import ZoneInfo
    zona = ZoneInfo(tz)
    hoy_local = datetime.now(zona).date()
    # El seed solo trae las últimas 8 horas: no se exige que empiece a medianoche,
    # sino que todo cubo caiga dentro del día local de hoy (y no del día UTC).
    for b in buckets:
        local = datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(zona)
        assert local.date() == hoy_local and local.minute == 0


async def test_ventana_de_perfiles_es_la_menor_que_cubre(client, analyst_headers):
    disponibles = sorted(d for (d,) in await _sql(
        "select distinct days_window from admin.role_activity_window"))
    pedido = disponibles[0] + 1  # entre dos ventanas precalculadas
    r = await client.get(f"{BASE}/roles/summary?days={pedido}", headers=analyst_headers)
    assert r.status_code == 200, r.text
    assert r.json()["days"] == next(d for d in disponibles if d >= pedido)


async def test_semana_en_curso_cuenta_como_ultima(client, analyst_headers):
    r = await client.get(f"{BASE}/roles/weekly-active?weeks=8", headers=analyst_headers)
    assert r.status_code == 200, r.text
    (parcial,) = (await _sql("select max(week_start) from admin.role_weekly_active "
                             "where is_partial"))[0]
    assert len(r.json()["weeks"]) == 8
    assert r.json()["weeks"][-1] == f"S{parcial.isocalendar()[1]}"


async def test_matriz_respeta_feature_roles(client, analyst_headers):
    r = await client.get(f"{BASE}/features/adoption?days=30", headers=analyst_headers)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    aplica = {(k, rol) for k, rol in await _sql(
        "select feature_key, app_role_code from admin.feature_roles")}
    for fila in cuerpo["features"]:
        for rol, valor in zip(cuerpo["roles"], fila["adoption"]):
            # null exactamente donde el par no existe en feature_roles
            assert (valor is None) == ((fila["feature_key"], rol) not in aplica)


async def test_umbral_por_defecto_viene_de_system_settings(client, analyst_headers):
    (original,) = (await _sql("select value from admin.system_settings "
                              "where key = 'feature_adoption_low_threshold'"))[0]
    try:
        await _sql("update admin.system_settings set value = '0.3'::jsonb, version = version + 1 "
                   "where key = 'feature_adoption_low_threshold'")
        r = await client.get(f"{BASE}/features/alerts", headers=analyst_headers)
        assert r.status_code == 200, r.text
        assert r.json()["threshold"] == 0.3
        # el valor de la URL sigue mandando sobre el parámetro
        r = await client.get(f"{BASE}/features/alerts?threshold=0.1", headers=analyst_headers)
        assert r.json()["threshold"] == 0.1
        assert all(min(a["adoption"]) < 0.1 for a in r.json()["alerts"])
    finally:
        await _sql("update admin.system_settings set value = cast(:v as jsonb), version = version + 1 "
                   "where key = 'feature_adoption_low_threshold'", v=str(original))
