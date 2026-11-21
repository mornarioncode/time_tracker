"""Agregaciones puras de reporting (Fase 3): sin Flet, sin SQL.

Recibe `TimeEntry` / `Task` / `Session` ya materializados (la UI los obtiene
del servicio) y devuelve estructuras listas para pintar. Nada de BD ni de
presentación en este módulo.

Decisiones (§6 Fase 3):

- **Entries sin `ended_at` (en curso) se EXCLUYEN de todos los cálculos**
  (opción recomendada en el plan): sumar un cronómetro sin cerrar sesga los
  totales. Se devuelven aparte con `excluidas_abiertas` para que la UI las
  marque visualmente (aviso en el resumen del informe).
- **Un intervalo entra en un rango si su `started_at` cae dentro de él**; el
  agrupado por día/semana usa también `started_at` en **hora local** (la que
  se pinta en `ui/format`). Los intervalos NO se reparten entre días: son
  bloques cortos de trabajo y partirlos añadiría complejidad sin beneficio.
- Rangos de calendario local: `hoy` = desde la medianoche local de hoy;
  `7d` / `30d` = hoy-6 / hoy-29 … hoy (ambos inclusive). El `fin` de
  `Rango` es **exclusivo**.
- El CSV usa `;` como separador (Excel en español); la UI lo escribe con
  BOM UTF-8 (`utf-8-sig`) para que las tildes se lean bien.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from core.exceptions import ValidationError
from core.models import Session, Task, TimeEntry

#: Presets de rango que entiende `rango_preset`.
PRESETS_RANGO = ("hoy", "7d", "30d", "todo", "personalizado")

#: Un rango acotado genera barras por día; por encima de este número de días
#: se renuncia al relleno de días vacíos (se pintan solo los que tienen datos).
_DIAS_MAX_RANGO = 92


# --------------------------------------------------------------------- rangos

@dataclass(frozen=True, slots=True)
class Rango:
    """Ventana de fechas `[inicio, fin)` en instantes UTC aware.

    `inicio`/`fin` en `None` = sin límite por ese lado. `clave` conserva el
    preset que lo generó (para etiquetarlo en la UI).
    """

    clave: str
    inicio: datetime | None = None
    fin: datetime | None = None


def dia_local(momento: datetime) -> date:
    """Fecha **local** (la que ve la persona) de un instante UTC aware."""
    return momento.astimezone().date()


def _medianoche_local(d: date) -> datetime:
    """Inicio del día `d` en la zona horaria local (aware)."""
    return datetime.combine(d, time.min).astimezone()


def rango_preset(clave: str, ahora: datetime) -> Rango:
    """Rango predefinido evaluado contra el reloj `ahora` (aware).

    - `hoy`: desde la medianoche local de hoy.
    - `7d` / `30d`: últimos 7 / 30 días de calendario incluyendo hoy.
    - `todo`: sin límites.
    - `personalizado`: usar `rango_fechas` → aquí lanza `ValidationError`.
    """
    if clave == "todo":
        return Rango(clave="todo")
    if clave in ("7d", "30d"):
        dias = 7 if clave == "7d" else 30
        desde = dia_local(ahora) - timedelta(days=dias - 1)
        return Rango(clave=clave, inicio=_medianoche_local(desde))
    if clave == "hoy":
        return Rango(clave="hoy", inicio=_medianoche_local(dia_local(ahora)))
    if clave == "personalizado":
        raise ValidationError(
            "El rango personalizado necesita las fechas 'desde' y 'hasta'"
        )
    raise ValidationError(f"Rango desconocido: {clave}")


def rango_fechas(desde: date, hasta: date) -> Rango:
    """Rango personalizado por fechas locales (ambas inclusive)."""
    if desde > hasta:
        raise ValidationError(
            "La fecha 'desde' no puede ser posterior a la 'hasta'"
        )
    inicio = _medianoche_local(desde)
    fin = _medianoche_local(hasta + timedelta(days=1))  # exclusivo
    return Rango(clave="personalizado", inicio=inicio, fin=fin)


# -------------------------------------------------------------------- filtros

def _coincide(
    entry: TimeEntry,
    rango: Rango | None,
    session_id: int | None,
    task_id: int | None,
) -> bool:
    """¿Cumple la entry el rango (por `started_at`) y los filtros sueltos?"""
    if rango is not None:
        if rango.inicio is not None and entry.started_at < rango.inicio:
            return False
        if rango.fin is not None and entry.started_at >= rango.fin:
            return False
    if session_id is not None and entry.session_id != session_id:
        return False
    if task_id is not None and entry.task_id != task_id:
        return False
    return True


def filtrar(
    entries: list[TimeEntry],
    *,
    rango: Rango | None = None,
    session_id: int | None = None,
    task_id: int | None = None,
) -> list[TimeEntry]:
    """Intervalos **cerrados** que cumplen los filtros (los abiertos, nunca)."""
    return [
        e for e in entries
        if e.ended_at is not None and _coincide(e, rango, session_id, task_id)
    ]


def excluidas_abiertas(
    entries: list[TimeEntry],
    *,
    rango: Rango | None = None,
    session_id: int | None = None,
    task_id: int | None = None,
) -> list[TimeEntry]:
    """Intervalos SIN `ended_at` que encajarían en el filtro.

    No entran en ningún total; la UI los muestra como aviso (decisión Fase 3:
    "excluir y marcar visualmente").
    """
    return [
        e for e in entries
        if e.ended_at is None and _coincide(e, rango, session_id, task_id)
    ]


# -------------------------------------------------------------------- totales

@dataclass(frozen=True, slots=True)
class TotalTarea:
    """Segundos acumulados de una tarea dentro del filtro."""

    task_id: int
    nombre: str
    segundos: int
    intervalos: int


@dataclass(frozen=True, slots=True)
class TotalDia:
    """Segundos de un día local (los vacíos del rango llegan a 0)."""

    dia: date
    segundos: int
    intervalos: int


@dataclass(frozen=True, slots=True)
class TotalSemana:
    """Segundos de una semana ISO (empezada el lunes)."""

    lunes: date
    segundos: int
    intervalos: int


def lunes_de(d: date) -> date:
    """Lunes (inicio de la semana ISO) de la fecha local `d`."""
    return d - timedelta(days=d.weekday())


def _segundos_de(entry: TimeEntry) -> int:
    """Duración en segundos (solo intervalos cerrados llegan hasta aquí)."""
    return entry.duration_seconds or 0


def _cerradas(entries: list[TimeEntry]) -> list[TimeEntry]:
    """Defensivo: los totales ignoran cualquier intervalo en curso."""
    return [e for e in entries if e.ended_at is not None]


def totales_por_tarea(
    entries: list[TimeEntry], tareas: list[Task]
) -> list[TotalTarea]:
    """Suma por tarea, de mayor a menor (solo las que tienen datos).

    Las tareas ausentes del catálogo se etiquetan `Tarea #id` (defensivo: el
    catálogo no se borra, pero una BD heredada podría tener huérfanas).
    """
    nombres = {t.id: t.name for t in tareas if t.id is not None}
    acumulado: dict[int, tuple[int, int]] = {}
    for e in _cerradas(entries):
        seg, n = acumulado.get(e.task_id, (0, 0))
        acumulado[e.task_id] = (seg + _segundos_de(e), n + 1)
    totales = [
        TotalTarea(
            task_id=task_id,
            nombre=nombres.get(task_id, f"Tarea #{task_id}"),
            segundos=seg,
            intervalos=n,
        )
        for task_id, (seg, n) in acumulado.items()
    ]
    totales.sort(key=lambda t: (-t.segundos, t.nombre))
    return totales


def totales_por_dia(
    entries: list[TimeEntry], *, dias: list[date] | None = None
) -> list[TotalDia]:
    """Suma por día **local** de `started_at`, ordenado ascendentemente.

    `dias`: lista de días a representar. Se rellenan con 0 los que no tengan
    datos y se añade cualquier día con datos que falte en la lista (nunca se
    pierde información).
    """
    por_dia: dict[date, tuple[int, int]] = {}
    for e in _cerradas(entries):
        d = dia_local(e.started_at)
        seg, n = por_dia.get(d, (0, 0))
        por_dia[d] = (seg + _segundos_de(e), n + 1)
    claves = set(por_dia) if dias is None else set(dias) | set(por_dia)
    return [
        TotalDia(
            dia=d,
            segundos=por_dia.get(d, (0, 0))[0],
            intervalos=por_dia.get(d, (0, 0))[1],
        )
        for d in sorted(claves)
    ]


def totales_por_semana(entries: list[TimeEntry]) -> list[TotalSemana]:
    """Suma por semana ISO (lunes local de `started_at`), de más antigua a
    más reciente. Solo semanas con datos."""
    por_semana: dict[date, tuple[int, int]] = {}
    for e in _cerradas(entries):
        lunes = lunes_de(dia_local(e.started_at))
        seg, n = por_semana.get(lunes, (0, 0))
        por_semana[lunes] = (seg + _segundos_de(e), n + 1)
    return [
        TotalSemana(lunes=lunes, segundos=seg, intervalos=n)
        for lunes, (seg, n) in sorted(por_semana.items())
    ]


# ------------------------------------------------------------------- informe

@dataclass(frozen=True, slots=True)
class Informe:
    """Snapshot de reporting listo para pintar (Fase 3)."""

    rango: Rango
    segundos: int
    intervalos: int
    excluidas: int  # en curso: fuera de los cálculos, para el aviso visual
    entries: list[TimeEntry]  # filtradas, de más reciente a más antigua
    por_tarea: list[TotalTarea]
    por_dia: list[TotalDia]
    por_semana: list[TotalSemana]


def _dias_del_rango(
    rango: Rango, entries: list[TimeEntry], ahora: datetime
) -> list[date] | None:
    """Días locales del rango para rellenar el eje; `None` = solo con datos.

    - `todo` (sin `inicio`): sin relleno (el histórico puede ser largo).
    - Rangos acotados: todos los días desde `inicio` hasta el fin del rango
      (o hoy, si no tiene fin), limitado a `_DIAS_MAX_RANGO`.
    """
    if rango.inicio is None:
        return None
    desde = dia_local(rango.inicio)
    if rango.fin is not None:
        hasta = dia_local(rango.fin - timedelta(microseconds=1))
    else:
        hasta = dia_local(ahora)
        for e in entries:
            d = dia_local(e.started_at)
            if d > hasta:
                hasta = d
    if hasta < desde:
        hasta = desde
    if (hasta - desde).days + 1 > _DIAS_MAX_RANGO:
        return None
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


def informe(
    entries: list[TimeEntry],
    tareas: list[Task],
    *,
    rango: Rango,
    ahora: datetime,
    session_id: int | None = None,
    task_id: int | None = None,
) -> Informe:
    """Agrega `entries` aplicando rango + filtros de sesión y tarea.

    - Excluye los intervalos en curso (`ended_at is None`) y los cuenta en
      `excluidas` para que la UI los marque.
    - `ahora` fija el día de hoy para rellenar los días de un rango abierto.
    """
    kwargs = dict(rango=rango, session_id=session_id, task_id=task_id)
    filtradas = filtrar(entries, **kwargs)
    fuera = excluidas_abiertas(entries, **kwargs)
    dias = _dias_del_rango(rango, filtradas, ahora)
    return Informe(
        rango=rango,
        segundos=sum(_segundos_de(e) for e in filtradas),
        intervalos=len(filtradas),
        excluidas=len(fuera),
        entries=sorted(
            filtradas, key=lambda e: e.started_at, reverse=True
        ),
        por_tarea=totales_por_tarea(filtradas, tareas),
        por_dia=totales_por_dia(filtradas, dias=dias),
        por_semana=totales_por_semana(filtradas),
    )


# ---------------------------------------------------------------------- csv

def csv_detalle(
    entries: list[TimeEntry],
    tareas: list[Task],
    sesiones: list[Session],
) -> str:
    """CSV del detalle (separador `;` para Excel en español).

    Solo intervalos cerrados, de más reciente a más antigua. La UI lo escribe
    con BOM UTF-8 (`utf-8-sig`) para que Excel detecte las tildes.
    """
    nombres_tareas = {t.id: t.name for t in tareas if t.id is not None}
    nombres_sesiones = {s.id: s.name for s in sesiones if s.id is not None}
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(
        ["Fecha", "Tarea", "Sesión", "Inicio", "Fin", "Duración (s)"]
    )
    for e in sorted(
        _cerradas(entries), key=lambda e: e.started_at, reverse=True
    ):
        writer.writerow(
            [
                dia_local(e.started_at).isoformat(),  # AAAA-MM-DD
                nombres_tareas.get(e.task_id, f"Tarea #{e.task_id}"),
                nombres_sesiones.get(e.session_id, f"Sesión #{e.session_id}"),
                e.started_at.astimezone().strftime("%H:%M"),
                (e.ended_at or e.started_at).astimezone().strftime("%H:%M"),
                _segundos_de(e),
            ]
        )
    return buffer.getvalue()
