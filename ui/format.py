"""Formateo de fechas, horas y duraciones para la UI (puro: sin Flet ni BD).

Todos los instantes llegan del dominio como datetimes *aware* en UTC; aquí se
convierten a la hora local del sistema y se pintan en español.
"""

from __future__ import annotations

from datetime import datetime

_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")


def hhmmss(segundos: int) -> str:
    """`01:02:03` — cronómetro y duraciones; las horas pueden pasar de 23."""
    total = max(0, int(segundos))
    horas, resto = divmod(total, 3600)
    minutos, seg = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{seg:02d}"


def hora(dt: datetime) -> str:
    """`09:00` en hora local del sistema."""
    return dt.astimezone().strftime("%H:%M")


def fecha_corta(dt: datetime) -> str:
    """`19 nov 2026` en hora local del sistema."""
    local = dt.astimezone()
    return f"{local.day:02d} {_MESES[local.month - 1]} {local.year}"


def rango_horas(inicio: datetime, fin: datetime | None) -> str:
    """`09:00 - 10:30`; sin cierre aún → `09:00 - en curso`."""
    if fin is None:
        return f"{hora(inicio)} - en curso"
    return f"{hora(inicio)} - {hora(fin)}"


def duracion_legible(segundos: int) -> str:
    """`45 s`, `12 min`, `1 h 23 min` — totales de sesión en el listado."""
    total = max(0, int(segundos))
    if total < 60:
        return f"{total} s"
    horas, resto = divmod(total, 3600)
    minutos, _ = divmod(resto, 60)
    if horas == 0:
        return f"{minutos} min"
    if minutos == 0:
        return f"{horas} h"
    return f"{horas} h {minutos} min"


def estado_sesion(abierta: bool) -> str:
    """`Abierta` / `Cerrada`."""
    return "Abierta" if abierta else "Cerrada"
