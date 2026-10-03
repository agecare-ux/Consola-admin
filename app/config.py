"""Configuración de la API de administración de AgeCare."""
from functools import lru_cache

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def url_para_asyncpg(url: str) -> str:
    """Deja la URL de PostgreSQL en la forma que entiende asyncpg.

    Neon entrega `postgresql://...?sslmode=require&channel_binding=require`, pensada
    para psql. asyncpg necesita el esquema `postgresql+asyncpg://`, pide el cifrado
    con `ssl=` y no acepta `sslmode` ni `channel_binding` (falla con TypeError al
    conectar, que la API acababa devolviendo como un 500 sin pista). Aquí se acepta
    cualquiera de las dos formas, así la variable de Vercel puede pegarse tal cual.

    Solo reescribe: nunca lanza error, para no tapar con un fallo de validación el
    error real de conexión si la URL está mal por otro motivo.
    """
    url = (url or "").strip().strip('"').strip("'")
    partes = urlsplit(url)
    esquema = partes.scheme
    if esquema in ("postgres", "postgresql"):
        esquema = "postgresql+asyncpg"
    if esquema != "postgresql+asyncpg":
        return url
    query = []
    for clave, valor in parse_qsl(partes.query, keep_blank_values=True):
        if clave == "channel_binding":
            continue
        if clave == "sslmode":
            clave = "ssl"
        query.append((clave, valor))
    return urlunsplit((esquema, partes.netloc, partes.path, urlencode(query), partes.fragment))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ADMIN_", extra="ignore")

    app_name: str = "AgeCare Admin API"
    environment: str = "dev"  # dev | staging | prod
    database_url: str = "postgresql+asyncpg://agecare:agecare@localhost:5432/agecare_admin"

    # JWT
    jwt_secret: str = "cambia-esto-en-produccion"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_hours: int = 12

    # Login
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    allowed_email_domains: str = "wellq.co.uk,wellq.co"  # separados por coma

    # Negocio
    business_timezone: str = "America/Santiago"

    # Multi-tenant. El modelo canónico aísla los datos por tenant con seguridad a
    # nivel de fila, y la API tiene que declarar en cada transacción a quién sirve.
    # Cómo se deduce el tenant en el login es un punto abierto de la especificación
    # (sección 9.1 del modelo de datos): mientras el equipo decide si va por
    # subdominio, se usa uno fijo. Cambiarlo será tocar una sola función.
    tenant_id: str = "00000000-0000-0000-0000-000000000001"

    @field_validator("database_url")
    @classmethod
    def _normalizar_url(cls, v: str) -> str:
        return url_para_asyncpg(v)

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
