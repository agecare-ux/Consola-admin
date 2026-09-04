# Despliegue en Vercel — AgeCare Admin API

Guía del primer despliegue de la API de la Consola de Administración en Vercel,
con Postgres externo (Neon). Camino hacia producción real: cada paso indica qué
queda resuelto y qué queda pendiente.

---

## 0. Antes de empezar

Necesitas:

- Cuenta de Vercel.
- Vercel CLI: `npm i -g vercel`
- El proyecto en un repositorio Git (GitHub, GitLab o Bitbucket) si quieres
  despliegues automáticos en cada push.
- Python 3.12 local, para correr las migraciones.

**Verifica primero que el proyecto corre en tu máquina.** No despliegues nada
que no hayas visto funcionar localmente:

```bash
docker compose up --build
curl http://localhost:8000/health
```

---

## 1. Crear la base de datos

Vercel no aloja bases de datos: te conecta con quien sí lo hace. Vercel Postgres
pasó a ser la integración nativa de Neon en el Vercel Marketplace.

1. En el dashboard de Vercel: **Storage → Create Database → Neon**.
2. Elige la región **más cercana a la región de tus funciones** (`iad1` /
   `us-east-1` es el default de Vercel). Si la base queda en otro continente,
   cada consulta paga el viaje de ida y vuelta.
3. Nombra la base `agecare_admin`.

Al terminar, Neon te da **dos** connection strings. Los dos importan y sirven
para cosas distintas:

| String | Cómo se reconoce | Para qué |
|---|---|---|
| **Agrupado (pooled)** | el host contiene `-pooler` | La API en Vercel |
| **Directo** | sin `-pooler` | Alembic (migraciones) y el seed |

### Por qué el agrupado no es opcional

Un servidor tradicional abre unas pocas conexiones de larga vida. Serverless
invierte eso: cada instancia de función puede abrir la suya, y una ráfaga de
tráfico levanta decenas de instancias en segundos. Postgres tiene un tope de
conexiones, así que una ráfaga se convierte directamente en
`FATAL: sorry, too many clients already` justo cuando tienes usuarios.

El pooler (PgBouncer) absorbe eso. **Pero PgBouncer en modo transacción rompe
los prepared statements de asyncpg** — ya está resuelto en `app/database.py`,
ver paso 5.

---

## 2. Adaptar el connection string a asyncpg

Neon entrega el string en formato `postgresql://…?sslmode=require`. Este
proyecto usa el driver **asyncpg**, que necesita dos cambios:

```
# Lo que te da Neon:
postgresql://usuario:clave@ep-abc-123-pooler.us-east-1.aws.neon.tech/agecare_admin?sslmode=require

# Lo que va en ADMIN_DATABASE_URL:
postgresql+asyncpg://usuario:clave@ep-abc-123-pooler.us-east-1.aws.neon.tech/agecare_admin
```

1. `postgresql://` → `postgresql+asyncpg://`
2. Quita `?sslmode=require`. asyncpg no entiende ese parámetro y falla al
   conectar; negocia TLS por su cuenta contra Neon.

Haz lo mismo con el string **directo**, que usarás en el paso siguiente.

---

## 3. Crear las tablas y sembrar los datos

Las migraciones **no corren en Vercel**. Ahí no hay un paso de build donde
ejecutar comandos contra la base, y aunque lo hubiera, correr Alembic en cada
despliegue es mala idea. Se ejecutan desde tu máquina (o desde CI) una sola vez,
contra el string **directo**:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ADMIN_DATABASE_URL="postgresql+asyncpg://usuario:clave@ep-abc-123.us-east-1.aws.neon.tech/agecare_admin"

alembic upgrade head
```

### El seed: cuidado

`scripts/seed.py` **borra todas las tablas antes de sembrar**. Es correcto para
una demo, es destructivo para cualquier otra cosa.

- Si quieres ver la consola con datos: córrelo **una vez**, ahora.
- Si esto va camino a datos reales: **no lo corras**, y crea tu primera cuenta
  de staff a mano.

```bash
python -m scripts.seed    # solo si quieres los datos demo del wireframe
```

Nota: el seed ancla sus datos al 28 de agosto de 2026. El KPI "mes en curso"
mostrará ceros si hoy es otro mes. No está roto.

---

## 4. Variables de entorno en Vercel

En **Project Settings → Environment Variables**. Estas cuatro son obligatorias:

| Clave | Valor | Ámbito |
|---|---|---|
| `ADMIN_DATABASE_URL` | El string **agrupado**, en formato asyncpg (paso 2) | Production, Preview |
| `ADMIN_JWT_SECRET` | Genéralo con `openssl rand -hex 32` | Production, Preview |
| `ADMIN_ENVIRONMENT` | `prod` | Production |
| `ADMIN_CORS_ORIGINS` | El origen de tu consola web, p. ej. `https://consola.agecare.app` | Production, Preview |

