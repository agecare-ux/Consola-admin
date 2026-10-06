"""Contenido, marketplace y moderación (secciones 9–11)."""
import pytest

BASE = "/api/v1/admin"
pytestmark = pytest.mark.asyncio


async def test_ciclo_de_contenido(client, admin_headers):
    r = await client.post(f"{BASE}/content/items", headers=admin_headers, json={
        "type": "news", "title": "Noticia de prueba", "body": "Cuerpo de la noticia de prueba."})
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["created_by_name"] and item["audio_available"]
    for accion, estado in (("publish", "published"), ("unpublish", "archived")):
        r = await client.post(f"{BASE}/content/items/{item['id']}/{accion}", headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == estado
    r = await client.delete(f"{BASE}/content/items/{item['id']}", headers=admin_headers)
    assert r.status_code == 204
    r = await client.post(f"{BASE}/content/items/{item['id']}/publish", headers=admin_headers)
    assert r.status_code == 404  # borrado lógico: ya no existe para la API


async def test_filtro_de_especialidad_cuenta_bien(client, admin_headers):
    todas = (await client.get(f"{BASE}/marketplace/caregivers?page_size=100",
                              headers=admin_headers)).json()["items"]
    especialidad = todas[0]["specialties"][0]
    esperadas = [c for c in todas if especialidad.lower() in [s.lower() for s in c["specialties"]]]
    r = await client.get(f"{BASE}/marketplace/caregivers",
                         params={"specialty": especialidad.upper(), "page_size": 100},
                         headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == len(esperadas) == len(r.json()["items"])


async def test_producto_publicado_y_archivado(client, admin_headers):
    r = await client.post(f"{BASE}/marketplace/products", headers=admin_headers, json={
        "name": "Pastillero semanal", "category": "Salud", "vendor": "Farmacia Demo",
        "price_clp": 4990, "external_url": "https://tienda.demo/pastillero"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    for estado in ("published", "archived", "published"):
        r = await client.patch(f"{BASE}/marketplace/products/{pid}", headers=admin_headers,
                               json={"status": estado})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == estado


async def test_decision_de_moderacion_es_definitiva(client, admin_headers):
    cola = (await client.get(f"{BASE}/moderation/queue", headers=admin_headers)).json()["items"]
    assert cola, "el seed debe traer elementos pendientes"
    mid = cola[0]["id"]
    r = await client.post(f"{BASE}/moderation/queue/{mid}/reject", headers=admin_headers,
                          json={"reason_code": "spam"})
    assert r.status_code == 200, r.text
    assert r.json()["decided_by_name"]
    r = await client.post(f"{BASE}/moderation/queue/{mid}/approve", headers=admin_headers, json={})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ALREADY_MODERATED"
