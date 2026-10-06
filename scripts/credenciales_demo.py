"""Cuentas de demostración y sus credenciales.

Las contraseñas y el secreto TOTP no se guardan en el repositorio: se leen de
variables de entorno, o del archivo .env local (que git ignora). Las usan el seed
(para crear las cuentas) y las auditorías (para iniciar sesión).

Para generar un juego nuevo de valores aleatorios:

    python -m scripts.credenciales_demo --generar

Copia la salida en tu .env y entrégala a quien deba probar por un canal seguro.

Las cuentas de administración tienen segundo factor (TOTP): el código de 6 dígitos
se obtiene en una app de autenticación configurada con DEMO_MFA_SECRET.
"""
import argparse
import os
import secrets
import sys

import pyotp
from dotenv import load_dotenv

load_dotenv()

# nombre, correo, rol, variable con la contraseña
CUENTAS = [
    ("Max K.", "admin@wellq.co.uk", "admin", "DEMO_CLAVE_ADMIN"),
    ("Sofía Rojas", "soporte@wellq.co.uk", "support", "DEMO_CLAVE_SOPORTE"),
    ("Diego Paredes", "analista@wellq.co.uk", "analyst", "DEMO_CLAVE_ANALISTA"),
    ("Carla Núñez", "editora@wellq.co.uk", "editor", "DEMO_CLAVE_EDITORA"),
    ("Ignacio Salas", "moderador@wellq.co.uk", "moderator", "DEMO_CLAVE_MODERADOR"),
]
VARIABLE_MFA = "DEMO_MFA_SECRET"
# Roles que exigen segundo factor (spec 3.1).
ROLES_CON_MFA = {"admin"}


def _leer(variable: str) -> str:
    valor = os.environ.get(variable, "").strip()
    if not valor:
        sys.exit(f"Falta la variable {variable}. Defínela en .env o en el entorno; "
                 "para generar valores nuevos: python -m scripts.credenciales_demo --generar")
    return valor


def cuenta(rol: str) -> tuple[str, str]:
    """(correo, contraseña) de la cuenta demo del rol."""
    for _, correo, r, variable in CUENTAS:
        if r == rol:
            return correo, _leer(variable)
    raise KeyError(rol)


def secreto_mfa() -> str:
    return _leer(VARIABLE_MFA)


def codigo_otp() -> str:
    """Código TOTP vigente para las cuentas con segundo factor."""
    return pyotp.TOTP(secreto_mfa()).now()


def credenciales_login(rol: str) -> dict:
    """Cuerpo de POST /auth/login para la cuenta demo del rol, con TOTP si lo exige."""
    correo, clave = cuenta(rol)
    cuerpo = {"email": correo, "password": clave}
    if rol in ROLES_CON_MFA:
        cuerpo["otp_code"] = codigo_otp()
    return cuerpo


def _clave_aleatoria(largo: int = 16) -> str:
    # Garantiza mayúscula, minúscula, dígito y símbolo; sin caracteres ambiguos.
    mayus, minus = "ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnpqrstuvwxyz"
    digitos, simbolos = "23456789", "!#%*+-=?"
    base = [secrets.choice(c) for c in (mayus, minus, digitos, simbolos)]
    todos = mayus + minus + digitos + simbolos
    base += [secrets.choice(todos) for _ in range(largo - len(base))]
    secrets.SystemRandom().shuffle(base)
    return "".join(base)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Credenciales de las cuentas demo.")
    ap.add_argument("--generar", action="store_true", help="Imprime valores nuevos para el .env.")
    if not ap.parse_args().generar:
        ap.print_help()
        sys.exit(0)
    for _, correo, _, variable in CUENTAS:
        print(f"{variable}={_clave_aleatoria()}")
    print(f"{VARIABLE_MFA}={pyotp.random_base32()}")
