"""Entidades de dominio: Session, Task y TimeEntry.

Todos los instantes de tiempo son *aware* y están en UTC. Las duraciones se
calculan como enteros de segundos; el formateo (1 h 23 min) es responsabilidad
de la UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.exceptions import ValidationError


def utc_now() -> datetime:
    """Momento actual en UTC (tz-aware)."""
    return datetime.now(timezone.utc)


def _require_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValidationError(f"{field} debe ser un datetime con zona horaria (UTC)")


def _require_non_empty(name: str, field: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValidationError(f"{field} no puede estar vacío")
    return name.strip()


@dataclass(frozen=True, slots=True)
class Session:
    """Grupo de trabajo (p. ej. 'Semana 47 — App web')."""

    name: str
    created_at: datetime
    id: int | None = None
    ended_at: datetime | None = None  # None = sesión abierta

    def __post_init__(self) -> None:
        # Normaliza el nombre en el propio modelo (frozen + slots → object.__setattr__)
        object.__setattr__(
            self, "name", _require_non_empty(self.name, "El nombre de la sesión")
        )
        _require_aware(self.created_at, "created_at")
        if self.ended_at is not None:
            _require_aware(self.ended_at, "ended_at")
            if self.ended_at < self.created_at:
                raise ValidationError("ended_at no puede ser anterior a created_at")

    @property
    def is_open(self) -> bool:
        return self.ended_at is None


@dataclass(frozen=True, slots=True)
class Task:
    """Tarea GLOBAL del catálogo (§5.1/§5.3.3): solo nombre y creación.

    Única en toda la BD (el UNIQUE de `tasks.name` aplica tras el strip del
    modelo; homónimos → DuplicateTaskError). No pertenece a ninguna sesión y
    sobrevive al borrado de sesiones (las entries sí caen en cascada).
    """

    name: str
    created_at: datetime
    id: int | None = None

    def __post_init__(self) -> None:
        # Normaliza el nombre en el propio modelo (frozen + slots → object.__setattr__)
        object.__setattr__(
            self, "name", _require_non_empty(self.name, "El nombre de la tarea")
        )
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class TimeEntry:
    """Intervalo: ancla "qué tarea" (task_id) + "qué sesión/jornada" (session_id).

    started_at / ended_at (None = en curso); todo en UTC aware.
    """

    task_id: int
    session_id: int
    started_at: datetime
    id: int | None = None
    ended_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.task_id is None:
            raise ValidationError("task_id es obligatorio")
        if self.session_id is None:
            raise ValidationError("session_id es obligatorio")
        _require_aware(self.started_at, "started_at")
        if self.ended_at is not None:
            _require_aware(self.ended_at, "ended_at")
            if self.ended_at < self.started_at:
                raise ValidationError("ended_at no puede ser anterior a started_at")

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def duration_seconds(self) -> int | None:
        """Duración en segundos; None si el intervalo sigue en curso."""
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds())
