"""Seed de datos demo coherentes con el Wireframe de la Consola v1.

Uso:
    python -m scripts.seed          # crea tablas (si faltan) y siembra datos
Credenciales demo:
    admin@wellq.co.uk / Admin123!   (rol admin, sin MFA para facilitar la prueba)
    soporte@wellq.co.uk / Soporte123!
    analista@wellq.co.uk / Analista123!
"""
import asyncio
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, select

from app import models
from app.database import Base, get_engine, get_session_factory
from app.enums import AppRole, ComponentKey, PlanCode
from app.security import hash_password

random.seed(20260828)
# Fecha de referencia del seed. Se ancla al día de ejecución para que los periodos
# "hoy", "semana en curso" y "mes en curso" de la consola tengan datos reales.
TODAY = date.today()
NOW = datetime.now(timezone.utc)

FEATURES = [
    # key, nombre, roles aplicables, expected_low, nota, orden
    ("home_status", "Inicio / semáforo", ["family", "caregiver", "doctor"], False, None, 1),
    ("alert_center", "Centro de alertas", ["family", "caregiver", "doctor"], False, None, 2),
    ("vitals", "Vitals del wearable", ["family", "caregiver", "doctor"], False, None, 3),
    ("medications", "Medicamentos y adherencia", ["family", "caregiver", "doctor"], False, None, 4),
    ("checkin", "Check-in diario", ["caregiver"], False, None, 5),
    ("logbook", "Bitácora y observaciones", ["family", "caregiver", "doctor"], False, None, 6),
    ("chat", "Chat de coordinación", ["family", "caregiver", "elder", "doctor"], False, None, 7),
    ("ai_assistant", "Asistente IA", ["family", "caregiver", "doctor"], False,
     "Evaluar resúmenes clínicos automáticos para médicos.", 8),
    ("photos", "Fotos compartidas", ["family", "caregiver", "elder"], False, None, 9),
    ("entertainment", "Entretenimiento", ["elder"], False, None, 10),
    ("music_director", "Director Musical", ["family", "elder"], False, None, 11),
    ("documents", "Documentos médicos", ["family", "caregiver", "doctor"], False, None, 12),
    ("premium_reports", "Reportes (premium)", ["family", "caregiver", "doctor"], False,
     "Función de pago poco descubierta; probar oferta contextual tras 30 días de uso.", 13),
    ("marketplace", "Marketplace", ["family", "caregiver"], False,
     "Vitrina Could de v1 con adopción marginal. Decidir: rediseñar el descubrimiento o posponer a fase 2.", 14),
    ("sos", "SOS", ["caregiver", "elder"], True,
     "Uso bajo por diseño: es un evento de emergencia, no una función de uso diario.", 15),
]

# Adopción (%) por rol [family, caregiver, elder, doctor] — igual que el wireframe
ADOPTION = {
    "home_status": [92, 88, None, 61], "alert_center": [84, 71, None, 33],
    "vitals": [77, 64, None, 58], "medications": [69, 91, None, 72],
    "checkin": [None, 86, None, None], "logbook": [48, 83, None, 39],
    "chat": [62, 55, 47, 12], "ai_assistant": [41, 18, None, 9],
    "photos": [58, 22, 66, None], "entertainment": [None, None, 54, None],
    "music_director": [21, None, 38, None], "documents": [34, 29, None, 44],
    "premium_reports": [9, 13, None, 7], "marketplace": [11, 6, None, None],
    "sos": [None, 4, 2, None],
}
ACTIVE_30D = {"family": 5310, "caregiver": 1470, "elder": 2640, "doctor": 420}
ROLE_ORDER = ["family", "caregiver", "elder", "doctor"]

# --- Coherencia de cifras -----------------------------------------------------
# Las cifras del wireframe se tratan como una MEZCLA (proporciones), no como
# totales absolutos. El seed las escala al cierre de la simulación diaria para que
# los KPIs, la tabla de planes, el embudo y las tarjetas de perfil cuadren entre sí.
ROLE_MIX_TOTAL = sum(ACTIVE_30D.values())                  # 9.840 usuarios activos
PAID_PLANS = [(PlanCode.gold, 610, 1000, .041),            # (plan, peso, precio CLP, churn)
              (PlanCode.platinum, 240, 10000, .022),
              (PlanCode.provider, 90, 5000, .018)]
PAID_MIX_TOTAL = sum(w for _, w, _, _ in PAID_PLANS)       # 940 usuarios de pago
FREE_CHURN = .029


def split_paying(total: int) -> list[tuple]:
    """Reparte los usuarios de pago entre planes conservando la mezcla del wireframe.

    El último plan absorbe el resto de la división para que la suma cuadre exacta.
    """
    rows, assigned = [], 0
    for i, (code, weight, price, churn) in enumerate(PAID_PLANS):
        users = total - assigned if i == len(PAID_PLANS) - 1 else round(total * weight / PAID_MIX_TOTAL)
        assigned += users
        rows.append((code, users, price, churn))
    return rows


