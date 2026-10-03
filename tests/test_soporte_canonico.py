"""Tickets (8.3–8.4) sobre el esquema canónico: lo que cambió en la fase 3."""
import uuid

import pytest

BASE = "/api/v1/admin"
pytestmark = pytest.mark.asyncio


async def test_asignar_reabrir_y_numeracion(client, admin_headers):
    r = await client.post(f"{BASE}/support/tickets", headers=admin_headers, json={
        "subject": "Prueba de asignación", "description": "Creado por la suite.",
        "user_email": "usuario2@demo.cl", "category": "other", "channel": "phone"})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["number"] > 1482  # sigue el correlativo del seed
    assert t["requester"]["user_id"] is not None  # enlazado a la cuenta del usuario

    staff = (await client.get(f"{BASE}/users?role=support", headers=admin_headers)).json()
    agente = staff["items"][0]
    r = await client.patch(f"{BASE}/support/tickets/{t['id']}", headers=admin_headers,
                           json={"assigned_to": agente["id"], "status": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["assigned_to"] == {"admin_id": agente["id"], "name": agente["full_name"]}

    for estado in ("resolved", "in_progress"):  # reapertura: resolved -> in_progress
        r = await client.patch(f"{BASE}/support/tickets/{t['id']}", headers=admin_headers,
                               json={"status": estado})
        assert r.status_code == 200, r.text


async def test_ticket_sin_enlazar_no_cuenta_como_usuario(client, admin_headers):
    correo = f"nadie{uuid.uuid4().hex[:6]}@example.com"
    cuerpo = {"subject": "Usuario sin cuenta", "description": "Llamada.", "user_email": correo,
              "category": "other", "channel": "phone"}
    r = await client.post(f"{BASE}/support/tickets", headers=admin_headers,
                          json={**cuerpo, "confirm_unlinked": True})
    assert r.status_code == 201, r.text
    # El ticket anterior se creó sin enlazar: no prueba que la cuenta exista.
    r = await client.post(f"{BASE}/support/tickets", headers=admin_headers, json=cuerpo)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "USER_NOT_FOUND"
