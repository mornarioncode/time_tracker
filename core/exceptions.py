"""Errores de dominio del time tracker."""

from __future__ import annotations


class TimeTrackerError(Exception):
    """Base de todos los errores de dominio."""


class ValidationError(TimeTrackerError):
    """Dato inválido: nombre vacío, fechas inconsistentes, etc."""


class SessionNotFoundError(TimeTrackerError):
    """No existe la sesión indicada."""


class TaskNotFoundError(TimeTrackerError):
    """No existe la tarea indicada."""


class EntryNotFoundError(TimeTrackerError):
    """No existe el intervalo (TimeEntry) indicado."""


class SessionClosedError(TimeTrackerError):
    """La sesión ya está cerrada y no admite más operaciones de escritura."""


class DuplicateTaskError(TimeTrackerError):
    """Ya existe una tarea con ese nombre dentro de la sesión."""


class MultipleOpenEntriesError(TimeTrackerError):
    """Hay más de un intervalo abierto: violación de integridad de datos."""


class StorageError(TimeTrackerError):
    """Error de persistencia: la BD no se pudo leer/escribir."""
