"""Formato estándar de error de la consola (sección 2.4 de la especificación).

Todo error responde:
    {"error": {"code": "...", "message": "...", "details": [...] | null, "request_id": "..."}}
"""
import logging
import uuid

from fastapi import FastAPI, Request
from sqlalchemy.exc import DBAPIError
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ApiError(Exception):
    """Error de negocio con código interno estable y mensaje en español."""

    def __init__(self, status_code: int, code: str, message: str, details: list | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


# Atajos para los errores más comunes
def unauthorized(message: str = "Tu sesión de administración expiró. Vuelve a iniciar sesión.",
                 code: str = "UNAUTHORIZED") -> ApiError:
    return ApiError(401, code, message)


def forbidden(message: str = "Tu rol no tiene permisos sobre este módulo.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def not_found(message: str = "El recurso solicitado no existe.") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def invalid(code: str, message: str, details: list | None = None) -> ApiError:
    return ApiError(422, code, message, details)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # UUID completo: el modelo canónico lo guarda en audit_log.request_id (uuid).
        request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response


def _body(request: Request, code: str, message: str, details: list | None = None) -> dict:
    return {"error": {
        "code": code,
        "message": message,
        "details": details,
        "request_id": getattr(request.state, "request_id", "-"),
    }}


# ---------------------------------------------------------------------------
# Traducción de errores del esquema canónico
# ---------------------------------------------------------------------------
# El modelo de datos impone por trigger las mismas reglas que la API valida en
# Python, y lanza el código de la especificación al principio del mensaje. Sin
# traducirlo, cualquiera de esas reglas saltando en la base devolvería un 500
# genérico en vez del 409 documentado. Es el punto abierto 9.6 del modelo.
#
# Las validaciones de los routers siguen ahí: son las que dan el mensaje en
# español y el detalle por campo. Esto es la red de seguridad para lo que se
# escape, y la única defensa cuando algo escriba en la base fuera de la API.
CODIGOS_DEL_ESQUEMA: dict[str, tuple[int, str]] = {
    "LAST_ADMIN": (409, "No puedes dejar el sistema sin ninguna cuenta de administrador activa."),
    "INVALID_TRANSITION": (409, "Ese cambio de estado no está permitido desde el estado actual."),
    "TICKET_CLOSED": (409, "El ticket está cerrado y no admite nuevas respuestas."),
    "ALREADY_MODERATED": (409, "Otra persona ya moderó este elemento."),
    "VERSION_CONFLICT": (409, "Alguien modificó este registro mientras lo editabas. Vuelve a cargarlo."),
}

# Mensajes del esquema que no llevan prefijo de código, con el que les corresponde.
MENSAJES_SIN_CODIGO: list[tuple[str, int, str, str]] = [
    ("versión legal publicada es inmutable", 409, "ALREADY_PUBLISHED",
     "Una versión legal publicada no se puede modificar."),
    ("versión publicada no puede volver a borrador", 409, "ALREADY_PUBLISHED",
     "Una versión publicada no puede volver a borrador."),
    ("es inmutable: no admite", 403, "FORBIDDEN",
     "Esa tabla es de solo lectura: el registro de auditoría no se modifica."),
]

# Errores genéricos de PostgreSQL, por si ninguna regla con nombre encaja.
POR_SQLSTATE: dict[str, tuple[int, str, str]] = {
    "23505": (409, "CONFLICT", "Ya existe un registro con esos datos."),
    "23503": (422, "VALIDATION_ERROR", "Referencia a un registro que no existe."),
    "23514": (422, "VALIDATION_ERROR", "Los datos no cumplen una restricción del modelo."),
    "42501": (403, "FORBIDDEN", "No tienes permiso sobre esos datos."),
    "40001": (409, "CONFLICT", "Conflicto de concurrencia. Vuelve a intentarlo."),
}


def traducir_error_de_bd(exc: Exception) -> ApiError | None:
    """Convierte una excepción de PostgreSQL en el error documentado, si lo hay.

    Devuelve None cuando no reconoce el error, para que siga su camino y acabe
    como INTERNAL_ERROR: es preferible un 500 honesto a un 409 inventado.
    """
    # Hay tres capas: la excepción de SQLAlchemy, el envoltorio DBAPI del dialecto
    # asyncpg, y dentro de él la excepción real de asyncpg. El texto limpio del
    # RAISE EXCEPTION solo está en la última; el del envoltorio viene precedido del
    # nombre de la clase, que rompería cualquier intento de leer el código.
    orig = getattr(exc, "orig", exc)
    raiz = getattr(orig, "__cause__", None) or orig
    mensaje = str(getattr(raiz, "message", None) or raiz)
    sqlstate = (getattr(raiz, "sqlstate", None) or getattr(orig, "sqlstate", None)
                or getattr(orig, "pgcode", None))

    codigo = mensaje.split(":", 1)[0].strip()
    if codigo in CODIGOS_DEL_ESQUEMA:
        estado, texto = CODIGOS_DEL_ESQUEMA[codigo]
        return ApiError(estado, codigo, texto)

    for fragmento, estado, cod, texto in MENSAJES_SIN_CODIGO:
        if fragmento in mensaje:
            return ApiError(estado, cod, texto)

    if sqlstate in POR_SQLSTATE:
        estado, cod, texto = POR_SQLSTATE[sqlstate]
        return ApiError(estado, cod, texto)
    return None


_log = logging.getLogger("agecare.api")


def _registrar(request: Request, exc: Exception) -> None:
    """Deja la traza completa en los logs (Vercel: Runtime Logs) con su request_id.

    El mensaje al usuario dice "revisa el request_id en los logs"; sin esto, en los
    logs no había nada que revisar.
    """
    _log.error("INTERNAL_ERROR request_id=%s %s %s",
               getattr(request.state, "request_id", "-"), request.method, request.url.path,
               exc_info=(type(exc), exc, exc.__traceback__))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code,
                            content=_body(request, exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "issue": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=_body(
            request, "VALIDATION_ERROR",
            "Hay datos inválidos en la solicitud. Revisa los campos marcados.", details))

    @app.exception_handler(DBAPIError)
    async def db_error_handler(request: Request, exc: DBAPIError):
        traducido = traducir_error_de_bd(exc)
        if traducido is None:
            _registrar(request, exc)
            return JSONResponse(status_code=500, content=_body(
                request, "INTERNAL_ERROR", "Error interno. Revisa el request_id en los logs."))
        return JSONResponse(status_code=traducido.status_code, content=_body(
            request, traducido.code, traducido.message, traducido.details))

    @app.exception_handler(Exception)
    async def internal_handler(request: Request, exc: Exception):
        _registrar(request, exc)
        return JSONResponse(status_code=500, content=_body(
            request, "INTERNAL_ERROR", "Error interno. Revisa el request_id en los logs."))
