# AgeCare — Admin API

Backend de la **Consola de Administración** de AgeCare (Wellq Co).
FastAPI · Python 3.12 · SQLAlchemy 2 async · PostgreSQL 16.

Corre sobre el **modelo de datos canónico** (esquema `admin`, multi-tenant con
seguridad por fila); ver `modelo/README.md`. Implementa los 50 endpoints de la *Especificación de Endpoints — Consola de
Administración v1*: autenticación de staff con MFA, las cuatro secciones
analíticas del wireframe (uso comercial, estado operativo, usuarios y soporte,
uso por funcionalidad) y los módulos de operación (tickets, curación de
contenido, catálogos del marketplace, moderación, configuración, legales y
auditoría).

## Arranque rápido (Docker)

```bash
docker compose up --build
```

Levanta PostgreSQL, aplica el modelo canónico, siembra datos demo y sirve la
consola en `http://localhost:8000`. Documentación interactiva (Swagger):
`http://localhost:8000/api/v1/admin/docs`.

## Arranque manual

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                  # ajusta ADMIN_DATABASE_URL si hace falta
python -m scripts.aplicar_modelo --rol-api "agecare_api:CLAVE"   # DDL + rol de la API (como propietario)
python -m scripts.seed_canonico       # datos demo del wireframe (como propietario)
python -m scripts.verificar_base      # comprueba que la base quedó lista
uvicorn app.main:app --reload         # la API, conectada como agecare_api
```

## Cuentas demo

El seed crea una cuenta por rol de staff (sección 2.3 de la especificación):

| Correo | Rol |
|---|---|
| admin@wellq.co.uk | admin (con segundo factor TOTP) |
| soporte@wellq.co.uk | soporte |
| analista@wellq.co.uk | analista |
| editora@wellq.co.uk | editor |
| moderador@wellq.co.uk | moderador |

Las contraseñas y el secreto TOTP **no están en el repositorio**: el seed y las
auditorías los leen de las variables `DEMO_*` (ver `.env.example`). Para generar un
juego nuevo y copiarlo al `.env`:

```bash
python -m scripts.credenciales_demo --generar
```

Quien reciba acceso para pruebas obtiene las contraseñas y el secreto por un canal
seguro. El rol admin exige segundo factor: el código de 6 dígitos se obtiene en una
app de autenticación (Google Authenticator, Microsoft Authenticator…) configurada con
`DEMO_MFA_SECRET`. Una cuenta admin sin TOTP configurado no puede iniciar sesión
(`403 MFA_NOT_CONFIGURED`).

## Probar con curl

```bash
BASE=http://localhost:8000/api/v1/admin

# Login
TOKEN=$(curl -s $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"analista@wellq.co.uk","password":"<clave>"}' | python3 -c \
  'import sys,json;print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

# Sección 1 · Uso comercial
curl -s "$BASE/metrics/commercial/summary?period=current_month" -H "$AUTH"
curl -s "$BASE/metrics/commercial/registrations?period=last_7_days" -H "$AUTH"
curl -s "$BASE/metrics/commercial/plans" -H "$AUTH"
curl -s "$BASE/metrics/commercial/funnel" -H "$AUTH"

# Sección 2 · Estado operativo
curl -s "$BASE/ops/status" -H "$AUTH"
curl -s "$BASE/ops/latency?window=1h" -H "$AUTH"
curl -s "$BASE/ops/incidents?days=30" -H "$AUTH"

# Sección 3 · Usuarios y soporte
curl -s "$BASE/metrics/roles/summary" -H "$AUTH"
curl -s "$BASE/metrics/roles/weekly-active?weeks=8" -H "$AUTH"
curl -s "$BASE/support/summary" -H "$AUTH"
curl -s "$BASE/support/tickets?status=open" -H "$AUTH"

# Sección 4 · Uso por funcionalidad
curl -s "$BASE/metrics/features/adoption?days=30" -H "$AUTH"
curl -s "$BASE/metrics/features/alerts?threshold=0.15" -H "$AUTH"
```

## Tests

```bash
pytest                          # 47 pruebas
python -m scripts.audit_spec    # conformidad con la especificación (96 comprobaciones)
python -m scripts.audit_roles   # matriz de permisos por rol
```

La suite necesita un PostgreSQL 16 (por defecto `localhost`, usuario y clave
`postgres`; se cambia con `ADMIN_TEST_DATABASE_URL`). Crea una base temporal,
aplica el DDL, siembra y corre la API con su rol propio, sujeta a la seguridad
por fila. Las dos auditorías usan la base de `ADMIN_DATABASE_URL`.

## Estructura

```
app/
  config.py        Configuración (pydantic-settings, prefijo ADMIN_)
  database.py      Engine async + sesión por petición
  errors.py        Formato estándar de error {error:{code,message,details,request_id}}
  enums.py         Enumeraciones (la matriz de permisos vive en la base)
  security.py      Argon2id, JWT (access 15 min / refresh 12 h rotatorio), TOTP
  deps.py          get_current_admin, require(módulo, write=…)
  audit.py         Escritura de audit_log con enmascarado de campos sensibles
  periods.py       Resolución de PeriodKey en la zona horaria del tenant + buckets
  staff.py         Nombres de staff para las respuestas (creado por, revisado por…)
  models_canonico.py  Modelos del esquema admin (generado desde el DDL)
  schemas/         Esquemas Pydantic por módulo
  routers/         Un router por módulo (prefijo común /api/v1/admin)
  static/console.html  La consola (una sola página, sin build)
modelo/            Modelo canónico: DDL (fuente de verdad), DBML, diagramas, README
alembic/           Revisión 0002: aplica el DDL canónico
scripts/
  aplicar_modelo.py     DDL, rol de la API y particiones de auditoría
  seed_canonico.py      Datos demo coherentes con el wireframe
  credenciales_demo.py  Cuentas demo; contraseñas y TOTP leídos del entorno
  verificar_base.py     Diagnóstico de una base (solo lectura)
  retirar_prototipo.py  Borra las tablas del prototipo que queden en public
  audit_spec.py, audit_roles.py   Auditorías contra la especificación
tests/             pytest + httpx (asyncio)
```

## Decisiones de implementación

- **Estrategia mixta de datos**: los endpoints analíticos leen tablas agregadas
  (`metrics_daily_users`, `metrics_plan_snapshot`, `role_activity_window`,
  `feature_usage_window`, `ops_latency_window`…) que en producción alimentan
  jobs; el seed las puebla directamente. El estado operativo se lee de la foto
  que mantiene el monitor (`ops_component_state`).
- **En la matriz de adopción, `null` ≠ `0.0`**: null = la función no aplica al
  rol (celda gris); 0.0 = disponible pero sin uso.
- **Refresh tokens rotatorios** con detección de reutilización: reusar un token
  rotado revoca todas las sesiones del administrador.
- **Bloqueo optimista** en configuración (`version`) y validación del valor
  contra el JSON Schema de cada parámetro.
- **Auditoría en toda mutación** y en logins (exitosos y fallidos), con
  campos sensibles enmascarados.
- Los puntos donde en producción se integraría correo, push, TTS o webhooks
  están marcados con comentarios en el código.
