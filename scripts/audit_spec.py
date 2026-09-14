"""Comprueba cada error y validación que la especificación documenta, sección por sección."""
import asyncio, uuid
from datetime import date, datetime, timedelta, timezone

import httpx
from app.main import app

P = "/api/v1/admin"
resultados = []


def check(sec, desc, esperado_http, esperado_code, r):
    """esperado_code=None => solo se comprueba el HTTP."""
    try:
        body = r.json()
    except Exception:
        body = {}
    code = (body.get("error") or {}).get("code")
    ok_http = r.status_code == esperado_http
    ok_code = esperado_code is None or code == esperado_code
    resultados.append((sec, desc, ok_http and ok_code,
                       f"esperado {esperado_http}/{esperado_code}, dio {r.status_code}/{code}"))


async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async def login(email, pw, otp=None):
            b = {"email": email, "password": pw}
            if otp:
                b["otp_code"] = otp
            return await c.post(f"{P}/auth/login", json=b)

        r = await login("admin@wellq.co.uk", "Admin123!")
        tok = r.json()
        H = {"Authorization": "Bearer " + tok["access_token"]}

        # ---------- 2.5 errores comunes ----------
        check("2.5", "sin token -> 401 UNAUTHORIZED", 401, "UNAUTHORIZED",
              await c.get(f"{P}/settings"))
        check("2.5", "token inválido -> 401", 401, "UNAUTHORIZED",
              await c.get(f"{P}/settings", headers={"Authorization": "Bearer basura"}))
        check("2.5", "recurso inexistente -> 404 NOT_FOUND", 404, "NOT_FOUND",
              await c.get(f"{P}/support/tickets/{uuid.uuid4()}", headers=H))
        rr = await c.get(f"{P}/settings", headers=H)
        resultados.append(("2.4", "respuesta 200 sin envoltorio de error", "error" not in rr.text[:40], ""))

        # ---------- 3.1 login ----------
        check("3.1", "contraseña incorrecta -> INVALID_CREDENTIALS", 401, "INVALID_CREDENTIALS",
              await login("admin@wellq.co.uk", "MalaClave1!"))
        r_inexistente = await login("noexiste@wellq.co.uk", "MalaClave1!")
        check("3.1", "correo inexistente -> mismo error (no revela existencia)", 401,
              "INVALID_CREDENTIALS", r_inexistente)

        # ---------- 3.2 refresh rotatorio ----------
        r1 = await c.post(f"{P}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
        check("3.2", "refresh válido -> 200", 200, None, r1)
        check("3.2", "reutilizar refresh rotado -> INVALID_REFRESH", 401, "INVALID_REFRESH",
              await c.post(f"{P}/auth/refresh", json={"refresh_token": tok["refresh_token"]}))
        check("3.2", "refresh inventado -> INVALID_REFRESH", 401, "INVALID_REFRESH",
              await c.post(f"{P}/auth/refresh", json={"refresh_token": "inventado"}))

        # ---------- 3.3 logout 204 ----------
        r2 = await login("admin@wellq.co.uk", "Admin123!")
        t2 = r2.json()
        check("3.3", "logout -> 204 sin cuerpo", 204, None,
              await c.post(f"{P}/auth/logout", headers={"Authorization": "Bearer " + t2["access_token"]},
                           json={"refresh_token": t2["refresh_token"]}))

        # ---------- 3.5 crear staff ----------
        check("3.5", "correo ya usado -> EMAIL_IN_USE", 409, "EMAIL_IN_USE",
              await c.post(f"{P}/users", headers=H,
                           json={"full_name": "Prueba Dup", "email": "admin@wellq.co.uk", "role": "support"}))
        check("3.5", "dominio no permitido -> DOMAIN_NOT_ALLOWED", 422, "DOMAIN_NOT_ALLOWED",
              await c.post(f"{P}/users", headers=H,
                           json={"full_name": "Externo", "email": "alguien@gmail.com", "role": "support"}))
        nuevo = await c.post(f"{P}/users", headers=H,
                             json={"full_name": "Temporal Uno", "email": f"tmp{uuid.uuid4().hex[:8]}@wellq.co.uk",
                                   "role": "support"})
        check("3.5", "creación válida -> 201 Created", 201, None, nuevo)

        # ---------- 3.7 actualizar staff ----------
        me = (await c.get(f"{P}/auth/me", headers=H)).json()
        check("3.7", "desactivarse a sí mismo -> CANNOT_DISABLE_SELF", 409, "CANNOT_DISABLE_SELF",
              await c.patch(f"{P}/users/{me['id']}", headers=H, json={"is_active": False}))
        check("3.7", "dejar sin admin activo -> LAST_ADMIN", 409, "LAST_ADMIN",
              await c.patch(f"{P}/users/{me['id']}", headers=H, json={"role": "support"}))

        # ---------- 4.1 / 4.2 periodo ----------
        check("4.1", "periodo inválido -> INVALID_PERIOD o 422", 422, None,
              await c.get(f"{P}/metrics/commercial/summary?period=el_mes_pasado", headers=H))
        for p in ["today", "current_week", "last_7_days", "current_month", "last_30_days", "ytd", "last_12_months"]:
            rr = await c.get(f"{P}/metrics/commercial/registrations?period={p}", headers=H)
            d = rr.json()
            largo_ok = rr.status_code == 200 and len(d["buckets"]) == len(d["signups"]) == len(d["cancellations"])
            resultados.append(("4.2", f"periodo {p}: len(buckets)==len(signups)==len(cancellations)", largo_ok, ""))
        gran = {p: (await c.get(f"{P}/metrics/commercial/registrations?period={p}", headers=H)).json()["granularity"]
                for p in ["today", "current_week", "current_month", "ytd"]}
        resultados.append(("4.2", f"granularidad hora/día/semana/mes {gran}",
                           gran == {"today": "hour", "current_week": "day", "current_month": "week", "ytd": "month"}, ""))

        # ---------- 5.2 ventana ----------
        check("5.2", "ventana inválida -> INVALID_WINDOW o 422", 422, None,
              await c.get(f"{P}/ops/latency?window=3h", headers=H))
        for w in ["1h", "24h", "7d"]:
            resultados.append(("5.2", f"ventana {w} aceptada",
                               (await c.get(f"{P}/ops/latency?window={w}", headers=H)).status_code == 200, ""))

        # ---------- 5.5 / 5.6 incidentes ----------
        futuro = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        check("5.5", "started_at futuro sin mantenimiento -> STARTED_AT_FUTURE", 422, "STARTED_AT_FUTURE",
              await c.post(f"{P}/ops/incidents", headers=H,
                           json={"title": "Incidente de prueba", "severity": "degraded",
                                 "description": "prueba", "started_at": futuro}))
        inc = await c.post(f"{P}/ops/incidents", headers=H,
                           json={"title": "Incidente de prueba de auditoría", "severity": "degraded",
                                 "description": "creado por la auditoría",
                                 "started_at": datetime.now(timezone.utc).isoformat()})
        check("5.5", "creación válida -> 201 Created", 201, None, inc)
        iid = inc.json().get("id")
        resultados.append(("5.5", "nace con status=investigating", inc.json().get("status") == "investigating", ""))
        check("5.6", "cerrar sin nota -> RESOLUTION_REQUIRED", 422, "RESOLUTION_REQUIRED",
              await c.patch(f"{P}/ops/incidents/{iid}", headers=H, json={"status": "resolved"}))
        check("5.6", "transición investigating->completed -> INVALID_TRANSITION", 409, "INVALID_TRANSITION",
              await c.patch(f"{P}/ops/incidents/{iid}", headers=H,
                            json={"status": "completed", "resolution": "x" * 20}))

        # ---------- 6.1 / 6.2 rangos ----------
        check("6.1", "days=3 (fuera de 7-90) -> 422", 422, None,
              await c.get(f"{P}/metrics/roles/summary?days=3", headers=H))
        check("6.1", "days=200 -> 422", 422, None,
              await c.get(f"{P}/metrics/roles/summary?days=200", headers=H))
        check("6.2", "weeks=1 (fuera de 2-26) -> 422", 422, None,
              await c.get(f"{P}/metrics/roles/weekly-active?weeks=1", headers=H))
        wa = (await c.get(f"{P}/metrics/roles/weekly-active?weeks=8", headers=H)).json()
        resultados.append(("6.2", "len(values)==len(weeks) en cada serie",
                           all(len(s["values"]) == len(wa["weeks"]) for s in wa["series"]), ""))

        # ---------- 7.1 / 7.3 ----------
        check("7.1", "days=45 (solo 7/30/90) -> 422", 422, None,
              await c.get(f"{P}/metrics/features/adoption?days=45", headers=H))
        ad = (await c.get(f"{P}/metrics/features/adoption?days=30", headers=H)).json()
        resultados.append(("7.1", "roles en orden fijo family, caregiver, elder, doctor",
                           ad["roles"] == ["family", "caregiver", "elder", "doctor"], str(ad["roles"])))
        hay_null = any(x is None for f in ad["features"] for x in f["adoption"])
        resultados.append(("7.1", "null (no aplica) distinto de 0.0", hay_null, ""))
        check("7.3", "threshold=0.9 (fuera de 0.01-0.5) -> 422", 422, None,
              await c.get(f"{P}/metrics/features/alerts?threshold=0.9", headers=H))
        al = (await c.get(f"{P}/metrics/features/alerts?threshold=0.15", headers=H)).json()
        resultados.append(("7.3", "expected_low marcado en SOS",
                           any(a["feature_key"] == "sos" and a["expected_low"] for a in al["alerts"]), ""))

        # ---------- 8.x tickets ----------
        lst = (await c.get(f"{P}/support/tickets", headers=H)).json()
        resultados.append(("2.6", "paginación por defecto page=1, page_size=25",
                           lst["page"] == 1 and lst["page_size"] == 25, f"{lst['page']}/{lst['page_size']}"))
        check("2.6", "page_size=500 (máx 100) -> 422", 422, None,
              await c.get(f"{P}/support/tickets?page_size=500", headers=H))
        num = lst["items"][0]["number"]
        check("8.2", f"detalle por correlativo #{num}", 200, None,
              await c.get(f"{P}/support/tickets/%23{num}", headers=H))
        check("8.3", "correo sin cuenta -> USER_NOT_FOUND", 404, "USER_NOT_FOUND",
              await c.post(f"{P}/support/tickets", headers=H,
                           json={"subject": "Ticket de auditoría", "description": "prueba",
                                 "user_email": "nadie@ejemplo.com", "category": "other"}))
        tk = await c.post(f"{P}/support/tickets", headers=H,
                          json={"subject": "Ticket de auditoría", "description": "prueba",
                                "user_email": "nadie@ejemplo.com", "category": "other",
                                "confirm_unlinked": True})
        check("8.3", "confirm_unlinked=true -> 201 Created", 201, None, tk)
        tid = tk.json().get("id")
        resultados.append(("8.3", "nace con status=open y number asignado",
                           tk.json().get("status") == "open" and isinstance(tk.json().get("number"), int), ""))
        check("8.4", "agente inexistente -> ASSIGNEE_NOT_FOUND", 404, "ASSIGNEE_NOT_FOUND",
              await c.patch(f"{P}/support/tickets/{tid}", headers=H, json={"assigned_to": str(uuid.uuid4())}))
        check("8.4", "open->closed no permitido -> INVALID_TRANSITION", 409, "INVALID_TRANSITION",
              await c.patch(f"{P}/support/tickets/{tid}", headers=H, json={"status": "closed"}))
        check("8.5", "responder -> 201 Created", 201, None,
              await c.post(f"{P}/support/tickets/{tid}/replies", headers=H,
                           json={"body": "Respuesta de auditoría", "internal": False}))

        # ---------- 9.x contenido ----------
        pasado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        check("9.2", "publish_at pasado -> PUBLISH_AT_PAST", 422, "PUBLISH_AT_PAST",
              await c.post(f"{P}/content/items", headers=H,
                           json={"type": "joke", "title": "Chiste de auditoría",
                                 "body": "Texto suficientemente largo para pasar.", "publish_at": pasado}))
        it = await c.post(f"{P}/content/items", headers=H,
                          json={"type": "joke", "title": "Chiste de auditoría",
                                "body": "Texto suficientemente largo para pasar."})
        check("9.2", "creación válida -> 201 Created", 201, None, it)
        iid2 = it.json().get("id")
        resultados.append(("9.2", "nace en draft", it.json().get("status") == "draft", ""))
        check("9.5", "retirar un draft -> NOT_PUBLISHED", 409, "NOT_PUBLISHED",
              await c.post(f"{P}/content/items/{iid2}/unpublish", headers=H))
        pub = await c.post(f"{P}/content/items/{iid2}/publish", headers=H)
        check("9.4", "publicar draft -> 200", 200, None, pub)
        check("9.4", "publicar dos veces -> ALREADY_PUBLISHED", 409, "ALREADY_PUBLISHED",
              await c.post(f"{P}/content/items/{iid2}/publish", headers=H))
        check("9.6", "borrar publicado -> ITEM_PUBLISHED", 409, "ITEM_PUBLISHED",
              await c.delete(f"{P}/content/items/{iid2}", headers=H))
        await c.post(f"{P}/content/items/{iid2}/unpublish", headers=H)
        check("9.6", "borrar archivado -> 204", 204, None,
              await c.delete(f"{P}/content/items/{iid2}", headers=H))

        # ---------- 10.x marketplace ----------
        check("10.4", "enlace http -> INSECURE_URL", 422, "INSECURE_URL",
              await c.post(f"{P}/marketplace/products", headers=H,
                           json={"name": "Andador de prueba", "category": "movilidad", "vendor": "Proveedor X",
                                 "external_url": "http://inseguro.example.com/p"}))
        check("10.4", "enlace https -> 201 Created", 201, None,
              await c.post(f"{P}/marketplace/products", headers=H,
                           json={"name": "Andador de prueba", "category": "movilidad", "vendor": "Proveedor X",
                                 "external_url": "https://seguro.example.com/p"}))
        cg = (await c.get(f"{P}/marketplace/caregivers", headers=H)).json()["items"]
        if cg:
            check("10.2", "suspender sin motivo -> REASON_REQUIRED", 422, "REASON_REQUIRED",
                  await c.patch(f"{P}/marketplace/caregivers/{cg[0]['caregiver_id']}", headers=H,
                                json={"status": "suspended"}))

        # ---------- 11.x moderación ----------
        q = (await c.get(f"{P}/moderation/queue", headers=H)).json()["items"]
        if q:
            mid = q[0]["id"]
            check("11.3", "motivo other sin nota -> NOTE_REQUIRED", 422, "NOTE_REQUIRED",
                  await c.post(f"{P}/moderation/queue/{mid}/reject", headers=H, json={"reason_code": "other"}))
            check("11.2", "aprobar -> 200", 200, None,
                  await c.post(f"{P}/moderation/queue/{mid}/approve", headers=H, json={}))
            check("11.2", "aprobar dos veces -> ALREADY_MODERATED", 409, "ALREADY_MODERATED",
                  await c.post(f"{P}/moderation/queue/{mid}/approve", headers=H, json={}))

        # ---------- 12.x configuración ----------
        check("12.1", "clave inexistente -> UNKNOWN_SETTING", 404, "UNKNOWN_SETTING",
              await c.get(f"{P}/settings?key=no_existe", headers=H))
        st = (await c.get(f"{P}/settings", headers=H)).json()["settings"][0]
        check("12.2", "versión desfasada -> VERSION_CONFLICT", 409, "VERSION_CONFLICT",
              await c.put(f"{P}/settings/{st['key']}", headers=H,
                          json={"value": st["value"], "version": st["version"] + 99,
                                "change_note": "prueba de auditoría"}))
        check("12.2", "valor que no cumple el esquema -> INVALID_VALUE", 422, "INVALID_VALUE",
              await c.put(f"{P}/settings/{st['key']}", headers=H,
                          json={"value": "texto donde va un objeto", "version": st["version"],
                                "change_note": "prueba de auditoría"}))

        # ---------- 13.x legales ----------
        docs = (await c.get(f"{P}/legal/documents", headers=H)).json()["documents"]
        cur = next(d for d in docs if d["doc_type"] == "terms")["current"]
        check("13.2", "semver no mayor -> SEMVER_NOT_GREATER", 409, "SEMVER_NOT_GREATER",
              await c.post(f"{P}/legal/documents/terms/versions", headers=H,
                           json={"semver": "1.0", "content_md": "x" * 150,
                                 "changelog": "prueba de auditoría",
                                 "effective_date": str(date.today() + timedelta(days=30))}))
        mayor = f"{int(cur['semver'].split('.')[0]) + 1}.0"
        check("13.2", "cambio mayor con menos de 15 días -> NOTICE_PERIOD", 422, "NOTICE_PERIOD",
              await c.post(f"{P}/legal/documents/terms/versions", headers=H,
                           json={"semver": mayor, "content_md": "x" * 150,
                                 "changelog": "prueba de auditoría",
                                 "effective_date": str(date.today() + timedelta(days=3))}))

        # ---------- 14.1 auditoría ----------
        check("14.1", "rango > 90 días -> RANGE_TOO_WIDE", 422, "RANGE_TOO_WIDE",
              await c.get(f"{P}/audit-log?date_from=2020-01-01T00:00:00Z&date_to=2026-01-01T00:00:00Z", headers=H))
        au = (await c.get(f"{P}/audit-log", headers=H)).json()
        acciones = {x["action"] for x in au["items"]}
        resultados.append(("14", f"las mutaciones dejan rastro ({len(acciones)} acciones distintas)",
                           len(acciones) > 3, ", ".join(sorted(acciones)[:6])))
        resultados.append(("3.1", "login fallido registrado en auditoría",
                           any("login" in a for a in acciones), ", ".join(a for a in acciones if "login" in a)))

        # ---------- computed_at ----------
        for ruta in ["/metrics/commercial/summary?period=today", "/metrics/commercial/plans",
                     "/metrics/commercial/funnel", "/ops/latency", "/metrics/roles/summary",
                     "/metrics/features/adoption", "/support/summary"]:
            d = (await c.get(P + ruta, headers=H)).json()
            resultados.append(("2.8", f"computed_at en {ruta.split('?')[0]}", "computed_at" in d, ""))

    # ---------- informe ----------
    fallos = [r for r in resultados if not r[2]]
    por_sec = {}
    for sec, desc, ok, det in resultados:
        por_sec.setdefault(sec, [0, 0])
        por_sec[sec][0] += 1
        por_sec[sec][1] += 1 if ok else 0
    print("Sección  Comprobaciones")
    for sec in sorted(por_sec, key=lambda s: [int(x) for x in s.split()[0].split(".")]):
        t, o = por_sec[sec]
        print(f"  {sec:<6} {o}/{t} {'' if o == t else '  <-- revisar'}")
    print(f"\nTotal: {len(resultados) - len(fallos)}/{len(resultados)} conformes")
    if fallos:
        print("\nDesviaciones respecto a la especificación:")
        for sec, desc, _, det in fallos:
            print(f"  [{sec}] {desc}\n        {det}")

asyncio.run(main())
