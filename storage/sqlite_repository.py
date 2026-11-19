"""Implementación SQLite de los repositorios de `core.repository`.

Mapeo fila ↔ dataclass, traducción de errores de SQLite a errores de dominio
(p. ej. UNIQUE(name) global del catálogo → DuplicateTaskError) y validación de
la regla "como máximo un intervalo abierto".
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime

from core.exceptions import (
    DuplicateTaskError,
    EntryNotFoundError,
    MultipleOpenEntriesError,
    SessionNotFoundError,
    StorageError,
    TaskNotFoundError,
    ValidationError,
)
from core.models import Session, Task, TimeEntry
from core.repository import EntryRepository, SessionRepository, TaskRepository
from storage.db import Database, from_db_timestamp, to_db_timestamp


def _fila_a_sesion(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        name=row["name"],
        created_at=from_db_timestamp(row["created_at"]),
        ended_at=from_db_timestamp(row["ended_at"]) if row["ended_at"] else None,
    )


def _fila_a_tarea(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        name=row["name"],
        created_at=from_db_timestamp(row["created_at"]),
    )


def _fila_a_entry(row: sqlite3.Row) -> TimeEntry:
    return TimeEntry(
        id=row["id"],
        task_id=row["task_id"],
        session_id=row["session_id"],
        started_at=from_db_timestamp(row["started_at"]),
        ended_at=from_db_timestamp(row["ended_at"]) if row["ended_at"] else None,
    )


def _es_violacion_uniqueness(exc: StorageError) -> bool:
    """¿La causa subyacente es una violación de UNIQUE y no otra integridad?

    `sqlite3.IntegrityError` abarca UNIQUE, FOREIGN KEY, NOT NULL, CHECK, etc.,
    así que comprobar solo el tipo de error convertía una FK rota en un falso
    `DuplicateTaskError`. Se distingue por `sqlite_errorcode` (Python >= 3.11):
    solo `SQLITE_CONSTRAINT_UNIQUE` cuenta como duplicado; el resto (p. ej.
    `SQLITE_CONSTRAINT_FOREIGNKEY`) debe re-lanzarse como `StorageError`.

    Si el código no estuviera disponible se cae al mensaje, comprobando primero
    FK que UNIQUE (ante una sentencia que pudiera violar varias restricciones,
    prevalece la lectura más restrictiva); ante la duda NO se clasifica como
    duplicado.
    """
    causa = exc.__cause__
    if not isinstance(causa, sqlite3.IntegrityError):
        return False
    codigo = getattr(causa, "sqlite_errorcode", None)
    if codigo is not None:
        return codigo == getattr(sqlite3, "SQLITE_CONSTRAINT_UNIQUE", 2067)
    texto = str(causa).lower()
    if "foreign key constraint failed" in texto:
        return False
    return "unique constraint failed" in texto


class _SqliteRepository:
    """Base común: comparten `Database`, por lo que sus transacciones son globales."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def db(self) -> Database:
        return self._db

    def transaction(self):
        return self._db.transaction()


class SqliteSessionRepository(_SqliteRepository, SessionRepository):
    def add(self, session: Session) -> Session:
        cur = self._db.execute(
            "INSERT INTO sessions (name, created_at, ended_at) VALUES (?, ?, ?)",
            (
                session.name,
                to_db_timestamp(session.created_at),
                to_db_timestamp(session.ended_at) if session.ended_at else None,
            ),
        )
        return replace(session, id=cur.lastrowid)

    def get(self, session_id: int) -> Session:
        row = self._db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise SessionNotFoundError(f"No existe la sesión con id={session_id}")
        return _fila_a_sesion(row)

    def list_all(self) -> list[Session]:
        rows = self._db.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [_fila_a_sesion(row) for row in rows]

    def set_ended_at(self, session_id: int, ended_at: datetime) -> Session:
        session = self.get(session_id)  # valida existencia + created_at <= ended_at
        cerrada = replace(session, ended_at=ended_at)
        self._db.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (to_db_timestamp(ended_at), session_id),
        )
        return cerrada

    def delete(self, session_id: int) -> None:
        self.get(session_id)  # valida existencia
        # tasks y time_entries caen en cascada (FK ON DELETE CASCADE)
        self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


class SqliteTaskRepository(_SqliteRepository, TaskRepository):
    def add(self, task: Task) -> Task:
        try:
            cur = self._db.execute(
                "INSERT INTO tasks (name, created_at) VALUES (?, ?)",
                (task.name, to_db_timestamp(task.created_at)),
            )
        except StorageError as exc:
            # UNIQUE(name) global (v2): homónimo en el catálogo → duplicado
            if _es_violacion_uniqueness(exc):
                raise DuplicateTaskError(
                    f"Ya existe la tarea '{task.name}' en el catálogo"
                ) from exc
            raise
        return replace(task, id=cur.lastrowid)

    def get(self, task_id: int) -> Task:
        row = self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFoundError(f"No existe la tarea con id={task_id}")
        return _fila_a_tarea(row)

    def list_all(self) -> list[Task]:
        rows = self._db.execute(
            "SELECT * FROM tasks ORDER BY created_at, id"
        ).fetchall()
        return [_fila_a_tarea(row) for row in rows]


class SqliteEntryRepository(_SqliteRepository, EntryRepository):
    def add(self, entry: TimeEntry) -> TimeEntry:
        if entry.is_open:
            actual = self.get_open_entry()
            if actual is not None:
                raise MultipleOpenEntriesError(
                    f"Ya hay un intervalo abierto (id={actual.id}); no se puede abrir otro"
                )
        cur = self._db.execute(
            "INSERT INTO time_entries (task_id, session_id, started_at, ended_at)"
            " VALUES (?, ?, ?, ?)",
            (
                entry.task_id,
                entry.session_id,
                to_db_timestamp(entry.started_at),
                to_db_timestamp(entry.ended_at) if entry.ended_at else None,
            ),
        )
        return replace(entry, id=cur.lastrowid)

    def get(self, entry_id: int) -> TimeEntry:
        row = self._db.execute(
            "SELECT * FROM time_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise EntryNotFoundError(f"No existe el intervalo con id={entry_id}")
        return _fila_a_entry(row)

    def list_by_session(self, session_id: int) -> list[TimeEntry]:
        # Anclado directo por time_entries.session_id (v2): sin JOIN a tasks
        rows = self._db.execute(
            "SELECT * FROM time_entries WHERE session_id = ?"
            " ORDER BY started_at, id",
            (session_id,),
        ).fetchall()
        return [_fila_a_entry(row) for row in rows]

    def get_open_entry(self) -> TimeEntry | None:
        rows = self._db.execute(
            "SELECT * FROM time_entries WHERE ended_at IS NULL ORDER BY started_at, id"
        ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            ids = [row["id"] for row in rows]
            raise MultipleOpenEntriesError(
                f"Violación de integridad: hay {len(rows)} intervalos abiertos {ids}"
            )
        return _fila_a_entry(rows[0])

    def close_entry(self, entry_id: int, ended_at: datetime) -> TimeEntry:
        entry = self.get(entry_id)
        if not entry.is_open:
            raise ValidationError(f"El intervalo {entry_id} ya está cerrado")
        cerrada = replace(entry, ended_at=ended_at)  # valida ended_at >= started_at
        self._db.execute(
            "UPDATE time_entries SET ended_at = ? WHERE id = ?",
            (to_db_timestamp(ended_at), entry_id),
        )
        return cerrada

    def close_open_entry(self, ended_at: datetime) -> TimeEntry | None:
        entry = self.get_open_entry()
        if entry is None:
            return None
        return self.close_entry(entry.id, ended_at)