Opcionales: `ADMIN_ALLOWED_EMAIL_DOMAINS` (default `wellq.co.uk,wellq.co`).

**No subas el archivo `.env`.** Ya está en `.vercelignore`.

`app/config.py` ahora valida esto al arrancar: si `ADMIN_ENVIRONMENT=prod` y el
secreto JWT sigue siendo el de ejemplo o mide menos de 32 caracteres, la app
falla al iniciar en vez de arrancar insegura. Lo mismo si falta CORS.

---

## 5. Qué se cambió en el código y por qué

Estos cambios ya están aplicados. Los tests (23) siguen pasando.

### `app/database.py` — la trampa de asyncpg + PgBouncer

Sin esto, en producción aparece de forma **intermitente**:

```
asyncpg.exceptions.DuplicatePreparedStatementError:
prepared statement "__asyncpg_stmt_a__" already exists
```

La función `_engine_kwargs()` detecta el modo serverless y aplica:

- **`NullPool`**: SQLAlchemy deja de mantener su propio pool encima del pooler
  remoto. Ese doble pooling es un problema sutil que muchos equipos no saben que
  tienen.
- **Las dos cachés apagadas**: `statement_cache_size` (la principal) y
  `prepared_statement_cache_size` (una LRU secundaria a la que asyncpg recurre).
  Muchas guías solo mencionan la primera; el error entonces baja de frecuencia
  pero no desaparece, y reaparece semanas después.
- **`prepared_statement_name_func`** con UUID, para que dos conexiones distintas
  del pooler nunca colisionen de nombre.

En Docker o en una VM nada de esto aplica: ahí se usa el pool normal con
`pool_pre_ping`. La detección es automática vía la variable `VERCEL` que la
plataforma inyecta.

### `app/main.py` — CORS y docs

- **CORS**: no existía. Sin él, tu consola web recibe cada respuesta bloqueada
  por el navegador aunque la API conteste 200. Se activa solo si
  `ADMIN_CORS_ORIGINS` tiene contenido.
- **Docs cerradas en producción**: `/docs` y `/openapi.json` devuelven 404
  cuando `ADMIN_ENVIRONMENT=prod`. La consola es interna; su esquema completo no
  debe ser público. Para reabrirlas temporalmente: `ADMIN_EXPOSE_DOCS=true` no
  basta, hay que bajar `ADMIN_ENVIRONMENT`.

### Archivos nuevos

- **`vercel.json`**: excluye tests, scripts, alembic y archivos `.db` del
  bundle. Las funciones de Python no pasan por tree-shaking: Vercel empaqueta
  todo archivo alcanzable en build, hasta un límite de 500 MB.
- **`.python-version`**: fija 3.12 (que además es el default del runtime).
- **`.vercelignore`**: evita subir `.env`, el venv y artefactos locales.

---

## 6. Desplegar

No configuras build command ni output directory: Vercel trae detección de
FastAPI sin configuración. Busca una instancia llamada `app` en un punto de
entrada reconocido — `app.py`, `index.py`, `server.py`, `main.py`, `wsgi.py` o
`asgi.py`, en la raíz o bajo `src/`, `app/` o `api/`. Este proyecto ya cumple
con `app/main.py`.

**Desde la CLI:**

```bash
vercel          # primer despliegue: crea el link del proyecto (preview)
vercel --prod   # despliegue de producción
```

**Desde Git:** haz push e importa el repo en `vercel.com/new`. Cada push a la
rama principal despliega a producción; las demás ramas generan previews.

**Para desarrollo local**, usa `vercel dev` en vez de uvicorn directo: sirve la
app igual que producción, con la misma instancia `app`, así que lo que pruebas
coincide con lo que despliegas.

