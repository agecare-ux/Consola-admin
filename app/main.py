"""AgeCare — API de la Consola de Administración (FastAPI + PostgreSQL)."""
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse

from app.config import get_settings
from app.errors import RequestIdMiddleware, register_error_handlers
from app.routers import (auth, content, marketplace, metrics_commercial, metrics_features,
                         metrics_roles, moderation, ops, support)
from app.routers import system as system_router

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="AgeCare Admin API",
    version="1.0.0",
    description="Backend de la Consola de Administración de AgeCare · Wellq Co",
    docs_url="/api/v1/admin/docs",
    openapi_url="/api/v1/admin/openapi.json",
)
app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

api = APIRouter(prefix="/api/v1/admin")
api.include_router(auth.router)
api.include_router(metrics_commercial.router)
api.include_router(ops.router)
api.include_router(metrics_roles.router)
api.include_router(support.router)
api.include_router(metrics_features.router)
api.include_router(content.router)
api.include_router(marketplace.router)
api.include_router(moderation.router)
api.include_router(system_router.router)
app.include_router(api)


@app.get("/health", tags=["Salud"])
async def health():
    return {"status": "ok", "service": get_settings().app_name}


@app.get("/", include_in_schema=False)
@app.get("/console", include_in_schema=False)
async def console():
    """Sirve la consola de administración desde el mismo origen que la API.

    Al compartir origen con /api/v1/admin, el navegador no aplica restricciones
    CORS y no hace falta configurar orígenes permitidos.
    """
    return FileResponse(STATIC_DIR / "console.html", media_type="text/html")
