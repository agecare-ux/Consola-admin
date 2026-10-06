"""Configuración, legales, auditoría y matriz de permisos (secciones 2.3 y 12–14)."""
import os
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

BASE = "/api/v1/admin"
pytestmark = pytest.mark.asyncio


async def _sql(consulta: str, **params):
    eng = create_async_engine(os.environ["ADMIN_DATABASE_URL"], poolclass=NullPool)
    try:
        async with eng.begin() as conn:
            res = await conn.execute(text(consulta), params)
            return res.all() if res.returns_rows else []
    finally:
        await eng.dispose()


async def test_permisos_salen_de_la_base(client, analyst_headers):
    assert (await client.get(f"{BASE}/ops/status", headers=analyst_headers)).status_code == 200
    await _sql("delete from admin.admin_role_permissions where role_code = 'analyst' and module = 'ops'")
    try:
        r = await client.get(f"{BASE}/ops/status", headers=analyst_headers)
        assert r.status_code == 403
        me = (await client.get(f"{BASE}/auth/me", headers=analyst_headers)).json()
        assert "ops" not in me["permissions"]
    finally:
        await _sql("insert into admin.admin_role_permissions values ('analyst', 'ops', 'read')")


async def test_parametro_y_auditoria(client, admin_headers):
    r = await client.get(f"{BASE}/settings", params={"key": "feature_adoption_low_threshold"},
                         headers=admin_headers)
    s = r.json()["settings"][0]
    r = await client.put(f"{BASE}/settings/feature_adoption_low_threshold", headers=admin_headers,
                         json={"value": s["value"], "version": s["version"], "change_note": "Prueba de suite"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == s["version"] + 1 and r.json()["updated_by"]["name"]

    r = await client.get(f"{BASE}/audit-log", params={"action": "settings.update"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    entrada = r.json()["items"][0]
    assert entrada["after"]["key"] == "feature_adoption_low_threshold"
    assert entrada["actor"]["role"] == "admin"


async def test_version_legal(client, admin_headers):
    docs = (await client.get(f"{BASE}/legal/documents", params={"doc_type": "privacy"},
                             headers=admin_headers)).json()["documents"][0]
    mayor, menor = map(int, docs["current"]["semver"].split("."))
    r = await client.post(f"{BASE}/legal/documents/privacy/versions", headers=admin_headers, json={
        "semver": f"{mayor}.{menor + 1}", "content_md": "# Política\n\n" + "Texto de prueba. " * 10,
        "changelog": "Ajuste menor de redacción.",
        "effective_date": (date.today() + timedelta(days=1)).isoformat()})
    assert r.status_code == 201, r.text
    assert r.json()["requires_reacceptance"] is False  # cambio menor
    r = await client.post(f"{BASE}/legal/versions/{r.json()['version_id']}/publish", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "published"
