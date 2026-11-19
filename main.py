"""Punto de entrada de Time Tracker (Fase 0: humo de arranque de Flet).

La UI real llega en la Fase 2 (`ui/`); esta versión solo comprueba que la
ventana se abre en Windows: `uv run flet run main.py` o `uv run python main.py`.
"""

from __future__ import annotations

import flet as ft


def main(page: ft.Page) -> None:
    page.title = "Time Tracker"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.add(ft.Text("Hola, Time Tracker!", size=24))


if __name__ == "__main__":
    ft.run(main)
