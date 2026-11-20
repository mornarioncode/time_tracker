"""Mensajes de error limpios para la UI: nunca trazas ni SQL (puro, testeable).

La interfaz traduce CUALQUIER excepción a un mensaje corto y accionable:
`core.exceptions` ya define sus mensajes en español para la persona usuaria.
"""

from __future__ import annotations

from core.exceptions import StorageError, TimeTrackerError


def mensaje_usuario(exc: BaseException) -> str:
    """Traduce una excepción a un mensaje comprensible para la UI.

    - Errores de dominio (`ValidationError`, `DuplicateTaskError`,
      `SessionClosedError`, `SessionNotFoundError`, ...): sus mensajes ya van
      en español y son accionables → se muestran tal cual.
    - `StorageError`: el mensaje interno contiene SQL → se sustituye por uno
      genérico (el detalle queda para la consola del desarrollador).
    - Cualquier otra excepción: mensaje genérico. Jamás se filtra una traza.
    """
    if isinstance(exc, StorageError):
        return "No se pudieron guardar los datos. Inténtalo de nuevo."
    if isinstance(exc, TimeTrackerError):
        mensaje = str(exc).strip()
        return mensaje if mensaje else "La operación no se pudo completar."
    return "Ha ocurrido un error inesperado. Inténtalo de nuevo."
