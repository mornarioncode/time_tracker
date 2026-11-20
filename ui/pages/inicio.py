"""Pantalla de inicio: crear/continuar/eliminar sesiones (Fase 2).

Solo compone controles a partir de `ResumenSesion` ya formateado y delega
todas las acciones en los callbacks que le pasa `ui/app.py`.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ui import theme
from ui.logica import ResumenSesion, RUTA_INICIO


def construir_vista_inicio(
    resumenes: list[ResumenSesion],
    *,
    on_crear: Callable[[str], None],
    on_abrir: Callable[[int], None],
    on_eliminar: Callable[[int, str], None],
) -> ft.View:
    """`View` de la portada.

    - Si hay sesión abierta, aviso destacado con **Continuar sesión**.
    - Formulario **Nueva sesión** (Enter o botón → crea y navega).
    - Listado de sesiones: nombre, fecha, duración total y estado. La fila
      completa abre la sesión (de solo lectura si está cerrada); el botón de
      papelera elimina **con confirmación**.
    """
    campo = ft.TextField(
        label="Nombre de la sesión",
        hint_text="p. ej. Semana 48 - App web",
        expand=True,
        on_submit=lambda e: on_crear(campo.value or ""),
    )
    formulario = ft.Row(
        [
            campo,
            ft.FilledButton(
                "Crear y empezar",
                icon=ft.Icons.ADD,
                on_click=lambda e: on_crear(campo.value or ""),
            ),
        ],
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    controles: list[ft.Control] = [
        theme.tarjeta([theme.titulo("Nueva sesión"), formulario])
    ]

    # ---------------------------------------------------- sesión en curso
    abierta = next((r for r in resumenes if r.abierta), None)
    if abierta is not None:
        controles.insert(
            0,
            theme.tarjeta(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.ACCESS_TIME, color=ft.Colors.PRIMARY),
                            ft.Column(
                                [
                                    ft.Text("Sesión en curso", size=12,
                                            color=ft.Colors.OUTLINE),
                                    ft.Text(abierta.nombre, size=16,
                                            weight=ft.FontWeight.BOLD),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.FilledButton(
                        "Continuar sesión",
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=lambda e, sid=abierta.id: on_abrir(sid),
                    ),
                ]
            ),
        )

    # --------------------------------------------------------- listado
    if resumenes:
        filas: list[ft.Control] = []
        for i, r in enumerate(resumenes):
            if i:
                filas.append(ft.Divider(height=1))
            estado_color = ft.Colors.GREEN if r.abierta else ft.Colors.OUTLINE
            plural = "intervalo" if r.intervalos == 1 else "intervalos"
            filas.append(
                ft.ListTile(
                    title=ft.Row(
                        [
                            ft.Text(r.nombre, weight=ft.FontWeight.BOLD, expand=True,
                                    max_lines=1),
                            ft.Text(r.estado, size=12, color=estado_color),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    subtitle=ft.Text(
                        f"{r.fecha} · {r.duracion} · {r.intervalos} {plural}",
                        size=13,
                        color=ft.Colors.OUTLINE,
                    ),
                    trailing=ft.IconButton(
                        ft.Icons.DELETE,
                        tooltip="Eliminar sesión",
                        on_click=lambda e, sid=r.id, nom=r.nombre:
                            on_eliminar(sid, nom),
                    ),
                    on_click=lambda e, sid=r.id: on_abrir(sid),
                )
            )
        controles.append(theme.tarjeta([theme.titulo("Sesiones"), *filas]))
    else:
        controles.append(
            theme.tarjeta(
                [
                    ft.Row(
                        [ft.Icon(ft.Icons.HISTORY, size=32, color=ft.Colors.OUTLINE)],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        "Aún no hay sesiones. Crea la primera arriba.",
                        color=ft.Colors.OUTLINE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ]
            )
        )

    appbar = ft.AppBar(title=ft.Text("Time Tracker", weight=ft.FontWeight.BOLD))
    return theme.vista(RUTA_INICIO, appbar, controles)
