# Modelo de datos canónico

Fuente de verdad del esquema de la Consola de Administración, definida en
`AgeCare_Consola_Admin_Modelo_de_Datos_v1.docx`. El código de este repositorio
se adapta a este modelo, no al revés (documento, sección 1.2).

| Archivo | Qué es |
|---|---|
| `agecare_admin_ddl.sql` | DDL ejecutable e idempotente. 1.339 líneas. Crea el esquema `admin` con 58 tablas (49 base + 9 de historial, según el reparto del documento), 35 particiones, 45 triggers, 45 políticas de seguridad por fila, 177 índices y 19 funciones. Cifras medidas sobre PostgreSQL 16 tras aplicarlo. |
| `agecare_admin_ddl_tests.sql` | 17 comprobaciones sobre el DDL: aislamiento entre tenants, LAST_ADMIN, transiciones, VERSION_CONFLICT, inmutabilidad del registro de auditoría, moderación única, inmutabilidad de versiones legales. |
| `agecare_admin.dbml` | Modelo lógico. Importable en dbdiagram.io. |
| `erd/` | Diagramas entidad-relación por módulo, en SVG. Los PNG equivalentes están en la carpeta del proyecto en Drive; aquí se omiten porque pesan 6,5 MB. |

## Aplicarlo

Requiere PostgreSQL 16 y las extensiones `citext` y `pg_trgm`.

Lo más cómodo es el script del proyecto, que no necesita tener `psql` en el PATH
(el instalador de Windows no lo añade) y funciona igual en cualquier sistema:

```bash
set ADMIN_DATABASE_URL=postgresql+asyncpg://usuario:clave@host/neondb?ssl=require
python -m scripts.aplicar_modelo --tests
```

Acepta la URL tanto en forma asyncpg como tal cual la entrega Neon para `psql`.

Con `psql` directamente:

```bash
psql -v ON_ERROR_STOP=1 -d agecare_canonico -f modelo/agecare_admin_ddl.sql
psql -v ON_ERROR_STOP=1 -d agecare_canonico -f modelo/agecare_admin_ddl_tests.sql
```

El DDL es idempotente: ejecutarlo dos veces no da error.

### Dónde ejecutar cada cosa

| | Neon | PostgreSQL local |
|---|---|---|
| DDL (`aplicar_modelo`) | sí, verificado | sí |
| Pruebas (`--tests`) | no | sí |

Las pruebas hacen `SET ROLE` para comprobar la seguridad por fila y los permisos por
rol. En un PostgreSQL local eres superusuario y eso vale para cualquier rol; en Neon
el rol propietario no lo es y PostgreSQL 16 separa el permiso de conmutar (SET) del
de administrar (ADMIN). El script intenta concedérselo, y si no puede lo dice en vez
de soltar el error en crudo. **No es un problema del DDL**: el esquema se aplica bien
en Neon, y las pruebas validan el mismo SQL corran donde corran.

**Las pruebas no son idempotentes.** Insertan tenants, cuentas y tickets de mentira para
comprobar las reglas, y no limpian al terminar: ejecutadas dos veces con `psql`
fallan por clave duplicada, y dejan esas filas en la base. El script las envuelve
en una transacción que revierte siempre, así que con `--tests` se pueden repetir
cuantas veces haga falta y no ensucian nada.

## Estado de la migración

Desde el cierre de la fase 3, la API corre entera sobre el esquema canónico `admin`;
el esquema del prototipo (`public`) ya no se usa.
La sección 7 del documento enumera las diferencias y la 8 propone seis migraciones.

