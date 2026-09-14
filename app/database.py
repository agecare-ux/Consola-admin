"""Motor async de SQLAlchemy y sesión por petición."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(url: str) -> dict:
    """Opciones del engine según el driver.

    Con asyncpg detrás de un pooler (PgBouncer en modo transacción, que es lo que
    usan Neon y Supabase) hay dos incompatibilidades conocidas:

    1. asyncpg cachea *prepared statements* con nombres reutilizables; como el
       pooler reparte cada transacción por una conexión distinta, el servidor
       responde `DuplicatePreparedStatementError`. Se desactiva el caché.
    2. El pool propio de SQLAlchemy sobra: quien agrupa las conexiones es el
       pooler. Además, en entornos serverless el proceso puede morir en
       cualquier momento y dejar conexiones colgadas. NullPool abre y cierra
       por petición y deja el trabajo al pooler.

    Contra un PostgreSQL directo (Docker en local) esto sigue funcionando; solo
    se pierde el pool en memoria, irrelevante en desarrollo.
    """
    if url.startswith("postgresql+asyncpg://"):
        return {
            "poolclass": NullPool,
            "connect_args": {
                "statement_cache_size": 0,           # caché de asyncpg
                "prepared_statement_cache_size": 0,  # caché del dialecto SQLAlchemy
            },
        }
    return {"pool_pre_ping": True}


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        url = get_settings().database_url
        _engine = create_async_engine(url, **_engine_kwargs(url))
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI: una sesión por petición, commit al éxito."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
