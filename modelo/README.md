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

El código todavía corre sobre el esquema del prototipo (22 tablas, sin tenant).
La sección 7 del documento enumera las diferencias y la 8 propone seis migraciones.

- [x] Fase 0 · Tests sobre PostgreSQL en vez de SQLite; modelo canónico versionado aquí; script `scripts/aplicar_modelo.py`
- [x] Fase 1 · Migración Alembic (`0002_modelo_canonico`) y modelos generados en `app/models_canonico.py`
- [ ] Fase 2 · Tenant en login y JWT, `SET LOCAL` por transacción, traducción de errores de BD
- [ ] Fase 3 · Routers adaptados a los nombres nuevos
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

### Punto abierto: el catálogo de funcionalidades

`admin.features` define **10** funcionalidades y el wireframe muestra **15**. Faltan en
el modelo: `alert_center`, `vitals`, `logbook`, `chat` y `documents`. Además el modelo
llama `home_traffic_light` a lo que nosotros llamamos `home_status`.

De momento el seed mantiene las 15 del wireframe, para no hacer desaparecer filas del
mapa de calor sin que nadie lo haya decidido. **Hay que preguntar al equipo** si la
reducción a 10 es deliberada o un olvido, y adoptar la lista que confirmen antes de
la fase 4.
