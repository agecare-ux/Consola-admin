"""Compatibilidad temporal mientras dura la fase 3 de la migración.

El modelo canónico llama `role_code` a lo que el prototipo llamaba `role`. Los
schemas de Pydantic (AdminOut, AdminUserOut) y los routers que todavía no se migran
leen `admin.role`. En vez de tocar todo a la vez, esta propiedad de solo lectura
traduce el nombre viejo al nuevo.

No se edita app/models_canonico.py porque es un archivo generado: la próxima vez
que se regenere desde el DDL, el cambio se perdería.

Este archivo se elimina al cerrar la fase 3. Para comprobar que nada lo necesita:
borrar el import en app/deps.py y correr pytest y las dos auditorías.
"""
from app.models_canonico import AdminUser


def _role(self: AdminUser) -> str:
    return self.role_code


# Solo lectura a propósito: escribir `admin.role = ...` fallará, y así cualquier
# código que aún escriba con el nombre viejo se detecta en vez de perder el dato.
AdminUser.role = property(_role)