def mrr_for(paying_total: int) -> int:
    """MRR derivado de la mezcla real de planes, no de un ARPU aproximado."""
    return sum(users * price for _, users, price, _ in split_paying(paying_total))


def split_by_role(total: int) -> dict[str, int]:
    """Reparte un total de usuarios activos entre perfiles con la mezcla del wireframe."""
    out, assigned = {}, 0
    for i, role in enumerate(ROLE_ORDER):
        users = total - assigned if i == len(ROLE_ORDER) - 1 else round(total * ACTIVE_30D[role] / ROLE_MIX_TOTAL)
        assigned += users
        out[role] = users
    return out


async def seed() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with get_session_factory()() as db:
        # limpiar (idempotente)
        for table in (models.AuditLog, models.AdminSession, models.TicketReply, models.Ticket,
                      models.FeatureUsageWindow, models.Feature, models.RoleWeeklyActive,
                      models.RoleActivityWindow, models.MetricsPlanSnapshot,
                      models.MetricsHourlyUsers, models.MetricsDailyUsers,
                      models.LatencyWindow, models.ComponentState, models.CriticalProcessState,
                      models.Incident, models.ContentItem, models.CaregiverProfile,
                      models.Product, models.ModerationItem, models.SystemSetting,
                      models.LegalVersion, models.AdminUser):
            await db.execute(delete(table))

        # ---- Staff ----
        admins = [
            models.AdminUser(full_name="Max K.", email="admin@wellq.co.uk", role="admin",
                             password_hash=hash_password("Admin123!"), is_active=True),
            models.AdminUser(full_name="Sofía Rojas", email="soporte@wellq.co.uk", role="support",
                             password_hash=hash_password("Soporte123!"), is_active=True),
            models.AdminUser(full_name="Diego Paredes", email="analista@wellq.co.uk", role="analyst",
                             password_hash=hash_password("Analista123!"), is_active=True),
            models.AdminUser(full_name="Carla Núñez", email="editora@wellq.co.uk", role="editor",
                             password_hash=hash_password("Editora123!"), is_active=True),
        ]
        db.add_all(admins)
        await db.flush()
        admin, soporte = admins[0], admins[1]

        # ---- Métricas diarias (últimos 14 meses) ----
        start = TODAY - timedelta(days=425)
        active = 700.0
        paying = 40.0
        d = start
        while d <= TODAY:
            month_idx = (d.year - start.year) * 12 + d.month - start.month
            base = 10 + month_idx * 4.6
            signups = max(0, int(random.gauss(base, base * .18)))
            cancels = max(0, int(signups * random.uniform(.09, .16)))
            active = active + signups - cancels
            paying = min(active * .096, paying + signups * .045)
            mrr = mrr_for(int(paying))  # mismo cálculo que el snapshot de planes
            db.add(models.MetricsDailyUsers(day=d, signups=signups, cancellations=cancels,
                                            downloads=int(signups * 1.9),
                                            active_users_eod=int(active),
                                            paying_users_eod=int(paying), mrr_clp_eod=mrr))
            d += timedelta(days=1)

        # ---- Métricas horarias de hoy (buckets de 3 h) ----
        for h, (s, c) in enumerate(zip([2, 1, 3, 9, 14, 11, 13, 9], [0, 0, 1, 2, 2, 1, 2, 1])):
            db.add(models.MetricsHourlyUsers(
                ts_hour=datetime.combine(TODAY, time(h * 3), tzinfo=timezone.utc), signups=s, cancellations=c))

        # ---- Snapshot de planes (derivado del cierre de la simulación) ----
        active_end, paying_end = int(active), int(paying)
        db.add(models.MetricsPlanSnapshot(as_of=TODAY, plan_code=PlanCode.free,
                                          users=active_end - paying_end, price_clp=None,
                                          mrr_clp=0, monthly_churn=FREE_CHURN))
        for code, users, price, churn in split_paying(paying_end):
            db.add(models.MetricsPlanSnapshot(as_of=TODAY, plan_code=code, users=users,
                                              price_clp=price,
                                              mrr_clp=users * price,
                                              monthly_churn=churn))

        # ---- Actividad por rol (escalada al total real de activos) ----
        active_30d = split_by_role(active_end)
        sessions = {"family": 9.4, "caregiver": 22.6, "elder": 11.8, "doctor": 2.1}
        seconds = {"family": 250, "caregiver": 460, "elder": 545, "doctor": 200}
        retention = {"family": .78, "caregiver": .91, "elder": .64, "doctor": .55}
        growth = {"family": .149, "caregiver": .089, "elder": .195, "doctor": .20}
        for window in (7, 30, 90):
            factor = {7: .62, 30: 1.0, 90: 1.22}[window]
            for role in ROLE_ORDER:
                db.add(models.RoleActivityWindow(days_window=window, role=role,
                                                 active_users=int(active_30d[role] * factor),
                                                 growth_8w=growth[role],
                                                 sessions_per_week=sessions[role],
                                                 avg_session_seconds=seconds[role],
                                                 retention_30d=retention[role]))
        # La forma de la curva viene del wireframe; la magnitud, del total real.
        weekly_shape = {"family": [4620, 4750, 4890, 4980, 5040, 5150, 5230, 5310],
                        "caregiver": [1350, 1370, 1390, 1410, 1430, 1450, 1460, 1470],
                        "elder": [2210, 2290, 2340, 2400, 2460, 2520, 2580, 2640],
                        "doctor": [350, 360, 375, 380, 395, 400, 410, 420]}
        weekly = {}
        for role, shape in weekly_shape.items():
            k = active_30d[role] / shape[-1]
            weekly[role] = [int(round(v * k)) for v in shape]
            weekly[role][-1] = active_30d[role]  # cierra en el mismo valor que la tarjeta
        monday = TODAY - timedelta(days=TODAY.weekday())
        for i in range(8):
            week = monday - timedelta(weeks=7 - i)
            for role in ROLE_ORDER:
                db.add(models.RoleWeeklyActive(week_start=week, role=role,
                                               active_users=weekly[role][i]))

        # ---- Funcionalidades y adopción ----
        for key, name, roles, low, note, order in FEATURES:
            db.add(models.Feature(feature_key=key, name=name, applicable_roles=roles,
                                  expected_low=low, note=note, sort_order=order))
        for window in (7, 30, 90):
            wf = {7: .82, 30: 1.0, 90: 1.08}[window]
            active_f = {7: .62, 30: 1.0, 90: 1.22}[window]
            for key, pcts in ADOPTION.items():
                for role, pct in zip(ROLE_ORDER, pcts):
                    if pct is None:
                        continue
                    users = int(active_30d[role] * active_f * min(pct * wf, 100) / 100)
                    db.add(models.FeatureUsageWindow(days_window=window, feature_key=key,
                                                     role=role, users=users))

        # ---- Estado operativo ----
        comps = [
            (ComponentKey.api_core, "operational", .9998, 84, 240, None),
            (ComponentKey.database, "operational", .9999, 6, 31, None),
            (ComponentKey.auth, "operational", .9997, 110, 320, None),
            (ComponentKey.push, "operational", .9990, None, 1900, "entrega extremo a extremo"),
            (ComponentKey.alert_engine, "operational", .9995, 220, 850, None),
            (ComponentKey.wearable_ingest, "operational", .9996, 95, 410, None),
            (ComponentKey.ai_assistant, "degraded", .9780, 1800, 4200, "latencia elevada"),
            (ComponentKey.storage, "operational", .9999, 120, 480, None),
            (ComponentKey.music_sync, "operational", .9920, 140, 620, None),
        ]
        for key, st, up, p50, p95, note in comps:
            db.add(models.ComponentState(key=key, status=st, uptime_30d=up,
                                         latency_p50_ms=p50, latency_p95_ms=p95, note=note))
            for window, mult in (("1h", 1.0), ("24h", 1.08), ("7d", 1.15)):
                if p50 is None:
                    continue
                db.add(models.LatencyWindow(window=window, component_key=key,
                                            p50_ms=int(p50 * mult), p95_ms=int(p95 * mult),
                                            sample_count={"1h": 3600, "24h": 82000, "7d": 560000}[window]))
        for key, name, chain, p95s, ok, st in [
            ("fall_alert", "Alerta de caída", "Wearable → ingesta → motor de alertas → push familiar", 6.8, .997, "operational"),
            ("sos", "Botón SOS", "App → API → push a círculo de cuidado", 3.1, .999, "operational"),
            ("missed_dose", "Alerta de medicamento omitido", "Ventana de toma → job programado → push", 48.0, .995, "operational"),
            ("ai_query", "Consulta al asistente IA", "App → API → LLM → respuesta", 4.2, .978, "degraded"),
            ("music_sync", "Sincronización Director Musical", "Tablet → API → S3 → confirmación", 11.4, .992, "operational"),
        ]:
            db.add(models.CriticalProcessState(key=key, name=name, chain=chain,
                                               p95_seconds=p95s, success_24h=ok, status=st))
        db.add_all([
            models.Incident(title="Latencia elevada en el Asistente IA", component_key="ai_assistant",
                            severity="degraded", status="observing",
                            description="p95 de generación sobre 4 s por saturación del proveedor LLM. "
                                        "Mitigación: caché de respuestas frecuentes en evaluación.",
                            started_at=NOW - timedelta(days=2), created_by=admin.id),
            models.Incident(title="Notificaciones push retrasadas 23 min", component_key="push",
                            severity="degraded", status="resolved",
                            description="Cola de Notification Hubs saturada tras pico de alertas.",
                            resolution="Se amplió el plan y se añadió alarma de profundidad de cola.",
                            started_at=NOW - timedelta(days=9), resolved_at=NOW - timedelta(days=9, hours=-1),
                            created_by=soporte.id),
            models.Incident(title="Mantenimiento programado de base de datos", component_key="database",
                            severity="degraded", status="completed", is_maintenance=True,
                            description="Actualización menor de PostgreSQL Flexible sin corte de servicio.",
                            resolution="Completado en ventana 02:00–02:40 con réplica + failover.",
                            started_at=NOW - timedelta(days=21), resolved_at=NOW - timedelta(days=21, hours=-1),
                            created_by=admin.id),
        ])

        # ---- Tickets ----
        subjects = [
            ("Wearable no sincroniza desde ayer", "wearable_sync", "high", "in_progress", "family"),
            ("No llegan las alertas de medicamentos", "alerts_push", "critical", "in_progress", "caregiver"),
            ("Error al digitalizar receta (OCR)", "medications", "medium", "open", "caregiver"),
            ("Cambio de plan Dorado → Platino", "billing_plans", "medium", "resolved", "family"),
            ("El médico no puede editar el plan", "account_access", "medium", "resolved", "doctor"),
            ("Audio del Director Musical no sube", "other", "low", "resolved", "caregiver"),
        ]
        n = 1482
        tickets_dest = []
        for i, (subj, cat, prio, st, role) in enumerate(subjects):
            created = NOW - timedelta(days=i, hours=3)
            t = models.Ticket(number=n - i, subject=subj, description=f"Detalle del caso: {subj}.",
                              requester_name=f"Usuario Demo {i + 1}",
                              requester_email=f"usuario{i + 1}@demo.cl", requester_role=role,
                              requester_plan="gold" if i % 2 else "free",
                              category=cat, priority=prio, status=st, channel="app",
                              assigned_to=soporte.id if st != "open" else None,
                              created_at=created,
                              first_response_at=created + timedelta(hours=2) if st != "open" else None,
                              resolved_at=created + timedelta(hours=20) if st == "resolved" else None,
                              csat_score=5 if st == "resolved" and i % 2 else None,
                              requester_context={"patients": [{"display_name": "Paciente Demo"}],
                                                 "devices": [{"platform": "android", "app_version": "1.0.3"}]})
            db.add(t)
            tickets_dest.append(t)
        # Histórico en DOS ventanas: los últimos 30 días y los 30 anteriores.
        # Sin la segunda, el KPI "resueltos vs mes anterior" divide entre casi cero
        # y muestra porcentajes absurdos.
        CATS = ["account_access"] * 32 + ["wearable_sync"] * 24 + ["alerts_push"] * 14 + \
               ["billing_plans"] * 12 + ["medications"] * 9 + ["other"] * 9
        # Ventana actual: el reparto hace que los KPIs cuadren con el wireframe
        # (214 resueltos, 37 abiertos, 21 en curso, 9 esperando), descontando los
        # seis tickets destacados de arriba.
        actual = ["resolved"] * 211 + ["open"] * 36 + ["in_progress"] * 19 + ["waiting_user"] * 9
        # Ventana anterior: un mes ya cerrado, todo resuelto o cerrado.
        previa = ["resolved"] * 170 + ["closed"] * 30
        random.shuffle(actual)
        random.shuffle(previa)

        historico = [(st, random.uniform(0, 29)) for st in actual] + \
                    [(st, random.uniform(34, 59)) for st in previa]
        tickets_hist = []
        for j, (estado, dias) in enumerate(historico):
            cerrado = estado in ("resolved", "closed")
            created = NOW - timedelta(days=dias)
            # El resolved_at no puede saltar de ventana: se acota a 48 h.
            resolved_at = created + timedelta(hours=random.uniform(4, 48)) if cerrado else None
            t = models.Ticket(number=n - 6 - j, subject=f"Caso histórico {j + 1}",
                              description="Ticket histórico de demo.",
                              requester_name="Usuario Demo", requester_email=f"hist{j}@demo.cl",
                              requester_role=random.choice(ROLE_ORDER),
                              category=CATS[j % len(CATS)],
                              priority=random.choice(["low", "medium", "medium", "high"]),
                              status=estado, channel="app", created_at=created,
                              assigned_to=soporte.id if estado != "open" else None,
                              first_response_at=created + timedelta(hours=random.uniform(.3, 4.5)),
                              resolved_at=resolved_at,
                              csat_score=random.choice([5, 5, 5, 5, 5, 5, 5, 4, 4, 3])
                              if cerrado and random.random() < .55 else None)
            db.add(t)
            tickets_hist.append(t)

        # ---- Conversaciones de los tickets ----
        # Sin esto, abrir cualquier ticket en la consola muestra un hilo vacío.
        # El id se genera en Python al hacer flush, así que hay que forzarlo antes.
        await db.flush()

        HILOS = {
            "wearable_sync": ("El reloj dejó de mandar datos ayer por la tarde y la app sigue "
                              "mostrando la última medición del mediodía.",
                              "Gracias por avisar. Vemos que el dispositivo perdió el vínculo Bluetooth. "
                              "Abre Ajustes › Dispositivos y pulsa «Volver a vincular»; si sigue igual, "
                              "reinicia el reloj manteniendo el botón lateral 10 segundos."),
            "alerts_push": ("No me llegan las notificaciones de medicamentos al teléfono, aunque en la "
                            "app aparecen como programadas.",
                            "Revisamos tu cuenta: las alertas se generan correctamente en nuestro lado. "
                            "El problema está en los permisos del sistema. Entra en Ajustes de Android › "
                            "Aplicaciones › AgeCare › Notificaciones y activa «Permitir alertas»."),
            "medications": ("Al fotografiar la receta, la app reconoce mal las dosis y me pone 2 "
                            "comprimidos donde dice 1.",
                            "El lector de recetas tiene dificultades con la letra manuscrita. "
                            "Puedes corregir la dosis a mano pulsando sobre el medicamento. "
                            "Hemos pasado el caso al equipo del OCR con tu ejemplo."),
            "billing_plans": ("Quiero cambiar del plan Dorado al Platino, pero no encuentro dónde hacerlo.",
                              "El cambio se hace desde Perfil › Mi plan › Cambiar. El cobro se prorratea: "
                              "solo pagas la diferencia de los días que quedan del mes en curso."),
            "account_access": ("El médico que invitamos no puede modificar el plan de medicamentos, "
                               "solo verlo.",
                               "Es el comportamiento previsto: la invitación se envió con rol de lectura. "
                               "Desde Perfil › Círculo de cuidado puedes cambiarle el rol a «Médico», "
                               "que sí permite prescribir."),
            "other": ("Grabé una canción en el Director Musical y no aparece en la galería de la familia.",
                      "La sincronización del Director Musical es offline-first: la canción se sube cuando "
                      "la tablet vuelve a tener wifi. Ya la vemos en nuestro lado, debería aparecer en "
                      "unos minutos."),
        }
        CIERRES = ["Damos por resuelto el caso. Si vuelve a ocurrir, responde a este mismo ticket y lo reabrimos.",
                   "Confirmado por el usuario que ya funciona. Cerramos el ticket.",
                   "Solucionado. Quedamos atentos por si necesitas cualquier otra cosa."]
        NOTAS = ["Nota interna: tercer caso esta semana con el mismo modelo de wearable. Conviene avisar al equipo de integración.",
                 "Nota interna: usuario en plan Dorado, sin histórico de incidencias previas.",
                 "Nota interna: escalado al turno de tarde por si el usuario responde fuera de horario."]

        def conversacion(t, rico: bool):
            """Genera el hilo de un ticket a partir de su categoría y su estado."""
            msgs = []
            pregunta, respuesta = HILOS.get(t.category, HILOS["other"])
            # 1) el usuario abre el caso
            msgs.append(("user", t.requester_name, pregunta, False, t.created_at + timedelta(minutes=1)))
            # 2) primera respuesta del equipo: es la que fija first_response_at
            if t.first_response_at:
                msgs.append(("admin", soporte.full_name, respuesta, False, t.first_response_at))
            # 3) nota interna en algunos casos (un ticket abierto aún no tiene respuesta)
            if t.first_response_at and (rico or random.random() < .25):
                msgs.append(("admin", soporte.full_name, random.choice(NOTAS), True,
                             t.first_response_at + timedelta(minutes=12)))
            # 4) cierre cuando el ticket está resuelto
            if t.resolved_at:
                msgs.append(("admin", soporte.full_name, random.choice(CIERRES), False, t.resolved_at))
            return msgs

        for t in tickets_dest:
            for autor, nombre, cuerpo, interna, cuando in conversacion(t, rico=True):
                db.add(models.TicketReply(ticket_id=t.id, author_type=autor,
                                          author_id=soporte.id if autor == "admin" else None,
                                          author_name=nombre, body=cuerpo,
                                          internal=interna, created_at=cuando))
        # En el histórico basta con una parte: 2 de cada 3 tickets llevan hilo.
        for t in tickets_hist:
            if random.random() < .66:
                for autor, nombre, cuerpo, interna, cuando in conversacion(t, rico=False):
                    db.add(models.TicketReply(ticket_id=t.id, author_type=autor,
                                              author_id=soporte.id if autor == "admin" else None,
                                              author_name=nombre, body=cuerpo,
                                              internal=interna, created_at=cuando))

        # ---- Contenido ----
        # Catálogo variado para que los filtros por tipo y estado tengan algo que filtrar.
        CHISTES = [
            ("El loro políglota", "—Doctor, mi loro habla tres idiomas. —¿Y cuál prefiere? "
                                  "—El silencio, cuando le toca la siesta.", ["humor blanco"]),
            ("La receta de la abuela", "La nieta le pregunta a la abuela por la receta secreta de sus "
                                       "empanadas. —Fácil: se hacen con calma y se comen con familia.",
             ["humor blanco", "familia"]),
            ("El reloj de don Ernesto", "—Mi reloj nuevo me avisa de todo. —¿Y qué te dijo hoy? "
                                        "—Que me levantara. Le hice caso a la tercera.", ["humor blanco"]),
            ("Memoria de elefante", "—Abuelo, ¿te acuerdas de cuando nos conocimos? —Claro, mijita, "
                                    "fue el mismo día que naciste.", ["humor blanco", "familia"]),
            ("El bastón elegante", "Don Manuel se compró un bastón con empuñadura de plata. Dice que "
                                   "no lo necesita, pero que combina con todo.", ["humor blanco"]),
            ("Clase de tecnología", "—Abuela, esto se llama «la nube». —¿Y ahí guardan mis fotos? "
                                    "—Sí. —Entonces que no llueva.", ["humor blanco", "tecnología"]),
        ]
        NOTICIAS = [
            ("Chile lidera adopción de telemedicina en la región",
             "Un estudio regional destaca el crecimiento de las consultas a distancia entre personas "
             "mayores de 60 años, con foco en el seguimiento de enfermedades crónicas.", ["actualidad", "salud"]),
            ("Caminar 30 minutos al día reduce el riesgo cardiovascular",
             "Una revisión de la Sociedad Chilena de Cardiología confirma que la caminata diaria moderada "
             "mejora la presión arterial y el descanso nocturno en mayores de 65 años.", ["salud", "ejercicio"]),
            ("Nuevo programa municipal de talleres de memoria",
             "Doce comunas de la Región Metropolitana ofrecerán talleres gratuitos de estimulación "
             "cognitiva a partir del próximo mes.", ["actualidad", "comunidad"]),
            ("La música en la tercera edad: qué dice la evidencia",
             "Investigaciones recientes asocian la práctica musical activa con mejoras en el ánimo y "
             "en la memoria de trabajo de adultos mayores.", ["salud", "música"]),
            ("Recomendaciones para la ola de calor",
             "Hidratación frecuente, evitar la exposición al sol entre las 12 y las 17 horas y revisar "
             "la medicación diurética son las claves señaladas por el Minsal.", ["actualidad", "salud"]),
            ("Cómo preparar la casa para prevenir caídas",
             "Retirar alfombras sueltas, mejorar la iluminación de los pasillos e instalar barras de "
             "apoyo en el baño reducen a la mitad el riesgo de caída doméstica.", ["salud", "hogar"]),
            ("Vacunación contra la influenza: fechas y lugares",
             "La campaña comienza este mes para mayores de 65 años en todos los centros de atención "
             "primaria del país.", ["actualidad", "salud"]),
            ("Aplicaciones que ayudan a recordar la medicación",
             "Un repaso a las herramientas disponibles para no olvidar las tomas, con consejos para "
             "configurar recordatorios eficaces.", ["tecnología", "salud"]),
        ]
        contenidos = []
        for k, (titulo, cuerpo, tags) in enumerate(CHISTES + NOTICIAS):
            tipo = "joke" if k < len(CHISTES) else "news"
            # Reparto: la mayoría publicados, algunos borradores, uno programado y uno archivado.
            if k % 7 == 3:
                estado, publicado, programado = "draft", None, None
            elif k % 7 == 5:
                estado, publicado, programado = "draft", None, NOW + timedelta(days=2)
            elif k % 7 == 6:
                estado, publicado, programado = "archived", NOW - timedelta(days=40), None
            else:
                estado, publicado, programado = "published", NOW - timedelta(days=k + 1), None
            contenidos.append(models.ContentItem(
                type=tipo, title=titulo, body=cuerpo, tags=tags, status=estado,
                publish_at=programado, published_at=publicado, tts_ready=True,
                created_at=NOW - timedelta(days=k + 3),
                created_by=admins[3].id, created_by_name=admins[3].full_name))
        db.add_all(contenidos)

        # ---- Marketplace ----
        CUIDADORAS = [
            ("María Torres", "Providencia", ["Alzheimer", "Movilidad reducida"], ["es"], 3, True, 4.8, 26, "approved"),
            ("Paula Fuentes", "Ñuñoa", ["Posoperatorio"], ["es", "en"], 1, False, None, 0, "pending"),
            ("Rosa Maldonado", "Las Condes", ["Demencia", "Acompañamiento"], ["es"], 4, True, 4.9, 41, "approved"),
            ("Carmen Villalobos", "La Florida", ["Movilidad reducida", "Curaciones"], ["es"], 2, True, 4.6, 18, "approved"),
            ("Ana Sepúlveda", "Maipú", ["Acompañamiento nocturno"], ["es"], 2, True, 4.4, 12, "approved"),
            ("Jorge Cárcamo", "Santiago Centro", ["Rehabilitación", "Movilidad reducida"], ["es"], 3, True, 4.7, 9, "approved"),
            ("Ingrid Kunstmann", "Vitacura", ["Alzheimer", "Terapia ocupacional"], ["es", "de"], 5, False, None, 0, "pending"),
            ("Luis Navarrete", "Puente Alto", ["Acompañamiento"], ["es"], 1, True, 3.2, 7, "suspended"),
        ]
        for nombre, zona, esp, idiomas, certs, verif, rating, reviews, estado in CUIDADORAS:
            db.add(models.CaregiverProfile(
                name=nombre, email=nombre.split()[0].lower() + "@cuidado.cl", zone=zona,
                specialties=esp, languages=idiomas, certifications_count=certs,
                certifications_verified=verif, rating_avg=rating, reviews_count=reviews,
                status=estado, submitted_at=NOW - timedelta(days=random.randint(3, 120)),
                status_reason="Reseñas reiteradas por impuntualidad." if estado == "suspended" else None,
                reviewed_by=admins[3].id if estado != "pending" else None,
                reviewed_by_name=admins[3].full_name if estado != "pending" else None))

        ARTICULOS = [
            ("Andador plegable con asiento", "Movilidad", "OrtoChile", 64990, "published"),
            ("Pastillero semanal electrónico", "Medicación", "SaludHogar", 29990, "published"),
            ("Barra de apoyo para baño", "Seguridad en el hogar", "OrtoChile", 18990, "published"),
            ("Silla de ducha regulable", "Seguridad en el hogar", "VidaPlena", 42990, "published"),
            ("Tensiómetro digital de brazo", "Monitoreo", "MediCasa", 34990, "published"),
            ("Oxímetro de pulso", "Monitoreo", "MediCasa", 15990, "published"),
            ("Cojín antiescaras", "Cuidado postural", "VidaPlena", 55990, "published"),
            ("Alfombra antideslizante para ducha", "Seguridad en el hogar", "SaludHogar", 9990, "published"),
            ("Lupa con luz LED para lectura", "Vida diaria", "VidaPlena", 12990, "draft"),
            ("Teléfono de teclas grandes", "Comunicación", "MediCasa", 27990, "archived"),
        ]
        for nombre, cat, prov, precio, estado in ARTICULOS:
            slug = nombre.lower().replace(" ", "-")[:40]
            db.add(models.Product(name=nombre, category=cat, vendor=prov, price_clp=precio,
                                  external_url=f"https://{prov.lower()}.cl/{slug}",
                                  status=estado, updated_at=NOW - timedelta(days=random.randint(1, 60))))

        # ---- Moderación ----
        # Suficientes elementos pendientes para que la cola no se vacíe tras dos decisiones.
        PENDIENTES = [
            ("review", "Familia Pérez", "family", {"rating": 5, "text": "Excelente cuidadora, muy puntual y cariñosa."}, None, None, False),
            ("photo", "Usuario Demo 4", "family", {"url": "https://storage.demo/signed/foto123", "album": "Cumpleaños"},
             {"name": "Usuario Demo 7", "role": "caregiver"}, "Contenido que expone datos personales", True),
            ("review", "Familia Soto", "family", {"rating": 2, "text": "Llegó tarde dos veces y no avisó."}, None, None, False),
            ("review", "Familia Ramírez", "family", {"rating": 1, "text": "Pésimo servicio, no la recomiendo para nada."},
             {"name": "Rosa Maldonado", "role": "caregiver"}, "Reseña considerada injusta por la cuidadora", False),
            ("caregiver_profile", "Ingrid Kunstmann", "caregiver",
             {"bio": "Terapeuta ocupacional con 12 años de experiencia en demencias.", "zone": "Vitacura"},
             None, None, False),
            ("chat_message", "Usuario Demo 11", "family",
             {"text": "Te paso el número de cuenta para el pago directo: 000-11-2233."},
             {"name": "Sistema", "role": "system"}, "Posible dato bancario en el chat", True),
            ("photo", "Usuario Demo 19", "caregiver",
             {"url": "https://storage.demo/signed/foto481", "album": "Control de signos"},
             {"name": "Usuario Demo 2", "role": "family"}, "Aparece la receta médica completa", True),
            ("review", "Familia Contreras", "family", {"rating": 4, "text": "Muy buena, aunque le costó el primer día."}, None, None, False),
        ]
        for tipo, autor, rol, contenido, reporte, motivo, seguridad in PENDIENTES:
            db.add(models.ModerationItem(type=tipo, author_name=autor, author_role=rol,
                                         content=contenido, reported_by=reporte, report_reason=motivo,
                                         is_safety=seguridad, status="pending",
                                         created_at=NOW - timedelta(days=random.uniform(0, 12))))
        # Algunos ya decididos, para poder probar los filtros de estado.
        DECIDIDOS = [
            ("review", "Familia Muñoz", {"rating": 5, "text": "Impecable, la recomendamos."}, "approved", None, "Cumple las normas de la comunidad."),
            ("photo", "Usuario Demo 8", {"url": "https://storage.demo/signed/foto77", "album": "Paseo"}, "approved", None, "Sin datos sensibles a la vista."),
            ("chat_message", "Usuario Demo 14", {"text": "Mensaje con insultos hacia la cuidadora."}, "rejected", "offensive", "Lenguaje ofensivo dirigido a una persona identificable."),
            ("review", "Familia Vega", {"rating": 1, "text": "Texto promocional de otro servicio."}, "rejected", "spam", "Contenido promocional ajeno a la plataforma."),
        ]
        for tipo, autor, contenido, estado, motivo, nota in DECIDIDOS:
            decidido = NOW - timedelta(days=random.uniform(2, 25))
            db.add(models.ModerationItem(type=tipo, author_name=autor, author_role="family",
                                         content=contenido, status=estado, reject_reason_code=motivo,
                                         decision_note=nota, decided_by=admins[3].id,
                                         decided_by_name=admins[3].full_name, decided_at=decidido,
                                         created_at=decidido - timedelta(days=1)))

        # ---- Configuración ----
        db.add_all([
            models.SystemSetting(
                key="plan_prices", description="Precios mensuales por plan (CLP).",
                value={"gold": 1000, "platinum": 10000, "provider": 5000},
                value_schema={"type": "object",
                              "properties": {"gold": {"type": "integer", "minimum": 0},
                                             "platinum": {"type": "integer", "minimum": 0},
                                             "provider": {"type": "integer", "minimum": 0}},
                              "required": ["gold", "platinum", "provider"],
                              "additionalProperties": False}),
            models.SystemSetting(
                key="churn_definition", description="Definición de churn para métricas comerciales.",
                value={"explicit_cancellation": True, "inactivity_days": 60},
                value_schema={"type": "object",
                              "properties": {"explicit_cancellation": {"type": "boolean"},
                                             "inactivity_days": {"type": "integer", "minimum": 15,
                                                                 "maximum": 180}},
                              "required": ["explicit_cancellation", "inactivity_days"],
                              "additionalProperties": False}),
            models.SystemSetting(
                key="ops_thresholds.api_core", description="Umbrales de salud del componente API central.",
                value={"p95_ms": 500, "error_rate": 0.02},
                value_schema={"type": "object",
                              "properties": {"p95_ms": {"type": "integer", "minimum": 50},
                                             "error_rate": {"type": "number", "minimum": 0, "maximum": 1}},
                              "required": ["p95_ms", "error_rate"],
                              "additionalProperties": False}),
        ])

        # ---- Legales ----
        db.add_all([
            models.LegalVersion(doc_type="terms", semver="1.0", status="published",
                                content_md="# Términos de servicio de AgeCare\n\nVersión inicial." + " Lorem." * 30,
                                changelog="Versión inicial de lanzamiento.",
                                effective_date=date(2026, 6, 1), requires_reacceptance=True,
                                published_at=NOW - timedelta(days=88),
                                created_by=admin.id, created_by_name=admin.full_name),
            models.LegalVersion(doc_type="privacy", semver="1.0", status="published",
                                content_md="# Política de privacidad de AgeCare\n\nVersión inicial." + " Lorem." * 30,
                                changelog="Versión inicial de lanzamiento.",
                                effective_date=date(2026, 6, 1), requires_reacceptance=True,
                                published_at=NOW - timedelta(days=88),
                                created_by=admin.id, created_by_name=admin.full_name),
        ])

        # ---- Registro de auditoría ----
        # La tabla se llena sola con el uso, pero sin histórico no hay nada con lo que
        # probar los filtros por fecha, actor o entidad de la sección 14.1.
        await db.flush()
        ACCIONES = [
            ("ticket.update", "ticket", [t.id for t in tickets_hist[:60]], soporte),
            ("ticket.reply", "ticket", [t.id for t in tickets_hist[60:110]], soporte),
            ("content.publish", "content_item", [c.id for c in contenidos], admins[3]),
            ("content.update", "content_item", [c.id for c in contenidos], admins[3]),
            ("moderation.approve", "moderation_item", [uuid.uuid4() for _ in range(6)], admins[3]),
            ("moderation.reject", "moderation_item", [uuid.uuid4() for _ in range(4)], admins[3]),
            ("marketplace.caregiver_update", "caregiver", [uuid.uuid4() for _ in range(5)], admins[3]),
            ("marketplace.product_create", "product", [uuid.uuid4() for _ in range(4)], admins[3]),
            ("settings.update", "setting", [uuid.uuid4() for _ in range(3)], admin),
            ("ops.incident_create", "incident", [uuid.uuid4() for _ in range(3)], soporte),
            ("staff.create", "admin_user", [uuid.uuid4() for _ in range(2)], admin),
            ("auth.login", "admin_user", [a.id for a in admins] * 4, None),
            ("auth.login_failed", "admin_user", [uuid.uuid4() for _ in range(3)], None),
        ]
        NAVEGADORES = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0",
                       "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) Safari/18.0",
                       "Mozilla/5.0 (X11; Linux x86_64) Firefox/132.0"]
        for accion, entidad, ids, actor_fijo in ACCIONES:
            for eid in random.sample(ids, min(len(ids), 6)):
                quien = actor_fijo or random.choice(admins)
                db.add(models.AuditLog(
                    actor_id=quien.id, actor_name=quien.full_name, actor_role=quien.role,
                    action=accion, entity_type=entidad, entity_id=eid,
                    before=None if accion.endswith((".create", ".login", ".login_failed")) else {"status": "anterior"},
                    after=None if accion in ("auth.login", "auth.login_failed") else {"status": "nuevo"},
                    ip=f"200.{random.randint(1, 120)}.{random.randint(1, 250)}.{random.randint(2, 250)}",
                    user_agent=random.choice(NAVEGADORES),
                    created_at=NOW - timedelta(days=random.uniform(0, 60), hours=random.uniform(0, 23))))

        await db.commit()
        total_tickets = (await db.execute(select(models.Ticket))).scalars().all()
        print(f"Seed completado: {len(admins)} cuentas de staff, {len(total_tickets)} tickets, "
              f"{len(FEATURES)} funcionalidades, métricas de 14 meses.")


if __name__ == "__main__":
    asyncio.run(seed())
