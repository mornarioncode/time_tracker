"""Punto de entrada de Time Tracker (Fase 2: UI Flet, target Windows).

Arranca la interfaz con la BD por defecto (`~/.time_tracker/time_tracker.db`)
y el reloj real. Ejecutar con `uv run flet run main.py` o `uv run python main.py`.
"""

from __future__ import annotations

import flet as ft

from storage.factory import create_service
from ui.app import TimeTrackerApp


def main(page: ft.Page) -> None:
    _db, service = create_service()  # la BD vive en los repos del servicio
    TimeTrackerApp(page, service).arrancar()


if __name__ == "__main__":
    ft.run(main)
