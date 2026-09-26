"""Fixtures de test sobre PostgreSQL efímero.

Por qué PostgreSQL y no SQLite
------------------------------
El modelo de datos canónico (AgeCare_Consola_Admin_Modelo_de_Datos_v1, sección 7)
usa seguridad a nivel de fila, tablas particionadas, citext, text[] y triggers.
Nada de eso existe en SQLite, así que los tests dejarían de poder validar el
esquema real. Desde la fase 0 de la migración, la suite corre sobre PostgreSQL.

Cómo indicar el servidor
------------------------
Se toma de ADMIN_TEST_DATABASE_URL; si no está, se usa un PostgreSQL local:

    postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/postgres

Cada sesión de test crea una base de datos propia con nombre aleatorio
(agecare_test_xxxxxxxx), la usa y la elimina al terminar. Así dos ejecuciones
simultáneas no se pisan y nunca se toca una base con datos reales.

En Windows: instalar PostgreSQL 16 desde postgresql.org y, si la contraseña del
usuario postgres no es "postgres", definir la variable antes de lanzar pytest:

    set ADMIN_TEST_DATABASE_URL=postgresql+asyncpg://postgres:TUCLAVE@127.0.0.1:5432/postgres
"""
import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

SERVIDOR = os.environ.get(
    "ADMIN_TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/postgres",
)
BD_TEST = f"agecare_test_{uuid.uuid4().hex[:8]}"
URL_TEST = SERVIDOR.rsplit("/", 1)[0] + "/" + BD_TEST

# La app lee la configuración al importarse, así que hay que fijarla antes.
os.environ["ADMIN_DATABASE_URL"] = URL_TEST
os.environ["ADMIN_JWT_SECRET"] = "secreto-de-test-suficientemente-largo-123456"

import app.database as database  # noqa: E402
from app.database import Base  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def _sin_transaccion(sql: str) -> None:
    """CREATE/DROP DATABASE no pueden ejecutarse dentro de una transacción."""
    eng = create_async_engine(SERVIDOR, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with eng.connect() as conn:
            await conn.execute(text(sql))
    finally:
        await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def engine():
    try:
        await _sin_transaccion(f'CREATE DATABASE "{BD_TEST}"')
    except Exception as e:  # pragma: no cover - solo guía al desarrollador
        pytest.exit(
            f"\nNo se pudo crear la base de datos de test en {SERVIDOR.split('@')[-1]}.\n"
            f"  Detalle: {type(e).__name__}: {e}\n"
            "  Instala PostgreSQL 16 o define ADMIN_TEST_DATABASE_URL apuntando a uno.\n",
            returncode=1,
        )

    eng = create_async_engine(URL_TEST, poolclass=NullPool)
    database._engine = eng
    database._session_factory = async_sessionmaker(eng, expire_on_commit=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()
    await _sin_transaccion(f'DROP DATABASE IF EXISTS "{BD_TEST}" WITH (FORCE)')


@pytest_asyncio.fixture(scope="session")
async def seeded(engine):
    from scripts.seed import seed
    await seed()
    return True


@pytest_asyncio.fixture
async def client(seeded):
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_headers(client):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"email": "admin@wellq.co.uk", "password": "Admin123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def analyst_headers(client):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"email": "analista@wellq.co.uk", "password": "Analista123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
