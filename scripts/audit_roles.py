"""Comprueba que cada endpoint autoriza exactamente los roles que dice la especificación."""
import asyncio, httpx
from app.main import app

P = "/api/v1/admin"
CUENTAS = {"admin": ("admin@wellq.co.uk", "Admin123!"),
           "analyst": ("analista@wellq.co.uk", "Analista123!"),
           "support": ("soporte@wellq.co.uk", "Soporte123!"),
           "editor": ("editora@wellq.co.uk", "Editora123!")}

# (método, ruta, roles autorizados según la spec, sección del documento)
CASOS = [
    ("GET",  "/metrics/commercial/summary?period=today", {"admin", "analyst", "support"}, "4.1"),
    ("GET",  "/metrics/commercial/plans",                {"admin", "analyst", "support"}, "4.3"),
    ("GET",  "/ops/status",                              {"admin", "analyst", "support"}, "5.1"),
    ("GET",  "/ops/incidents",                           {"admin", "analyst", "support"}, "5.4"),
    ("POST", "/ops/incidents",                           {"admin", "support"},            "5.5 escritura"),
    ("GET",  "/metrics/roles/summary",                   {"admin", "analyst", "support"}, "6.1"),
    ("GET",  "/support/summary",                         {"admin", "analyst", "support"}, "6.3"),
    ("GET",  "/metrics/features/adoption",               {"admin", "analyst", "support"}, "7.1"),
    ("GET",  "/support/tickets",                         {"admin", "analyst", "support"}, "8.1"),
    ("POST", "/support/tickets",                         {"admin", "support"},            "8.3 escritura"),
    ("GET",  "/content/items",                           {"admin", "editor"},             "9.1"),
    ("POST", "/content/items",                           {"admin", "editor"},             "9.2"),
    ("GET",  "/marketplace/caregivers",                  {"admin", "editor", "moderator"},"10.1"),
    ("POST", "/marketplace/products",                    {"admin", "editor"},             "10.4"),
    ("GET",  "/moderation/queue",                        {"admin", "moderator"},          "11.1"),
    ("GET",  "/settings",                                {"admin"},                       "12.1"),
    ("GET",  "/legal/documents",                         {"admin"},                       "13.1"),
    ("GET",  "/audit-log",                               {"admin"},                       "14.1"),
    ("GET",  "/users",                                   {"admin"},                       "3.6"),
]


async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        tokens = {}
        for rol, (email, pw) in CUENTAS.items():
            r = await c.post(f"{P}/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, f"{rol}: {r.text}"
            tokens[rol] = {"Authorization": "Bearer " + r.json()["access_token"]}

        fallos = 0
        print(f"{'sec':<14} {'endpoint':<44} " + "  ".join(f"{r:<8}" for r in CUENTAS))
        for metodo, ruta, permitidos, sec in CASOS:
            fila, detalle = [], []
            for rol in CUENTAS:
                if metodo == "GET":
                    r = await c.get(P + ruta, headers=tokens[rol])
                else:
                    r = await c.post(P + ruta, headers=tokens[rol], json={})
                # 422 = pasó el control de permisos y falló la validación del cuerpo: cuenta como permitido
                permitido_real = r.status_code != 403
                esperado = rol in permitidos
                ok = permitido_real == esperado
                if not ok:
                    fallos += 1
                    detalle.append(f"{rol}: esperado {'permitir' if esperado else 'denegar'}, dio {r.status_code}")
                fila.append(("ok " if ok else "MAL") + ("+" if permitido_real else "-"))
            print(f"{sec:<14} {metodo + ' ' + ruta.split('?')[0]:<44} " + "  ".join(f"{f:<8}" for f in fila))
            for d in detalle:
                print(f"{'':<14} └─ {d}")
        print(f"\nDesviaciones: {fallos}")
        print("Leyenda: '+' el rol puede acceder, '-' recibe 403. 'ok' coincide con la spec.")
        print("Nota: no hay cuenta con rol 'moderator' en el seed, así que esa columna no se prueba.")

asyncio.run(main())
