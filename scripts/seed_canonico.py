"""Siembra datos de demostración en el esquema canónico `admin`.

Las constantes de la simulación —funcionalidades, adopción, reparto por plan y por
perfil— están en scripts/datos_demo.py, para que las cifras cuadren entre sí: los
KPIs, la tabla de planes, el embudo y las tarjetas de perfil hablan del mismo total
de usuarios activos.

Lo que NO siembra, porque ya viene con el DDL: los doce catálogos (roles de staff y
de la app, permisos, planes, categorías de ticket, componentes, procesos críticos,
funcionalidades, pares función/rol, transiciones y definiciones de parámetros).

Tampoco siembra las tablas de evento (`feature_usage_events`, `ops_component_checks`,
`ops_request_stats`, `store_downloads_daily`) ni las de historial: las primeras las
alimentarían los jobs de agregación, y las segundas se llenan solas por trigger.

Uso:
    $env:ADMIN_DATABASE_URL = "CADENA_DE_NEON_TAL_CUAL"   # o una base local
    python -m scripts.seed_canonico

Es idempotente: borra lo que siembra antes de volver a escribirlo.
"""
import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import models_canonico as M
from app.config import get_settings
from app.security import hash_password
from scripts import datos_demo as D
from scripts.datos_demo import (ACTIVE_30D, ADOPTION, FEATURES, MFA_SECRET_DEMO, NOW, PAID_PLANS,
                                ROLE_ORDER, TODAY, mrr_for, split_by_role, split_paying)

TENANT = uuid.UUID(get_settings().tenant_id)
FREE_CHURN = .029

STAFF = [
    ("Max K.", "admin@wellq.co.uk", "admin", "Admin123!", False),
    ("Sofía Rojas", "soporte@wellq.co.uk", "support", "Soporte123!", False),
    ("Diego Paredes", "analista@wellq.co.uk", "analyst", "Analista123!", False),
    ("Carla Núñez", "editora@wellq.co.uk", "editor", "Editora123!", False),
    ("Ignacio Salas", "moderador@wellq.co.uk", "moderator", "Moderador123!", False),
    ("Bryan Ávila", "admin.mfa@wellq.co.uk", "admin", "AdminMfa123!", True),
]

# Tablas que siembra este script, en orden inverso de dependencia para poder vaciarlas.
A_VACIAR = ["audit_log", "support_csat_surveys", "support_ticket_replies", "support_tickets",
            "support_metrics_daily", "moderation_items", "marketplace_products",
            "marketplace_caregivers", "content_items", "ops_incidents",
            "ops_critical_process_state", "ops_latency_window", "ops_component_state",
            "feature_usage_window", "role_weekly_active", "role_activity_window",
            "metrics_funnel_snapshot", "metrics_plan_snapshot", "metrics_hourly_users",
            "metrics_daily_users", "legal_versions", "system_settings",
            # Las crea el uso de la API (login, alta de staff): sin vaciarlas antes,
            # admin_invitations.created_by impide borrar el staff al volver a sembrar.
            "admin_login_attempts", "admin_sessions", "admin_invitations", "admin_users"]


