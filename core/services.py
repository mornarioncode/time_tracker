"""Casos de uso del time tracker: `TimeTrackerService`.

Toda escritura a BD pasa por aquí. El servicio no conoce SQLite: depende de
los repositorios abstractos de `core.repository` y usa `transaction()` para
garantizar atomicidad (p. ej. cerrar la entry abierta + abrir la nueva).
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from core.exceptions import SessionClosedError, SessionNotFoundError, ValidationError
from core.models import Session, Task, TimeEntry, utc_now
from core.repository import EntryRepository, SessionRepository, TaskRepository


def _nombre_no_vacio(nombre: str, contexto: str) -> str:
    if not isinstance(nombre, str) or not nombre.strip():
        raise ValidationError(f"El nombre {contexto} no puede estar vacío")
    return nombre.strip()


class TimeTrackerService:
    """Operaciones de caso de uso sobre sesiones, tareas e intervalos."""

    def __init__(
        self,
        sessions: SessionRepository,
        tasks: TaskRepository,
        entries: EntryRepository,
        *,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._sessions = sessions
        self._tasks = tasks
        self._entries = entries
        self._now = now
        self._sesion_actual_id: int | None = None

    # ------------------------------------------------------------------ sesiones

    @property
    def sesion_actual(self) -> Session | None:
        """Sesión seleccionada (None si no hay o fue eliminada)."""
        if self._sesion_actual_id is None:
            return None
        try:
            return self._sessions.get(self._sesion_actual_id)
        except SessionNotFoundError:
            self._sesion_actual_id = None
            return None

    def crear_sesion(self, name: str) -> Session:
        """Crea una sesión y la deja como sesión actual.

        Regla §5.3 (decisión del usuario): solo puede haber UNA sesión de
        trabajo abierta a la vez. Si había otra sesión abierta, se cierra
        automáticamente (entry global en curso + `ended_at` de la sesión
        anterior) con el reloj inyectado, dentro de la MISMA transacción en la
        que se inserta la nueva sesión (atómico: o se cierra la anterior y se
        crea la nueva, o no cambia nada).

        El nombre se valida ANTES de cerrar nada: una creación inválida no
        debe cerrar la sesión abierta anterior.
        """
        nombre = _nombre_no_vacio(name, "de la sesión")
        now = self._now()
        with self._sessions.transaction():
            self._cerrar_sesiones_abiertas(now)
            session = self._sessions.add(Session(name=nombre, created_at=now))
        self._sesion_actual_id = session.id
        return session

    def seleccionar_sesion(self, session_id: int) -> Session:
        """Selecciona una sesión existente (abierta o cerrada) como actual.

        Decisión §5.3.4 (sesiones cerradas = historial de solo lectura):
        `seleccionar_sesion` NO lanza aunque la sesión esté cerrada, porque hay
        que poder verla (listar_intervalos/listar_tareas siguen funcionando).
        El `SessionClosedError` lo lanzan las OPERACIONES DE ESCRITURA
        posteriores: `iniciar_tarea` (añadirle intervalos) y `cerrar_sesion`.
        Solo cambia la selección: NO cierra ni reabre nada (los cierres
        implícitos de la regla de sesión única viven únicamente en
        `crear_sesion`; reabrir una sesión cerrada queda fuera de Fase 1b).
        """
        session = self._sessions.get(session_id)
        self._sesion_actual_id = session.id
        return session

    def listar_sesiones(self) -> list[Session]:
        return self._sessions.list_all()

    def cerrar_sesion(self, session_id: int | None = None) -> Session:
        """Termina la sesión: cierra el intervalo abierto (si lo hay) y marca
        `ended_at`. Ambas escrituras ocurren en una única transacción.
        Sesión ya cerrada → SessionClosedError (§5.3.4: no se reabre)."""
        session = self._sesion_o_actual(session_id)
        if not session.is_open:
            raise SessionClosedError(f"La sesión '{session.name}' ya está cerrada")
        now = self._now()
        with self._sessions.transaction():
            self._entries.close_open_entry(now)
            return self._sessions.set_ended_at(session.id, now)

    def eliminar_sesion(self, session_id: int) -> None:
        """Borra la sesión con sus INTERVALOS (cascada FK en time_entries).

        Las tareas del catálogo GLOBAL no se borran: sobreviven al catálogo
        (§5.2 regla 3); quedan sin entries de esta sesión.
        """
        self._sessions.get(session_id)  # valida que exista
        self._sessions.delete(session_id)
        if self._sesion_actual_id == session_id:
            self._sesion_actual_id = None

    # ------------------------------------------------------------------- tareas

    def añadir_tarea(self, name: str) -> Task:
        """Crea una tarea en el CATÁLOGO GLOBAL (§5.3.3): no pertenece a
        ninguna sesión y se reutiliza en todas.

        NO requiere sesión seleccionada y NO lanza SessionClosedError por
        sesión cerrada: crear en el catálogo no es "añadir una entrada a una
        sesión" (eso sigue prohibido en sesiones cerradas — §5.3.4 — y aquí no
        aplica). Valida nombre no vacío (tras strip); homónimo en el catálogo
        → DuplicateTaskError (UNIQUE global).
        """
        nombre = _nombre_no_vacio(name, "de la tarea")
        return self._tasks.add(Task(name=nombre, created_at=self._now()))

    def listar_tareas(self) -> list[Task]:
        """Catálogo GLOBAL de tareas (independiente de la sesión seleccionada)."""
        return self._tasks.list_all()

    # --------------------------------------------------------------- intervalos

    def iniciar_tarea(self, task_id: int) -> TimeEntry:
        """Inicia (o cambia a) la tarea `task_id` en la sesión SELECCIONADA.

        §5.3.3: la entry nueva se ancla a `task_id` (catálogo global) +
        `session_id` de la sesión actualmente seleccionada, que debe estar
        ABIERTA → SessionClosedError si es cerrada (§5.3.4: las sesiones
        cerradas no admiten intervalos) y ValidationError si no hay sesión.
        No cierra sesiones implícitamente (el cierre automático vive solo en
        `crear_sesion`).

        Regla §5.3.1: si la tarea ya está corriendo, no-op (devuelve la entry
        existente, sin micro-intervalos). Regla de integridad: como máximo UN
        intervalo abierto en toda la BD; cambiar de tarea cierra el anterior y
        abre la nueva en la MISMA transacción.
        """
        task = self._tasks.get(task_id)
        session = self._sesion_o_actual(None)  # sesión seleccionada (no la de la tarea)
        if not session.is_open:
            raise SessionClosedError(
                f"No se puede iniciar en la sesión cerrada '{session.name}'"
            )
        now = self._now()
        with self._entries.transaction():
            abierta = self._entries.get_open_entry()
            if abierta is not None:
                if abierta.task_id == task.id:
                    return abierta  # ya estaba corriendo: no reabrir
                self._entries.close_open_entry(now)  # valida now >= started_at
            return self._entries.add(
                TimeEntry(task_id=task.id, session_id=session.id, started_at=now)
            )

    def detener_tarea(self) -> TimeEntry | None:
        """Cierra el intervalo en curso guardando `ended_at`; None si no había."""
        now = self._now()
        with self._entries.transaction():
            return self._entries.close_open_entry(now)

    def entry_abierta(self) -> TimeEntry | None:
        """Intervalo en curso en toda la BD (para recuperar el estado al arrancar)."""
        return self._entries.get_open_entry()

    def listar_intervalos(self, session_id: int | None = None) -> list[TimeEntry]:
        """Intervalos de las tareas de la sesión indicada (o la actual)."""
        session = self._sesion_o_actual(session_id)
        return self._entries.list_by_session(session.id)

    # ------------------------------------------------------------------ internos

    def _cerrar_sesiones_abiertas(self, ended_at: datetime) -> None:
        """(§5.3) Cierra TODA sesión abierta y la entry global en curso.

        Debe llamarse dentro de una transacción. Orden coherente con
        `cerrar_sesion`: primero la entry abierta (máx. 1 global; `None` si no
        la hay) y después cada sesión abierta con `ended_at`. Cierra todas las
        abiertas (no solo la más reciente) para reparar también BDs heredadas
        de la Fase 1, que permitían varias sesiones abiertas.

        Si no hay ninguna sesión abierta, es un no-op: crear la primera sesión
        no toca la BD más allá del INSERT.
        """
        abiertas = [s for s in self._sessions.list_all() if s.is_open]
        if not abiertas:
            return
        self._entries.close_open_entry(ended_at)
        for sesion in abiertas:
            self._sessions.set_ended_at(sesion.id, ended_at)

    def _sesion_o_actual(self, session_id: int | None) -> Session:
        if session_id is None:
            if self._sesion_actual_id is None:
                raise ValidationError(
                    "No hay sesión seleccionada; crea o selecciona una sesión primero"
                )
            session_id = self._sesion_actual_id
        return self._sessions.get(session_id)
