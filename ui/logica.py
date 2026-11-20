"""Lógica de presentación pura de la UI (sin Flet, sin BD): testeable sola.

Reúne los cálculos que las vistas necesitan pintar (cronómetro, totales,
rutas, resúmenes) para que `ui/pages` solo componga controles y `ui/app.py`
solo coordine navegación y llamadas al servicio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.models import Session, Task, TimeEntry
from ui import format as fmt

RUTA_INICIO = "/"


# ------------------------------------------------------------------- rutas

def ruta_sesion(session_id: int) -> str:
    """Ruta de la vista de sesión (`/sesion/7`)."""
    return f"/sesion/{session_id}"


def id_sesion_de_ruta(route: str | None) -> int | None:
    """`/sesion/7` → 7; `/` u otras rutas → None."""
    if not route or not route.startswith("/sesion/"):
        return None
    try:
        return int(route.removeprefix("/sesion/"))
    except ValueError:
        return None


# --------------------------------------------------------------- cronómetro

def segundos_desde(inicio: datetime, ahora: datetime) -> int:
    """Segundos enteros transcurridos desde `inicio` (nunca negativos)."""
    return max(0, int((ahora - inicio).total_seconds()))


def entrada_de_sesion(entrada: TimeEntry | None, sesion_id: int) -> TimeEntry | None:
    """La entry abierta SOLO si pertenece a esta sesión (nunca en cerradas
    ajenas): filtra la única entry global en curso."""
    if entrada is None or entrada.session_id != sesion_id:
        return None
    return entrada


# --------------------------------------------------------------- duraciones

def segundos_entry(entry: TimeEntry, ahora: datetime, sesion_abierta: bool) -> int:
    """Duración del intervalo en segundos.

    - Cerrado: `ended_at - started_at`.
    - Abiert y en una sesión abierta: hasta `ahora` (el cronómetro corre).
    - Abiert en una sesión cerrada (estado inalcanzable por las reglas de
      negocio): 0 — una sesión cerrada nunca acumula tiempo.
    """
    if entry.ended_at is not None:
        fin = entry.ended_at
    elif sesion_abierta:
        fin = ahora
    else:
        return 0
    return max(0, int((fin - entry.started_at).total_seconds()))


def total_sesion(
    intervalos: list[TimeEntry], ahora: datetime, sesion_abierta: bool
) -> int:
    """Duración total de una sesión (suma de sus intervalos)."""
    return sum(segundos_entry(e, ahora, sesion_abierta) for e in intervalos)


# ------------------------------------------------------------- presentación

def nombre_tarea(tareas: list[Task], task_id: int) -> str:
    """Nombre de la tarea para una entry; si no está en el catálogo, un
    identificador legible (defensivo: el catálogo no se borra)."""
    for tarea in tareas:
        if tarea.id == task_id:
            return tarea.name
    return f"Tarea #{task_id}"


@dataclass(frozen=True, slots=True)
class ResumenSesion:
    """Datos ya formateados de una sesión para pintarla en el listado."""

    id: int
    nombre: str
    fecha: str          # "19 nov 2026"
    estado: str         # "Abierta" / "Cerrada"
    duracion: str       # "1 h 23 min"
    intervalos: int
    abierta: bool


def resumen_sesion(
    sesion: Session, intervalos: list[TimeEntry], ahora: datetime
) -> ResumenSesion:
    """Agrupa lo que la portada muestra de una sesión (nombre, fecha,
    duración total, nº de intervalos y estado)."""
    return ResumenSesion(
        id=sesion.id if sesion.id is not None else 0,
        nombre=sesion.name,
        fecha=fmt.fecha_corta(sesion.created_at),
        estado=fmt.estado_sesion(sesion.is_open),
        duracion=fmt.duracion_legible(total_sesion(intervalos, ahora, sesion.is_open)),
        intervalos=len(intervalos),
        abierta=sesion.is_open,
    )
