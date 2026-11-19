"""Composición de arranque: une `core` + `storage` (punto de entrada para UI/smoke)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from core.services import TimeTrackerService
from storage.db import Database
from storage.sqlite_repository import (
    SqliteEntryRepository,
    SqliteSessionRepository,
    SqliteTaskRepository,
)


def create_service(
    db_path: str | Path | None = None,
    *,
    now: Callable[[], datetime] | None = None,
) -> tuple[Database, TimeTrackerService]:
    """Abre (o crea) la BD, aplica el esquema (migra v1→v2, §5.2) y devuelve
    `(db, servicio)`.

    `now` permite inyectar un reloj (tests / smoke con tiempos controlados).
    """
    db = Database(db_path)
    db.initialize()
    kwargs = {} if now is None else {"now": now}
    service = TimeTrackerService(
        sessions=SqliteSessionRepository(db),
        tasks=SqliteTaskRepository(db),
        entries=SqliteEntryRepository(db),
        **kwargs,
    )
    return db, service
