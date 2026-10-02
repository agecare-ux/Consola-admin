"""Configuración de la API de administración de AgeCare."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def allowed_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
