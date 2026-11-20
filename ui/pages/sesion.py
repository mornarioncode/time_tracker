"""Vista de sesión: cronómetro, catálogo global de tareas e intervalos (Fase 2).

Solo compone controles: recibe la sesión, sus intervalos, el catálogo y la
entry en curso ya resueltos por `ui/app.py`, y callbacks para cada acción.

Sesión cerrada = historial de solo lectura: se pinta el aviso y NO se emiten
controles de escritura (añadir/iniciar/detener/terminar).
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import flet as ft

from core.models import Session, Task, TimeEntry
from ui import format as fmt, logica, theme


def construir_vista_sesion(
    sesion: Session,
    *,
    tareas: list[Task],
    intervalos: list[TimeEntry],
    entrada: TimeEntry | None,
    ahora: datetime,
    lbl_crono: ft.Text,
    on_anadir_tarea: Callable[[str], None],
    on_iniciar_tarea: Callable[[int], None],
    on_detener: Callable[[], None],
    on_terminar_sesion: Callable[[], None],
    on_volver: Callable[[], None],
) -> ft.View:
    """`View` de la sesión seleccionada.

    - **Cronómetro**: `lbl_crono` lo trae `ui/app.py` (lo actualiza cada
      segundo con `page.run_task`); aquí solo se coloca.
    - **Tareas**: catálogo global; añadir (campo + Enter/botón) y pulsar una
      para iniciar/cambiar (no-op si ya corre, lo decide el servicio).
    - **Intervalos**: tarea, inicio-fin y duración `hh:mm:ss` releídos tras
      cada acción (modelos inmutables: el snapshot nunca es el vigente).
    """
    abierta = sesion.is_open
    corriendo_id = entrada.task_id if entrada is not None else None

    controles: list[ft.Control] = []

    # ------------------------------------------------- aviso solo lectura
    if not abierta:
        controles.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.HISTORY, size=18, color=ft.Colors.OUTLINE),
                        ft.Text("Sesión cerrada - historial de solo lectura",
                                size=13, color=ft.Colors.ON_SURFACE),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=12,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border_radius=8,
            )
        )

    # --------------------------------------------------------- cronómetro
    if entrada is not None:
        estado_fila = ft.Row(
            [
                ft.Icon(ft.Icons.PLAY_ARROW, size=16, color=ft.Colors.GREEN),
                ft.Text(
                    f"Corriendo: {logica.nombre_tarea(tareas, entrada.task_id)}",
                    size=14,
                    color=ft.Colors.GREEN,
                    expand=True,
                    max_lines=1,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    else:
        estado_fila = ft.Row(
            [
                ft.Icon(ft.Icons.TIMER, size=16, color=ft.Colors.OUTLINE),
                ft.Text(
                    "Sin tarea en curso" if abierta else "Detenida",
                    size=14,
                    color=ft.Colors.OUTLINE,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    acciones: list[ft.Control] = []
    if abierta:
        if entrada is not None:
            acciones.append(
                ft.OutlinedButton(
                    "Detener",
                    icon=ft.Icons.STOP,
                    on_click=lambda e: on_detener(),
                )
            )
        acciones.append(
            ft.FilledButton(
                "Terminar sesión",
                icon=ft.Icons.CHECK,
                on_click=lambda e: on_terminar_sesion(),
            )
        )

    controles.append(
        theme.tarjeta(
            [
                ft.Row(
                    [
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.ACCESS_TIME,
                                        color=ft.Colors.PRIMARY, size=18),
                                theme.apoyo("Cronómetro"),
                            ],
                            spacing=6,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        theme.apoyo(
                            f"{fmt.estado_sesion(abierta)} · "
                            f"{fmt.fecha_corta(sesion.created_at)}"
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row([lbl_crono], alignment=ft.MainAxisAlignment.CENTER),
                estado_fila,
                *([ft.Row(acciones, spacing=12)] if acciones else []),
            ]
        )
    )

    # -------------------------------------------------------------- tareas
    controles_tareas: list[ft.Control] = [
        ft.Row(
            [theme.titulo("Tareas"), theme.apoyo("catálogo global")],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    ]
    if abierta:
        campo_tarea = ft.TextField(
            label="Nueva tarea",
            hint_text="p. ej. Revisar pull requests",
            expand=True,
            on_submit=lambda e: on_anadir_tarea(campo_tarea.value or ""),
        )
        controles_tareas.append(
            ft.Row(
                [
                    campo_tarea,
                    ft.FilledButton(
                        "Añadir",
                        icon=ft.Icons.ADD,
                        on_click=lambda e: on_anadir_tarea(campo_tarea.value or ""),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    if tareas:
        for i, tarea in enumerate(tareas):
            corriendo = tarea.id == corriendo_id
            if i:
                controles_tareas.append(ft.Divider(height=1))
            trailing = None
            if abierta and not corriendo:
                trailing = ft.IconButton(
                    ft.Icons.PLAY_ARROW,
                    tooltip=f"Iniciar '{tarea.name}'",
                    on_click=lambda e, tid=tarea.id: on_iniciar_tarea(tid),
                )
            controles_tareas.append(
                ft.ListTile(
                    dense=True,
                    leading=ft.Icon(
                        ft.Icons.PLAY_ARROW if corriendo else ft.Icons.TASK,
                        color=ft.Colors.GREEN if corriendo else ft.Colors.OUTLINE,
                    ),
                    title=ft.Text(tarea.name,
                                  color=ft.Colors.GREEN if corriendo else None),
                    trailing=trailing,
                    on_click=(lambda e, tid=tarea.id: on_iniciar_tarea(tid))
                    if abierta else None,
                )
            )
    else:
        controles_tareas.append(
            ft.Text("El catálogo está vacío. Añade tu primera tarea.",
                    size=13, color=ft.Colors.OUTLINE)
        )
    controles.append(theme.tarjeta(controles_tareas))

    # ---------------------------------------------------------- intervalos
    controles_intervalos: list[ft.Control] = [
        ft.Row(
            [
                theme.titulo("Intervalos"),
                theme.apoyo(str(len(intervalos))),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    ]
    if intervalos:
        for i, entry in enumerate(intervalos):
            if i:
                controles_intervalos.append(ft.Divider(height=1))
            dur = fmt.hhmmss(logica.segundos_entry(entry, ahora, abierta))
            en_curso = entrada is not None and entry.id == entrada.id
            controles_intervalos.append(
                ft.ListTile(
                    dense=True,
                    title=ft.Text(logica.nombre_tarea(tareas, entry.task_id)),
                    subtitle=ft.Text(
                        fmt.rango_horas(entry.started_at, entry.ended_at),
                        size=13,
                        color=ft.Colors.OUTLINE,
                    ),
                    trailing=ft.Text(
                        dur,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREEN if en_curso else None,
                    ),
                )
            )
    else:
        controles_intervalos.append(
            ft.Text("Sin intervalos todavía.", size=13, color=ft.Colors.OUTLINE)
        )
    controles.append(theme.tarjeta(controles_intervalos))

    # -------------------------------------------------------------- appbar
    appbar = ft.AppBar(
        title=ft.Text(sesion.name, weight=ft.FontWeight.BOLD, max_lines=1),
        actions=[
            ft.IconButton(
                ft.Icons.HOME,
                tooltip="Volver al inicio",
                on_click=lambda e: on_volver(),
            )
        ],
    )
    return theme.vista(logica.ruta_sesion(sesion.id or 0), appbar, controles)
