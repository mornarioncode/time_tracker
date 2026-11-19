"""Conexión SQLite, PRAGMAs, esquema v2 y migraciones por `user_version`.

- Conexión única por proceso con `check_same_thread=False` y un `RLock` que
  serializa accesos (la UI podrá usarla desde varios hilos sin "database is
  locked").
- Transacciones explícitas (`BEGIN`/`COMMIT`, `SAVEPOINT` si se anidan).
- Esquema: migraciones numeradas aplicadas con `PRAGMA user_version`.
  v1 (§5.2 histórico: `tasks.session_id`, `UNIQUE(session_id, name)`) →
  **v2** (Fase 1b): tareas globales (`tasks.name UNIQUE`) y
  `time_entries.session_id` con FK `ON DELETE CASCADE` + `idx_entries_session`.
  BDs nuevas recorren 0→1→2; las existentes en v1 aplican solo el paso 2.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.exceptions import StorageError, ValidationError

DEFAULT_FOLDER = ".time_tracker"
DEFAULT_FILENAME = "time_tracker.db"


def default_db_path() -> Path:
    """Ruta por defecto: ~/.time_tracker/time_tracker.db (funciona en Windows/POSIX)."""
    return Path.home() / DEFAULT_FOLDER / DEFAULT_FILENAME


# --------------------------------------------------------------- timestamps

def to_db_timestamp(value: datetime) -> str:
    """datetime aware → texto ISO-8601 UTC terminado en 'Z' (2026-11-18T09:12:00Z)."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValidationError("Se esperaba un datetime con zona horaria (UTC)")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def from_db_timestamp(text: str) -> datetime:
    """Texto ISO-8601 UTC → datetime aware en UTC."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# --------------------------------------------------------------- migraciones

# v1 — esquema histórico (Fase 1). Solo como paso intermedio de la migración
# 1→2 y para BDs dev pre-existentes: no se usa como esquema final.
_SCHEMA_V1: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        created_at  TEXT    NOT NULL,
        ended_at    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        name        TEXT    NOT NULL,
        created_at  TEXT    NOT NULL,
        UNIQUE (session_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS time_entries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        started_at  TEXT    NOT NULL,
        ended_at    TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_entries_task ON time_entries(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_entries_started ON time_entries(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id)",
)

# v1 → v2 (Fase 1b). Best-effort pre-lanzamiento (§5.2): rebuild de `tasks` y
# `time_entries` dentro de UNA transacción (DDL transaccional en SQLite → o
# migra completo o la BD queda intacta en v1 con user_version=1).
#
# Semántica:
#   1) Se renombran las tablas viejas PRIMERO (y no se hace `DROP` de `tasks`
#      con hijos apuntando: evitamos el `DELETE FROM` implícito del DROP con
#      foreign_keys=ON y el re-punteo de REFERENCES que haría RENAME).
#   2) Se crean las tablas v2 y se copian los datos:
#      - tasks: homónimos (mismo nombre en varias sesiones, permitido en v1)
#        se FUSIONAN conservando el id más antiguo (MIN(id)) y la creación más
#        antigua → cumple el UNIQUE(name) global. Best-effort: gana el más
#        antiguo; el nombre no se toca (ya venía "stripado" de fábrica).
#      - time_entries: `session_id` se deriva de la task vieja
#        (`tasks_v1.session_id`) y `task_id` se REMAPEA al superviviente. Las
#        entries con task o sesión huérfana (no deberían existir con FKs ON)
#        se descartan: JOIN purga huérfanos (best-effort, documentado).
#   3) Se dropean las tablas viejas (ya sin referencias) y se crean los
#      índices de v2 (incluido idx_entries_session; idx_tasks_session muere
#      con tasks_v1).
_MIGRATION_V2: tuple[str, ...] = (
    "ALTER TABLE time_entries RENAME TO time_entries_v1",
    "ALTER TABLE tasks RENAME TO tasks_v1",
    """
    CREATE TABLE tasks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL UNIQUE,
        created_at  TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE time_entries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        started_at  TEXT    NOT NULL,
        ended_at    TEXT
    )
    """,
    # fusión de homónimos: conserva id/creación más antiguos por nombre
    """
    INSERT INTO tasks (id, name, created_at)
    SELECT MIN(id), name, MIN(created_at)
      FROM tasks_v1
     GROUP BY name
    """,
    # entries: session_id desde la task vieja; task_id remapeado al superviviente
    """
    INSERT INTO time_entries (id, task_id, session_id, started_at, ended_at)
    SELECT e.id,
           (SELECT MIN(x.id) FROM tasks_v1 x WHERE x.name = t.name),
           t.session_id,
           e.started_at,
           e.ended_at
      FROM time_entries_v1 e
      JOIN tasks_v1 t ON t.id = e.task_id
      JOIN sessions s ON s.id = t.session_id
    """,
    "DROP TABLE time_entries_v1",
    "DROP TABLE tasks_v1",
    "CREATE INDEX IF NOT EXISTS idx_entries_task ON time_entries(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_entries_started ON time_entries(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_entries_session ON time_entries(session_id)",
)

MIGRATIONS: dict[int, tuple[str, ...]] = {1: _SCHEMA_V1, 2: _MIGRATION_V2}


# ------------------------------------------------------------------ database

class Database:
    """Conexión SQLite única con lock, transacciones y migraciones."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else default_db_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(
                str(self._path), check_same_thread=False, isolation_level=None
            )
        except sqlite3.Error as exc:
            raise StorageError(f"No se pudo abrir la BD {self._path}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._tx_depth = 0
        self.execute("PRAGMA foreign_keys = ON")
        self.execute("PRAGMA journal_mode = WAL")
        self.execute("PRAGMA synchronous = NORMAL")

    @property
    def path(self) -> Path:
        return self._path

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Ejecuta SQL serializando con el lock y traduciendo errores a StorageError."""
        with self._lock:
            try:
                return self._conn.execute(sql, params)
            except sqlite3.Error as exc:
                raise StorageError(f"Error de SQLite al ejecutar '{sql.strip()}': {exc}") from exc

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Transacción atómica. Anidada usa SAVEPOINT para no romper la externa."""
        with self._lock:
            if self._tx_depth == 0:
                self.execute("BEGIN")
                self._tx_depth = 1
                try:
                    yield
                except BaseException:
                    self.execute("ROLLBACK")
                    raise
                else:
                    self.execute("COMMIT")
                finally:
                    self._tx_depth = 0
            else:
                name = f"sp_{self._tx_depth}"
                self.execute(f"SAVEPOINT {name}")
                self._tx_depth += 1
                try:
                    yield
                except BaseException:
                    self.execute(f"ROLLBACK TO SAVEPOINT {name}")
                    self.execute(f"RELEASE SAVEPOINT {name}")
                    raise
                else:
                    self.execute(f"RELEASE SAVEPOINT {name}")
                finally:
                    self._tx_depth -= 1

    def initialize(self) -> int:
        """Aplica las migraciones pendientes; devuelve la versión final de `user_version`."""
        with self._lock:
            current = int(self.execute("PRAGMA user_version").fetchone()[0])
            for version in sorted(MIGRATIONS):
                if version <= current:
                    continue
                with self.transaction():
                    for statement in MIGRATIONS[version]:
                        self.execute(statement)
                    self.execute(f"PRAGMA user_version = {version}")
            return int(self.execute("PRAGMA user_version").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()