- [x] Fase 0 · Tests sobre PostgreSQL en vez de SQLite; modelo canónico versionado aquí; script `scripts/aplicar_modelo.py`
- [x] Fase 1 · Migración Alembic (`0002_modelo_canonico`) y modelos generados en `app/models_canonico.py`
- [x] Fase 2 · Tenant en el token, contexto por transacción y traducción de errores de la base
- [x] Fase 3 · Routers adaptados a los nombres nuevos — 50 de 50 endpoints
  - [x] Auth y staff (3.1–3.7), más `deps.py` y `audit.py`, que usan todos los routers
  - [x] Comercial (4) · Perfiles (2) · Funcionalidades (3). Periodos en la zona
        horaria del tenant; embudo desde `metrics_funnel_snapshot`; ventana de perfiles
        = la menor precalculada que cubra lo pedido; umbral de alertas por defecto desde
        `feature_adoption_low_threshold`
  - [x] Operativo e incidentes (6). Transiciones leídas de `incident_status_transitions`
        (un mantenimiento se completa, no se resuelve)
  - [x] Tickets y soporte (8). Transiciones, fechas, reaperturas, número correlativo y
        primera respuesta los ponen los triggers; CSAT desde `support_csat_surveys`. Un
        ticket previo solo identifica al usuario si estaba enlazado a su cuenta
  - [x] Contenido (6) · Marketplace (5) · Moderación (3). Los nombres de quién creó,
        revisó o decidió se resuelven desde `admin_users` (`app/staff.py`); el filtro por
        especialidad se hace en la base, antes de paginar
  - [x] Configuración (2) · Legales (3) · Auditoría (1). Esquema y descripción de cada
        parámetro desde `setting_definitions`; la matriz de permisos por rol se lee de
        `admin_role_permissions` (ya no está duplicada en `enums.py`)
- [ ] Fase 4 · Seed con tenants y catálogos
- [ ] Fase 5 · Verificación contra las tres auditorías

### Cómo se regeneran los modelos

`app/models_canonico.py` está generado, no escrito a mano. Si el DDL cambia:

```bash
createdb canonico
python -m scripts.aplicar_modelo --url "postgresql://postgres:postgres@127.0.0.1:5432/canonico"
python -m scripts.generar_modelos
```

Mapea las 58 tablas lógicas (no las particiones), declara una Base propia para no
mezclarse con la del prototipo, y renombra quince clases a los nombres que ya usan
los routers. Verificado contra la base: 58 tablas y 613 columnas, coincidencia exacta.

Mientras dure la transición conviven los dos esquemas: el prototipo en `public` y el
canónico en `admin`. `alembic upgrade head` crea ambos. Al terminar la fase 3 se
elimina la revisión 0001 y `public` queda vacío.

El criterio de que la migración no rompió nada son las suites que ya existen:
23 tests, 19 comprobaciones de permisos y 80 de conformidad con la especificación.
El contrato de la API no cambia, así que deben seguir dando lo mismo.

## Divergencias detectadas y cómo se resolvieron

Comparación hecha aplicando el DDL sobre PostgreSQL 16 y contrastando sus catálogos
con los valores del código. Coinciden al valor exacto: roles de staff (5), roles de la
app (4), planes (4), categorías de ticket (6) y componentes de operación (9).

| Divergencia | Quién se desviaba | Resolución |
|---|---|---|
| El backend permitía `open → resolved` y `waiting_user → resolved` | Nosotros | Corregido. Las transiciones son las seis de la sección 8.4, que coinciden con `ticket_status_transitions`. La consola web ofrece las mismas. |
| El backend permitía `observing → investigating` en incidentes | Nosotros | Corregido. Cuatro transiciones, como en `incident_status_transitions`. |
| `allowed_email_domains` y `feature_adoption_low_threshold` estaban fijos en el código | Nosotros | Sembrados como parámetros. Conectarlos al código es trabajo de la fase 3. |
| La matriz daba al admin lectura sobre auditoría; el modelo da escritura | Nosotros | Alineado. No hay endpoint que escriba en el registro, pero la matriz queda literal para poder cargarla de `admin_role_permissions`. |

### Resuelto: el catálogo de funcionalidades

`admin.features` define 10 funcionalidades y el wireframe mostraba 15. El equipo
decidió **trabajar con las 10 del modelo** y valorar más adelante si se incorporan
`alert_center`, `vitals`, `logbook`, `chat` y `documents`.