Tu app corre como **una sola Vercel Function** sobre Fluid compute, que atiende
varias peticiones concurrentes dentro de una misma instancia. Eso reduce
arranques en frío y abarata el trabajo ligado a E/S como las consultas a la base
de datos — que es casi todo lo que hace esta API.

---

## 7. Verificar el despliegue

```bash
BASE=https://tu-proyecto.vercel.app

curl -s $BASE/health
# {"status":"ok","service":"AgeCare Admin API","environment":"prod"}

TOKEN=$(curl -s $BASE/api/v1/admin/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@wellq.co.uk","password":"Admin123!"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s "$BASE/api/v1/admin/ops/status" -H "Authorization: Bearer $TOKEN"
curl -s "$BASE/api/v1/admin/metrics/commercial/plans" -H "Authorization: Bearer $TOKEN"
```

Si el login falla con error 500, revisa los logs en **Observability**: casi
siempre es el connection string (formato asyncpg, o el `sslmode` que quedó).

**Cambia las contraseñas del seed inmediatamente si desplegaste con datos demo.**
Están publicadas en el README.

---

## 8. Lo que queda pendiente para producción real

Esto no es opcional a mediano plazo; es lo que Vercel no resuelve por ti.

### 8.1 Los jobs de agregación no existen

Los endpoints analíticos leen tablas agregadas (`metrics_daily_users`,
`feature_usage_window`, `ops_latency_window`…) que en producción llenan jobs
programados. Esos jobs **no están escritos**. Hoy solo el seed las llena, así
que las métricas quedan congeladas.

En Vercel esto se hace con Cron Jobs: disparan una ruta enviándole un GET según
un horario, y **solo corren en despliegues de producción**. Necesitas escribir
las rutas y registrarlas:

```python
# app/routers/cron.py
import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/cron", tags=["Cron"])

@router.get("/aggregate-daily")
async def aggregate_daily(request: Request):
    if request.headers.get("authorization") != f"Bearer {os.environ.get('CRON_SECRET')}":
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    # ... recalcular metrics_daily_users, metrics_plan_snapshot, etc.
    return {"ok": True}
```

```json
{
  "crons": [
    { "path": "/api/v1/admin/cron/aggregate-daily", "schedule": "0 6 * * *" }
  ]
}
```

Define `CRON_SECRET` en las variables de entorno del proyecto: Vercel lo envía
como token Bearer en el header `Authorization` de cada invocación, y tu handler
lo compara antes de ejecutar. Sin eso, cualquiera puede disparar tus jobs.

Nota sobre la hora: el cron de Vercel corre en UTC. `0 6 * * *` son las 03:00 en
America/Santiago, que es lo que pide la especificación (sección 2.8).

### 8.2 Los health checks de 60 segundos no caben aquí

La spec pide `ops_component_checks` cada 60 s. La granularidad y el número de
crons dependen de tu plan de Vercel, y en cualquier caso un cron por minuto es
una forma cara y frágil de monitorear. Usa un servicio externo de monitoreo
(UptimeRobot, Better Stack, Checkly) que golpee `/health` y escriba en la tabla,
o mueve el monitor a un proceso fuera de Vercel.

### 8.3 La migración `0001` no es una migración real

Hace `Base.metadata.create_all()` en lugar de tener el DDL escrito. Arranca bien
la primera vez, pero el día que cambies un modelo,
`alembic revision --autogenerate` no tendrá contra qué comparar. Antes de tener
datos que te importen, genera una migración inicial de verdad con
`--autogenerate` contra una base vacía y reemplaza la actual.

### 8.4 El allowlist de IP de la spec no es viable

La sección 2.1 recomienda restringir el acceso por red (IP allowlist o VPN
corporativa) además de la autenticación. Eso no se implementa cómodamente en
funciones serverless públicas. Alternativas: Vercel Routing Middleware para
filtrar en el edge antes de que la petición llegue a FastAPI, o el firewall de
Vercel según tu plan. Si el allowlist es un requisito duro del proyecto, Vercel
es la plataforma equivocada para esta API.

### 8.5 Rotación del secreto JWT

Cambiar `ADMIN_JWT_SECRET` invalida todas las sesiones activas del staff. No es
un problema, pero conviene saberlo antes de hacerlo un viernes.