async def seed() -> None:
    random.seed(20260828)
    url = get_settings().database_url
    engine = create_async_engine(url, poolclass=NullPool,
                                 connect_args={"statement_cache_size": 0,
                                               "prepared_statement_cache_size": 0}
                                 if url.startswith("postgresql+asyncpg://") else {})
    Sesion = async_sessionmaker(engine, expire_on_commit=False)

    async with Sesion() as db:
        # El contexto hay que declararlo en cada transacción: sin él, las políticas de
        # aislamiento no dejan ver ni escribir nada.
        await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT)})

        # ---- Tenant ----
        await db.execute(text(
            "INSERT INTO admin.tenants (id, code, name, country_code, currency_code, timezone, environment) "
            "VALUES (:i,'wellq','Wellq Co','CL','CLP','America/Santiago','development') "
            "ON CONFLICT (id) DO NOTHING"), {"i": str(TENANT)})
        await db.commit()

    async with Sesion() as db:
        await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT)})
        # Vaciar lo que este script siembra, para poder repetirlo.
        # Varias tablas son inmutables por trigger y no admiten DELETE: el registro de
        # auditoría, las respuestas de ticket y las diez de historial. TRUNCATE sí,
        # porque no dispara triggers de fila. Las de historial se vacían también, o
        # el trigger las volvería a llenar con cada resiembra.
        INMUTABLES = ["audit_log", "support_ticket_replies"] + [
            f"{t}_history" for t in ("admin_users", "content_items", "legal_versions",
                                     "marketplace_caregivers", "marketplace_products",
                                     "moderation_items", "ops_incidents", "support_tickets",
                                     "system_settings")]
        await db.execute(text("TRUNCATE " + ", ".join(f"admin.{t}" for t in INMUTABLES)))
        for tabla in [t for t in A_VACIAR if t not in INMUTABLES]:
            await db.execute(text(f"DELETE FROM admin.{tabla}"))
        await db.execute(text("DELETE FROM admin.tenant_counters"))
        await db.commit()

    async with Sesion() as db:
        await db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(TENANT)})

        # ---- Staff ----
        staff = {}
        for nombre, correo, rol, clave, con_mfa in STAFF:
            u = M.AdminUser(tenant_id=TENANT, full_name=nombre, email=correo, role_code=rol,
                            password_hash=hash_password(clave), is_active=True,
                            activated_at=NOW - timedelta(days=120),
                            mfa_enabled=con_mfa,
                            mfa_secret_enc=MFA_SECRET_DEMO.encode() if con_mfa else None)
            db.add(u)
            staff[rol if rol != "admin" or correo.startswith("admin@") else correo] = u
        await db.flush()
        admin = staff["admin"]
        soporte = staff["support"]
        editor = staff["editor"]

        # ---- Parámetros del sistema ----
        # Las definiciones y sus esquemas los trae el DDL; aquí van los valores.
        valores = {
            "plan_prices": {"gold": 1000, "platinum": 10000, "provider": 5000},
            "churn_definition": {"inactive_days": 30},
            "ops_thresholds.api_core": {"p95_ms": 400, "error_rate": 0.01},
            "allowed_email_domains": ["wellq.co.uk"],
            "feature_adoption_low_threshold": 0.15,
        }
        for clave, valor in valores.items():
            db.add(M.SystemSetting(tenant_id=TENANT, key=clave, value=valor, updated_by=admin.id))

        # ---- Legales ----
        for tipo, mayor, menor in [("terms", 2, 1), ("privacy", 1, 4)]:
            db.add(M.LegalVersion(
                tenant_id=TENANT, doc_type=tipo, semver_major=mayor, semver_minor=menor,
                content_md="# Documento\n\n" + "Contenido de demostración. " * 12,
                changelog="Versión vigente de demostración.",
                effective_date=date.today() - timedelta(days=90),
                requires_reacceptance=True, status="published",
                created_by=admin.id, published_by=admin.id,
                published_at=NOW - timedelta(days=95)))

        # ---- Métricas diarias (misma simulación que el seed del prototipo) ----
        # Base de usuarios que ya existía antes de la ventana simulada. Cuenta en el
        # embudo: sin ella, "cuentas creadas" quedaba por debajo de "activos 30 días".
        BASE_CUENTAS = 7400
        activos, pagan = float(BASE_CUENTAS), 300.0
        inicio = TODAY - timedelta(days=425)
        dias = []
        for i in range(426):
            d = inicio + timedelta(days=i)
            est = 1 + .35 * (i / 425)
            altas = int(random.gauss(34, 7) * est)
            bajas = int(altas * random.uniform(.08, .16))
            descargas = int(altas * random.uniform(1.7, 2.3))
            activos = min(activos + altas - bajas, activos * 1.004 + altas)
            pagan = min(pagan + altas * .045, activos * .096)
            db.add(M.MetricsDailyUsers(
                tenant_id=TENANT, day=d, signups=altas, cancellations=bajas,
                churned_users=bajas, downloads=descargas,
                active_users_eod=int(activos), paying_users_eod=int(pagan),
                mrr_amount=mrr_for(int(pagan)), is_final=True))
            dias.append((d, altas, bajas, descargas))

        hora_base = NOW.replace(minute=0, second=0, microsecond=0)
        for h in range(8):
            db.add(M.MetricsHourlyUsers(
                tenant_id=TENANT, ts_hour=hora_base - timedelta(hours=7 - h),
                signups=random.randint(2, 9), cancellations=random.randint(0, 2)))

        activos_fin, pagan_fin = int(activos), int(pagan)

        # ---- Planes y embudo ----
        db.add(M.MetricsPlanSnapshot(tenant_id=TENANT, as_of=TODAY, plan_code="free",
                                     users=activos_fin - pagan_fin, price_amount=None,
                                     mrr_amount=0, monthly_churn=FREE_CHURN))
        for codigo, usuarios, precio, churn in split_paying(pagan_fin):
            db.add(M.MetricsPlanSnapshot(tenant_id=TENANT, as_of=TODAY,
                                         plan_code=str(codigo).split(".")[-1], users=usuarios,
                                         price_amount=precio, mrr_amount=usuarios * precio,
                                         monthly_churn=churn))
        db.add(M.MetricsFunnelSnapshot(
            tenant_id=TENANT, as_of=TODAY,
            # La base previa también descargó la app (≈2 descargas por cuenta, como
            # en la simulación diaria).
            downloads_total=2 * BASE_CUENTAS + sum(d[3] for d in dias),
            accounts_total=BASE_CUENTAS + sum(d[1] for d in dias),
            active_30d=activos_fin, paying=pagan_fin))

        # ---- Perfiles ----
        activos_rol = split_by_role(activos_fin)
        sesiones = {"family": 9.4, "caregiver": 22.6, "elder": 11.8, "doctor": 2.1}
        segundos = {"family": 250, "caregiver": 460, "elder": 545, "doctor": 200}
        retencion = {"family": .78, "caregiver": .91, "elder": .64, "doctor": .55}
        crecimiento = {"family": .149, "caregiver": .089, "elder": .195, "doctor": .20}
        for ventana in (7, 30, 90):
            factor = {7: .62, 30: 1.0, 90: 1.22}[ventana]
            for rol in ROLE_ORDER:
                db.add(M.RoleActivityWindow(
                    tenant_id=TENANT, days_window=ventana, app_role_code=rol,
                    active_users=int(activos_rol[rol] * factor), growth_8w=crecimiento[rol],
                    sessions_per_week=sesiones[rol], avg_session_seconds=segundos[rol],
                    retention_30d=retencion[rol]))

        forma = {"family": [4620, 4750, 4890, 4980, 5040, 5150, 5230, 5310],
                 "caregiver": [1350, 1370, 1390, 1410, 1430, 1450, 1460, 1470],
                 "elder": [2210, 2290, 2340, 2400, 2460, 2520, 2580, 2640],
                 "doctor": [350, 360, 375, 380, 395, 400, 410, 420]}
        lunes = TODAY - timedelta(days=TODAY.weekday())
        for rol, serie in forma.items():
            k = activos_rol[rol] / serie[-1]
            escalada = [int(round(v * k)) for v in serie]
            escalada[-1] = activos_rol[rol]
            for i, v in enumerate(escalada):
                db.add(M.RoleWeeklyActive(tenant_id=TENANT, week_start=lunes - timedelta(weeks=7 - i),
                                          app_role_code=rol, active_users=v, is_partial=(i == 7)))

        # ---- Adopción de funcionalidades ----
        # adoption es columna calculada: se derivan users y role_active_users.
        for ventana in (7, 30, 90):
            wf = {7: .82, 30: 1.0, 90: 1.08}[ventana]
            af = {7: .62, 30: 1.0, 90: 1.22}[ventana]
            for clave, pcts in ADOPTION.items():
                for rol, pct in zip(ROLE_ORDER, pcts):
                    if pct is None:
                        continue
                    base = int(activos_rol[rol] * af)
                    db.add(M.FeatureUsageWindow(
                        tenant_id=TENANT, days_window=ventana, feature_key=clave,
                        app_role_code=rol, role_active_users=base,
                        users=int(base * min(pct * wf, 100) / 100)))

        # ---- Estado operativo ----
        COMPONENTES = [
            ("api_core", "operational", .9998, 118, 342, None),
            ("database", "operational", .9999, 9, 31, None),
            ("auth", "operational", .9997, 64, 180, None),
            ("push", "degraded", .9962, None, None, "Retraso medio de 42 s en Android"),
            ("alert_engine", "operational", .9995, 210, 610, None),
            ("wearable_ingest", "operational", .9991, 150, 430, None),
            ("ai_assistant", "operational", .9988, None, None, "Generación 2,4 s de media"),
            ("storage", "operational", .9999, 48, 140, None),
            ("music_sync", "operational", .9994, 95, 260, None),
        ]
        for clave, estado, uptime, p50, p95, nota in COMPONENTES:
            db.add(M.ComponentState(
                tenant_id=TENANT, component_key=clave, status=estado,
                status_since=NOW - timedelta(days=random.randint(1, 20)), checked_at=NOW,
                uptime_30d=uptime, latency_p50_ms=p50, latency_p95_ms=p95, note=nota))
        for ventana in ("1h", "24h", "7d"):
            f = {"1h": 1.0, "24h": 1.08, "7d": 1.15}[ventana]
            for clave, _, _, p50, p95, _ in COMPONENTES:
                if p50 is None:
                    continue
                db.add(M.LatencyWindow(tenant_id=TENANT, window=ventana, component_key=clave,
                                       p50_ms=int(p50 * f), p95_ms=int(p95 * f),
                                       sample_count=random.randint(4000, 90000)))
        # Las cinco claves son las de admin.critical_processes, que trae el DDL.
        PROCESOS = [("fall_alert", 7.8, .9995), ("sos", 4.2, .9997),
                    ("missed_medication", 11.2, .9988), ("ai_query", 2.4, .9971),
                    ("music_sync", 95.0, .9958)]
        for clave, p95, exito in PROCESOS:
            db.add(M.CriticalProcessState(
                tenant_id=TENANT, process_key=clave, p95_seconds=p95, success_24h=exito,
                status="operational" if exito > .997 else "degraded",
                based_on_synthetic=True, last_run_at=NOW - timedelta(minutes=random.randint(1, 50))))
        # severity solo admite degraded u outage; los mantenimientos se marcan con
        # is_maintenance, y solo ellos pueden terminar en completed.
        INCIDENTES = [
            ("Retraso en notificaciones push de Android", "push", "degraded", "investigating", False,
             "Entrega media de 42 s frente a los 8 s habituales. En análisis con el proveedor.", 2, None),
            ("Mantenimiento de PostgreSQL Flexible", "database", "degraded", "completed", True,
             "Actualización menor sin corte de servicio mediante réplica y failover.", 9,
             "Completado sin incidencias."),
            ("Latencia alta en la ingesta de wearables", "wearable_ingest", "degraded", "resolved", False,
             "Pico de latencia por reintentos acumulados tras una caída del proveedor.", 17,
             "Resuelto tras ampliar la ventana de reintento."),
        ]
        for titulo, comp, sev, estado, mantenimiento, desc, hace, resolucion in INCIDENTES:
            db.add(M.Incident(
                tenant_id=TENANT, title=titulo, component_key=comp, severity=sev, status=estado,
                description=desc, started_at=NOW - timedelta(days=hace),
                is_maintenance=mantenimiento, resolution=resolucion,
                resolved_at=NOW - timedelta(days=hace - 1) if resolucion else None,
                created_by=soporte.id))

        await db.flush()

        # ---- Tickets ----
        # Los tickets del seed llevan número explícito, igual que el prototipo y el
        # wireframe (#1482 el más reciente). Al final se ajusta el correlativo para
        # que los que cree la API sigan desde ahí (trg_ticket_number).
        # requester_user_id: los tickets de canal app los abre un usuario con cuenta;
        # se le da un id estable derivado del correo (referencia lógica a app.users).
        def id_usuario(correo: str) -> uuid.UUID:
            return uuid.uuid5(uuid.NAMESPACE_URL, f"agecare-app-user:{correo}")

        NUMERO_MAS_RECIENTE = 1482
        tickets = []
        destacados = []
        for i, (asunto, cat, prio, estado, rol) in enumerate(D.subjects):
            creado = NOW - timedelta(days=i, hours=3)
            cerrado = estado in ("resolved", "closed")
            t = M.Ticket(
                tenant_id=TENANT, subject=asunto, description=f"Detalle del caso: {asunto}.",
                number=NUMERO_MAS_RECIENTE - i, requester_user_id=id_usuario(f"usuario{i + 1}@demo.cl"),
                requester_name=f"Usuario Demo {i + 1}", requester_email=f"usuario{i + 1}@demo.cl",
                requester_role_code=rol, requester_plan_code=random.choice(["free", "gold", "platinum"]),
                category_code=cat, priority=prio, status=estado, channel="app", created_at=creado,
                requester_context={"patients": [{"display_name": "Paciente Demo"}],
                                   "devices": [{"platform": "android", "app_version": "1.0.3"}]},
                assigned_to=soporte.id if estado != "open" else None,
                first_response_at=creado + timedelta(hours=2) if estado != "open" else None,
                resolved_at=creado + timedelta(hours=20) if cerrado else None,
                closed_at=creado + timedelta(hours=72) if estado == "closed" else None,
                created_by=soporte.id)
            db.add(t)
            tickets.append(t)
            destacados.append(t)

        actual = ["resolved"] * 211 + ["open"] * 36 + ["in_progress"] * 19 + ["waiting_user"] * 9
        previa = ["resolved"] * 170 + ["closed"] * 30
        random.shuffle(actual)
        random.shuffle(previa)
        historico = ([(e, random.uniform(0, 29)) for e in actual] +
                     [(e, random.uniform(34, 59)) for e in previa])
        for j, (estado, dias) in enumerate(historico):
            cerrado = estado in ("resolved", "closed")
            creado = NOW - timedelta(days=dias)
            t = M.Ticket(
                tenant_id=TENANT, subject=f"Caso histórico {j + 1}",
                description="Ticket histórico de demo.",
                number=NUMERO_MAS_RECIENTE - len(D.subjects) - j,
                requester_user_id=id_usuario(f"hist{j}@demo.cl"),
                requester_name="Usuario Demo", requester_email=f"hist{j}@demo.cl",
                requester_role_code=random.choice(ROLE_ORDER),
                category_code=D.CATS[j % len(D.CATS)],
                priority=random.choice(["low", "medium", "medium", "high"]),
                status=estado, channel="app", created_at=creado,
                assigned_to=soporte.id if estado != "open" else None,
                first_response_at=creado + timedelta(hours=random.uniform(.3, 4.5)),
                resolved_at=creado + timedelta(hours=random.uniform(4, 48)) if cerrado else None,
                # El esquema exige closed_at exactamente cuando el estado es closed.
                closed_at=creado + timedelta(hours=72) if estado == "closed" else None,
                created_by=soporte.id)
            db.add(t)
            tickets.append(t)
        await db.flush()
        await db.execute(text(
            "INSERT INTO admin.tenant_counters (tenant_id, counter_name, next_value) "
            "VALUES (:t, 'ticket_number', :n) ON CONFLICT (tenant_id, counter_name) "
            "DO UPDATE SET next_value = EXCLUDED.next_value"),
            {"t": str(TENANT), "n": NUMERO_MAS_RECIENTE + 1})

        # ---- Conversación y satisfacción ----
        CIERRES = ["Damos por resuelto el caso. Si vuelve a ocurrir, responde a este mismo ticket.",
                   "Confirmado por el usuario que ya funciona. Cerramos el ticket.",
                   "Solucionado. Quedamos atentos por si necesitas cualquier otra cosa."]
        NOTAS = ["Nota interna: tercer caso esta semana con el mismo modelo de wearable.",
                 "Nota interna: usuario en plan Dorado, sin incidencias previas.",
                 "Nota interna: escalado al turno de tarde por si responde fuera de horario."]
        for t in tickets:
            # El trigger del esquema impide responder a un ticket cerrado (TICKET_CLOSED),
            # así que el histórico cerrado se queda sin hilo. Es coherente: nadie escribe
            # en un ticket ya cerrado.
            if t.status == "closed":
                continue
            if t not in destacados and random.random() >= .66:
                continue
            pregunta, respuesta = D.HILOS.get(t.category_code, D.HILOS["other"])
            # El esquema exige que cada mensaje identifique a su autor: author_admin_id
            # si lo escribe el staff, author_user_id si lo escribe el usuario.
            db.add(M.TicketReply(tenant_id=TENANT, ticket_id=t.id, author_type="user",
                                 author_user_id=uuid.uuid4(),
                                 author_name=t.requester_name, body=pregunta,
                                 created_at=t.created_at + timedelta(minutes=1)))
            if t.first_response_at:
                db.add(M.TicketReply(tenant_id=TENANT, ticket_id=t.id, author_type="admin",
                                     author_admin_id=soporte.id, author_name=soporte.full_name,
                                     body=respuesta, created_at=t.first_response_at))
                if t in destacados or random.random() < .25:
                    db.add(M.TicketReply(tenant_id=TENANT, ticket_id=t.id, author_type="admin",
                                         author_admin_id=soporte.id, author_name=soporte.full_name,
                                         body=random.choice(NOTAS), is_internal=True,
                                         created_at=t.first_response_at + timedelta(minutes=12)))
            if t.resolved_at:
                db.add(M.TicketReply(tenant_id=TENANT, ticket_id=t.id, author_type="admin",
                                     author_admin_id=soporte.id, author_name=soporte.full_name,
                                     body=random.choice(CIERRES), created_at=t.resolved_at))
        # La satisfacción ya no es una columna del ticket: es una encuesta aparte.
        for t in tickets:
            if t.resolved_at and random.random() < .55:
                db.add(M.SupportCsatSurveys(
                    tenant_id=TENANT, ticket_id=t.id, sent_at=t.resolved_at,
                    responded_at=t.resolved_at + timedelta(hours=random.uniform(1, 40)),
                    score=random.choice([5, 5, 5, 5, 5, 5, 5, 4, 4, 3])))

        # ---- Contenido, marketplace y moderación ----
        for k, (titulo, cuerpo, tags) in enumerate(D.CHISTES + D.NOTICIAS):
            tipo = "joke" if k < len(D.CHISTES) else "news"
            if k % 7 == 3:
                estado, publicado, programado = "draft", None, None
            elif k % 7 == 5:
                estado, publicado, programado = "draft", None, NOW + timedelta(days=2)
            elif k % 7 == 6:
                estado, publicado, programado = "archived", NOW - timedelta(days=40), None
            else:
                estado, publicado, programado = "published", NOW - timedelta(days=k + 1), None
            # El esquema exige archived_at exactamente cuando el estado es archived.
            db.add(M.ContentItem(tenant_id=TENANT, type=tipo, title=titulo, body=cuerpo, tags=tags,
                                 status=estado, publish_at=programado, published_at=publicado,
                                 archived_at=NOW - timedelta(days=5) if estado == "archived" else None,
                                 tts_status="ready", created_at=NOW - timedelta(days=k + 3),
                                 created_by=editor.id))

        for nombre, zona, esp, idiomas, certs, verif, rating, reviews, estado in D.CUIDADORAS:
            db.add(M.CaregiverProfile(
                caregiver_id=uuid.uuid4(), tenant_id=TENANT, display_name=nombre,
                email=nombre.split()[0].lower() + "@cuidado.cl", zone=zona, specialties=esp,
                languages=idiomas, certifications_count=certs,
                certifications_verified_count=certs if verif else 0,
                rating_avg=rating, reviews_count=reviews, status=estado,
                submitted_at=NOW - timedelta(days=random.randint(3, 120)),
                status_reason="Reseñas reiteradas por impuntualidad." if estado == "suspended" else None,
                reviewed_by=editor.id if estado != "pending" else None,
                reviewed_at=NOW - timedelta(days=5) if estado != "pending" else None))

        for nombre, cat, prov, precio, estado in D.ARTICULOS:
            slug = nombre.lower().replace(" ", "-")[:40]
            db.add(M.Product(tenant_id=TENANT, name=nombre, category=cat, vendor=prov,
                             price_amount=precio, external_url=f"https://{prov.lower()}.cl/{slug}",
                             status=estado,
                             published_at=NOW - timedelta(days=10) if estado == "published" else None,
                             archived_at=NOW - timedelta(days=3) if estado == "archived" else None,
                             created_by=editor.id))

        for tipo, autor, rol, contenido, reporte, motivo, seguridad in D.PENDIENTES:
            db.add(M.ModerationItem(
                tenant_id=TENANT, item_type=tipo, source_entity_id=uuid.uuid4(),
                content_snapshot=contenido, author_user_id=uuid.uuid4(), author_name=autor,
                author_role_code=rol,
                # Un reporte de seguridad exige saber quién lo levantó.
                reported_by_user_id=uuid.uuid4() if reporte else None,
                reported_by_name=(reporte or {}).get("name"),
                report_reason=motivo, is_safety_report=bool(seguridad and reporte), status="pending",
                created_at=NOW - timedelta(days=random.uniform(0, 12))))

        # ---- Auditoría ----
        NAVEGADORES = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0",
                       "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) Safari/18.0"]
        cuentas = list(staff.values())
        for accion, entidad in [("auth.login", "admin_user"), ("ticket.update", "ticket"),
                                ("ticket.reply", "ticket"), ("content.publish", "content_item"),
                                ("settings.update", "system_setting"), ("moderation.approve", "moderation_item"),
                                ("auth.login_failed", "admin_user")]:
            for _ in range(8):
                quien = random.choice(cuentas)
                db.add(M.AuditLog(
                    tenant_id=TENANT, actor_id=quien.id, actor_name=quien.full_name,
                    actor_role=quien.role_code, action=accion, entity_type=entidad,
                    entity_id=uuid.uuid4(),
                    after=None if accion.startswith("auth.") else {"status": "nuevo"},
                    ip=f"200.{random.randint(1,120)}.{random.randint(1,250)}.{random.randint(2,250)}",
                    user_agent=random.choice(NAVEGADORES),
                    # audit_log está particionada por mes y el DDL crea las particiones
                    # desde el mes en curso. Las entradas se mantienen dentro de ese
                    # rango; un histórico más largo exigiría crear particiones antiguas.
                    created_at=NOW - timedelta(days=random.uniform(0, max(1, NOW.day - 1)),
                                               hours=random.uniform(0, 23))))

        total_tickets = len(tickets)
        await db.commit()
    await engine.dispose()
    print(f"Esquema canónico sembrado: {len(STAFF)} cuentas de staff, "
          f"{total_tickets} tickets, {len(FEATURES)} funcionalidades, métricas de 14 meses.")


if __name__ == "__main__":
    asyncio.run(seed())