El seed ya usa el catálogo oficial. No era solo quitar cinco: el modelo también
renombra `home_status` a `home_traffic_light` y cambia a qué perfiles aplica cada
función. Se adoptaron ambas cosas, así que `admin.feature_roles` y el seed coinciden
en los 21 pares función/rol. El mapa de calor de la consola pasa de 15 filas a 10.

## Con qué rol debe conectarse la aplicación

Comprobado en PostgreSQL 16: declarando el mismo tenant y ejecutando la misma
consulta, el propietario de las tablas ve los datos de **todos** los tenants y un
rol miembro de `agecare_admin_api` ve solo los suyos.

| Conexión | Tenants visibles |
|---|---|
| Propietario de las tablas | 2 — se salta el aislamiento |
| Miembro de `agecare_admin_api` | 1 — aislado |

La causa es que el DDL activa la seguridad por fila pero no la fuerza
(`FORCE ROW LEVEL SECURITY` no aparece), y en PostgreSQL el propietario de una tabla
queda exento salvo que se fuerce.

**Consecuencia para el despliegue:** en Neon la aplicación se conecta hoy como
`neondb_owner`, que es quien creó las tablas. Si se deja así, las 45 políticas de
aislamiento no protegerían nada. Antes de la fase 3 hay que crear un rol de login
miembro de `agecare_admin_api` y apuntar `ADMIN_DATABASE_URL` a él:

```sql
CREATE ROLE agecare_api LOGIN PASSWORD '…' IN ROLE agecare_admin_api;
```

Consultado al autor del modelo: responde que hagamos lo que menos moleste hasta la
entrega al usuario final. Se opta por **crear el rol desde ya**, no por dejarlo para
el final:

```bash
python -m scripts.aplicar_modelo --rol-api "agecare_api:CLAVE"
```

El motivo es que activar el aislamiento el último día convierte un problema pequeño
y repartido en uno grande y concentrado. Con el rol puesto desde el principio, cada
consulta que escribamos en la fase 3 se ejerce ya bajo las políticas y los fallos
aparecen de uno en uno, cuando son baratos de arreglar. El coste de hacerlo ahora es
una sentencia SQL y una variable de entorno.

Verificado: con el rol de la aplicación se ve un solo tenant; con el propietario, dos.

## Cierre de la fase 3

Durante la migración convivieron los dos esquemas con tres apoyos temporales, ya
retirados: la propiedad `role` de compatibilidad (`app/compat.py`), los permisos de la
API sobre `public` y el doble seed de los tests. Hoy:

- La suite y las dos auditorías corren con la API conectada como `agecare_api`, que
  ya no tiene permisos sobre las tablas de `public`: si algún router volviera a leer
  el prototipo, fallaría de inmediato.
- `aplicar_modelo.py --rol-api` retira esos permisos en las bases donde se habían
  concedido (es idempotente).
- Las tablas del prototipo en `public` y la revisión Alembic `0001` siguen existiendo,
  sin uso. Borrarlas queda como limpieza opcional, junto con `app/models.py` y
  `scripts/seed.py`.

**Particiones del registro de auditoría.** `audit_log` está particionada por mes y una
fila sin partición hace fallar la escritura (y con ella el login). El DDL solo prepara
hasta dos meses adelante y no hay un job que corra `admin.partition_maintenance()`.
Como solución de MVP, `aplicar_modelo.py` deja creadas las particiones de los
próximos 12 meses cada vez que se ejecuta; `verificar_base.py` muestra hasta qué mes
está cubierto y avisa si no llega al mes siguiente. Basta con volver a ejecutar
`aplicar_modelo.py` una vez al año (o programar el job, fuera de alcance).

**Secreto MFA.** El modelo pide guardar el secreto TOTP cifrado por la aplicación
con Key Vault (`mfa_secret_enc`). Eso pertenece al despliegue en Azure, fuera del
alcance académico. En la demo se guardan los bytes del secreto sin cifrar.

**Bloqueo de login.** Se calcula contando en `admin_login_attempts` las contraseñas
incorrectas de los últimos 10 minutos, desde el último login correcto o el fin del
último bloqueo (spec 3.1: "persistido, no en memoria").
