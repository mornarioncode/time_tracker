"""Repositorios abstractos: contrato entre `core` y `storage`.

`core` define *qué* se persiste; `storage` decide *cómo*. La atomicidad se
expresa con `transaction()`: el servicio envuelve las escrituras múltiples en
un único contexto (p. ej. cerrar la entry abierta + abrir la nueva).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from datetime import datetime

from core.models import Session, Task, TimeEntry


class Repository(ABC):
    """Contrato común: contexto de transacción reutilizable por el servicio."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]:
        """Contexto que hace atómicas las escrituras realizadas dentro de él."""


class SessionRepository(Repository):
    @abstractmethod
    def add(self, session: Session) -> Session:
        """Persiste la sesión y devuelve una copia con el `id` asignado."""

    @abstractmethod
    def get(self, session_id: int) -> Session:
        """Devuelve la sesión o lanza `SessionNotFoundError`."""

    @abstractmethod
    def list_all(self) -> list[Session]:
        """Todas las sesiones, de la más reciente a la más antigua."""

    @abstractmethod
    def set_ended_at(self, session_id: int, ended_at: datetime) -> Session:
        """Marca la sesión como cerrada en `ended_at` y devuelve la sesión."""

    @abstractmethod
    def delete(self, session_id: int) -> None:
        """Borra la sesión (tareas e intervalos en cascada)."""


class TaskRepository(Repository):
    @abstractmethod
    def add(self, task: Task) -> Task:
        """Persiste la tarea en el CATÁLOGO GLOBAL; `DuplicateTaskError` si el
        nombre ya existe en toda la BD (UNIQUE global tras strip)."""

    @abstractmethod
    def get(self, task_id: int) -> Task:
        """Devuelve la tarea o lanza `TaskNotFoundError`."""

    @abstractmethod
    def list_all(self) -> list[Task]:
        """Catálogo global de tareas, por orden de creación."""


class EntryRepository(Repository):
    @abstractmethod
    def add(self, entry: TimeEntry) -> TimeEntry:
        """Persiste el intervalo (task_id + session_id); lanza
        `MultipleOpenEntriesError` si ya hay otro abierto."""

    @abstractmethod
    def get(self, entry_id: int) -> TimeEntry:
        """Devuelve el intervalo o lanza `EntryNotFoundError`."""

    @abstractmethod
    def list_by_session(self, session_id: int) -> list[TimeEntry]:
        """Intervalos anclados a la sesión (`session_id`), ordenados por inicio."""

    @abstractmethod
    def get_open_entry(self) -> TimeEntry | None:
        """Intervalo en curso en toda la BD, o None. Lanza `MultipleOpenEntriesError` si hay >1."""

    @abstractmethod
    def close_open_entry(self, ended_at: datetime) -> TimeEntry | None:
        """Cierra el intervalo abierto (si lo hay) con `ended_at` y lo devuelve; None si no había."""

    @abstractmethod
    def close_entry(self, entry_id: int, ended_at: datetime) -> TimeEntry:
        """Cierra un intervalo concreto; valida `ended_at >= started_at`."""
