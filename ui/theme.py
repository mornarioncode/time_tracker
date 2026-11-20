"""Tema Material limpio y disposición común de todas las ventanas (Fase 2).

Decisiones de diseño (prioridad del usuario: "muy limpia"):
- Material 3 con semilla índigo; el modo claro/oscuro lo decide el sistema
  (`ThemeMode.SYSTEM`: respeta el tema del SO en el arranque).
- Contenido en una columna centrada de ancho fijo (`ANCHO_CONTENIDO`) para que
  en escritorio el texto no se estire de borde a borde.
- Tarjetas (`Card`) como único contenedor de secciones: título + cuerpo.
"""

from __future__ import annotations

import flet as ft

ANCHO_CONTENIDO = 740  # columna centrada (legible en escritorio)


def configurar_pagina(page: ft.Page) -> None:
    """Tema Material + geometría de la ventana (target Windows)."""
    page.title = "Time Tracker"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO, use_material3=True)
    page.window.width = 1120
    page.window.height = 800
    page.window.min_width = 800
    page.window.min_height = 600


def contenedor(controles: list[ft.Control]) -> ft.Control:
    """Fila centrada con la columna de ancho fijo: base de todas las vistas."""
    interior = ft.Container(
        ft.Column(controles, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        width=ANCHO_CONTENIDO,
    )
    return ft.Row([interior], alignment=ft.MainAxisAlignment.CENTER)


def vista(route: str, appbar: ft.AppBar, controles: list[ft.Control]) -> ft.View:
    """`View` estándar: appbar + contenido con scroll y ancho centrado."""
    return ft.View(
        route=route,
        appbar=appbar,
        controls=[contenedor(controles)],
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        spacing=0,
    )


def tarjeta(controles: list[ft.Control]) -> ft.Card:
    """Card Material con su contenido espaciado y a ancho completo."""
    return ft.Card(
        content=ft.Container(
            ft.Column(
                controles,
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=16,
        )
    )


def titulo(texto: str) -> ft.Text:
    """Título de sección de tarjeta (16 px, negrita)."""
    return ft.Text(texto, size=16, weight=ft.FontWeight.BOLD)


def apoyo(texto: str) -> ft.Text:
    """Texto secundario de apoyo (12 px, gris)."""
    return ft.Text(texto, size=12, color=ft.Colors.OUTLINE)
