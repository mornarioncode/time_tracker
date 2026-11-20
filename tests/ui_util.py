"""Utilidades para tests de la UI Flet (sin GUI real).

- Recorrido del árbol de controles de una `ft.View`: los hijos de Flet viven
  en atributos (`controls`, `actions`) o en el dict `_values` (valores de
  constructor); `caminar` recorre ambos sin entrar en `_internals` (ciclos).
- `PaginaFalsa`: sustituto mínimo de `ft.Page` para coordinar
  `TimeTrackerApp` (navegación, vistas, diálogos) sin ventana ni Flutter.

Los tests NO abren ventanas ni arrancan Flet: solo construyen controles
Python (son objetos normales) y disparan sus callbacks directamente.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Iterator

import flet as ft


# ------------------------------------------------------------ árbol de controles

def caminar(control: Any) -> Iterator[ft.Control]:
    """Recorre recursivamente todos los controles alcanzables desde `control`."""
    pendientes: list[Any] = [control]
    vistos: set[int] = set()
    while pendientes:
        c = pendientes.pop()
        if not isinstance(c, ft.Control) or id(c) in vistos:
            continue
        vistos.add(id(c))
        yield c
        valores = list(vars(c).values()) + list(getattr(c, "_values", {}).values())
        for valor in valores:
            if isinstance(valor, ft.Control):
                pendientes.append(valor)
            elif isinstance(valor, (list, tuple)):
                # en pila: se empujan en REVERSO para recorrer en orden de documento
                pendientes.extend(
                    v for v in reversed(valor) if isinstance(v, ft.Control)
                )
            elif isinstance(valor, dict):
                pendientes.extend(
                    v for v in reversed(list(valor.values()))
                    if isinstance(v, ft.Control)
                )


def controles(vista: Any) -> list[ft.Control]:
    """Todos los controles de una vista (lista materializada)."""
    return list(caminar(vista))


def valor(control: Any, campo: str) -> Any:
    """Valor de un campo venga del atributo o del `_values` de Flet."""
    v = getattr(control, campo, None)
    if v is None:
        v = control._values.get(campo)
    return v


def textos(vista: Any) -> list[str]:
    """Valores de todos los `ft.Text` del árbol (etiquetas visibles)."""
    return [
        c.value
        for c in controles(vista)
        if isinstance(c, ft.Text) and isinstance(c.value, str)
    ]


def etiquetas_botones(vista: Any) -> list[str]:
    """Texto de los botones con etiqueta (Filled/Outlined/TextButton)."""
    etiquetas = []
    for c in controles(vista):
        if isinstance(c, (ft.FilledButton, ft.OutlinedButton, ft.TextButton)):
            etiqueta = valor(c, "content")
            if isinstance(etiqueta, str):
                etiquetas.append(etiqueta)
    return etiquetas


def campos_texto(vista: Any) -> list[ft.TextField]:
    return [c for c in controles(vista) if isinstance(c, ft.TextField)]


def iconos_con_tooltip(vista: Any) -> list[str]:
    return [
        c.tooltip
        for c in controles(vista)
        if isinstance(c, ft.IconButton) and isinstance(c.tooltip, str)
    ]


def al_pulsar(control: Any) -> Any:
    """Callback `on_click` de un control (atributo o `_values`)."""
    cb = getattr(control, "on_click", None)
    if cb is None:
        cb = control._values.get("on_click")
    return cb


def boton(vista_o_dialogo: Any, etiqueta: str) -> Any:
    """Primer botón con esa etiqueta en la vista o en las acciones de un diálogo."""
    if isinstance(vista_o_dialogo, ft.AlertDialog):
        candidatos = vista_o_dialogo.actions
    else:
        candidatos = controles(vista_o_dialogo)
    for c in candidatos:
        if isinstance(c, (ft.FilledButton, ft.OutlinedButton, ft.TextButton)):
            if valor(c, "content") == etiqueta:
                return c
    raise AssertionError(f"No se encontró el botón {etiqueta!r}")


# ------------------------------------------------------------------ diálogos

def snacks(page: Any) -> list[ft.SnackBar]:
    return [d for d in page.dialogos if isinstance(d, ft.SnackBar)]


def dialogos_modales(page: Any) -> list[ft.AlertDialog]:
    return [d for d in page.dialogos if isinstance(d, ft.AlertDialog)]


def texto_snack(page: Any) -> str:
    """Texto del último SnackBar mostrado (o falla: el test exige feedback)."""
    if not snacks(page):
        raise AssertionError("No se mostró ningún SnackBar")
    contenido = valor(snacks(page)[-1], "content")
    return contenido.value


def texto_dialogo(dlg: ft.AlertDialog) -> tuple[str, str]:
    """(título, cuerpo) de un AlertDialog."""
    return valor(dlg, "title").value, valor(dlg, "content").value


# ------------------------------------------------------------- página simulada

class PaginaFalsa:
    """`ft.Page` mínima: registra navegación, vistas y diálogos.

    `run_task` NO ejecuta el bucle del cronómetro (cierra la corrutina para
    evitar warnings): el tick se prueba llamando a `_tick_cronometro` a mano.
    """

    def __init__(self, route: str = "/") -> None:
        self.route = route
        self.views: list = []
        self.dialogos: list = []
        self.navegaciones: list[str] = []
        self.actualizaciones = 0
        # atributos que `theme.configurar_pagina` rellena
        self.title: str | None = None
        self.theme_mode: Any = None
        self.theme: Any = None
        self.window = SimpleNamespace(
            width=None, height=None, min_width=None, min_height=None
        )
        self.on_route_change: Any = None
        self.on_view_pop: Any = None

    def update(self) -> None:
        self.actualizaciones += 1

    def navigate(self, route: str) -> None:
        self.navegaciones.append(route)
        self.route = route

    async def push_route(self, route: str) -> None:
        self.navegaciones.append(route)
        self.route = route

    def show_dialog(self, dialogo: Any) -> None:
        self.dialogos.append(dialogo)

    def pop_dialog(self) -> None:
        self.dialogos.pop()

    def run_task(self, target: Any, *args: Any) -> None:
        """`Page.run_task` recibe la FUNCIÓN corrutina: aquí NO se ejecuta
        (el cronómetro no late en tests); si llega una corrutina ya creada,
        se cierra para evitar el warning de "never awaited"."""
        if asyncio.iscoroutine(target):
            target.close()
        return None
