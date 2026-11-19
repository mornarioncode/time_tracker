"""Fixtures compartidas de la suite de Fase 1.

Todas las pruebas corren contra un SQLite real en `tmp_path/*.db` (sin mocks)
y usan un reloj inyectado (`FakeClock`) para controlar duraciones exactas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.services import TimeTrackerService
from storage.db import Database
from storage.sqlite_repository import (
    SqliteEntryRepository,
    SqliteSessionRepository,
    SqliteTaskRepository,
)

UTC = timezone.utc
HORA_BASE = datetime(2026, 11, 18, 9, 0, 0, tzinfo=UTC)


class FakeClock:
    """Reloj controlable: devuelve un instante fijo que el test avanza o retrocede."""

    def __init__(self, start: datetime = HORA_BASE) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock requiere un datetime aware")
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def set(self, instant: datetime) -> datetime:
        if instant.tzinfo is None:
            raise ValueError("FakeClock requiere un datetime aware")
        self._now = instant
        return self._now

    def advance(self, seconds: float) -> datetime:
        self._now = self._now + timedelta(seconds=seconds)
        return self._now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def db_path(tmp_path):
    """Ruta de BD temporal: siempre dentro de tmp_path (nunca el home del usuario)."""
    return tmp_path / "time_tracker.db"


@pytest.fixture
def db(db_path):
    """`Database` real inicializada con el esquema v2 (tareas globales)."""
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def repos(db) -> SimpleNamespace:
    """Repositorios SQLite reales compartiendo la misma `Database`."""
    return SimpleNamespace(
        sessions=SqliteSessionRepository(db),
        tasks=SqliteTaskRepository(db),
        entries=SqliteEntryRepository(db),
    )


@pytest.fixture
def service(db, clock) -> TimeTrackerService:
    """Servicio de dominio con reloj controlado sobre la BD temporal."""
    return TimeTrackerService(
        sessions=SqliteSessionRepository(db),
        tasks=SqliteTaskRepository(db),
        entries=SqliteEntryRepository(db),
        now=clock,
    )


@pytest.fixture
def sesion(service) -> "object":
    """Sesión abierta creada y dejada como sesión actual."""
    return service.crear_sesion("Sesión de prueba")


@pytest.fixture
def tarea(service, sesion):
    """Tarea del catálogo global fixture (sin intervalos)."""
    return service.añadir_tarea("Tarea 1")
