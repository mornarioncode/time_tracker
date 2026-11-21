"""Vista de informes: filtros, resumen y gráficos con `flet-charts` (Fase 3).

Solo compone controles a partir del `Informe` que agrega `reports/stats` (lo
construye `ui/app.py`) y delega cada cambio de filtro en callbacks. Tres
vistas conmutables:

- **Por día**: barras por día local + totales por semana debajo.
- **Por tarea**: tarta con el reparto por tarea + leyenda con totales.
- **Detalle**: tabla detallada con botón de exportación a CSV.

Los filtros (rango hoy/7d/30d/todo/personalizado, sesión y tarea) viven en
`ui.logica.FiltrosInforme`; aquí solo se pintan y se avisa de los cambios.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Callable

import flet as ft
from flet_charts import (
    BarChart,
    BarChartGroup,
    BarChartRod,
    ChartAxis,
    ChartAxisLabel,
    ChartGridLines,
    PieChart,
    PieChartSection,
)

from core.models import Session, Task
from reports.stats import Informe
from ui import format as fmt, logica, theme

# Colores del reparto por tarea (ciclo: tarta y leyenda usan el mismo)
_PALETA = (
    ft.Colors.INDIGO, ft.Colors.TEAL, ft.Colors.ORANGE, ft.Colors.PINK,
    ft.Colors.GREEN, ft.Colors.PURPLE, ft.Colors.AMBER, ft.Colors.CYAN,
    ft.Colors.DEEP_PURPLE, ft.Colors.LIME, ft.Colors.BROWN, ft.Colors.BLUE_GREY,
)


# ------------------------------------------------------------------ helpers

def _fecha(d: date) -> str:
    """`19 nov 2026` de una fecha local (reutiliza `ui/format`: una fecha
    naive se interpreta como hora local)."""
    return fmt.fecha_corta(datetime.combine(d, time.min))


def _etiqueta_rango(informe: Informe, filtros: logica.FiltrosInforme) -> str:
    """Etiqueta del rango activo para el resumen."""
    if informe.rango.clave == "personalizado":
        return f"{_fecha(filtros.desde)} - {_fecha(filtros.hasta)}"
    return {
        "hoy": "Hoy",
        "7d": "Últimos 7 días",
        "30d": "Últimos 30 días",
        "todo": "Todo el historial",
    }.get(informe.rango.clave, informe.rango.clave)


def _valor_dropdown(e: Any) -> str | None:
    """Valor seleccionado de un Dropdown (`value` sincronizado; `data` como
    respaldo por si el cliente no lo hubiera propagado aún)."""
    valor = getattr(getattr(e, "control", None), "value", None)
    if isinstance(valor, str):
        return valor
    datos = getattr(e, "data", None)
    return datos if isinstance(datos, str) else None


def _id_de_clave(clave: str | None) -> int | None:
    """Clave de opción (`"todas"` / `"12"`) → id de filtro o None."""
    if clave is None or clave == "todas":
        return None
    try:
        return int(clave)
    except ValueError:
        return None


def _primer_segmento(e: Any) -> str | None:
    """Primer valor seleccionado de un SegmentedButton (`data` documentado;
    `selected` como respaldo)."""
    datos = getattr(e, "data", None)
    if isinstance(datos, list) and datos:
        return str(datos[0])
    seleccion = getattr(getattr(e, "control", None), "selected", None)
    if isinstance(seleccion, list) and seleccion:
        return str(seleccion[0])
    return None


def _al_cambiar_valor(e: Any, callback: Callable[[str], None]) -> None:
    """Común a los dos SegmentedButton: primer segmento seleccionado."""
    valor = _primer_segmento(e)
    if valor is not None:
        callback(valor)


def _marcas_eje(max_seg: int) -> list[int]:
    """Valores (segundos) de las marcas del eje Y: ~4 divisiones en
    unidades redondas (min, h o días)."""
    if max_seg <= 0:
        return []
    objetivo = max_seg / 4
    pasos = (
        60, 300, 900, 1800, 3600, 2 * 3600, 3 * 3600, 6 * 3600,
        12 * 3600, 24 * 3600, 2 * 24 * 3600, 7 * 24 * 3600,
    )
    paso = pasos[-1]
    for p in pasos:
        if p >= objetivo:
            paso = p
            break
    return list(range(0, max_seg + paso, paso))


def _etiqueta_marca(segundos: int) -> str:
    """Etiqueta compacta del eje Y: `0`, `45 min`, `2 h`, `3 d`."""
    if segundos == 0:
        return "0"
    if segundos % 86400 == 0:
        return f"{segundos // 86400} d"
    if segundos % 3600 == 0:
        return f"{segundos // 3600} h"
    if segundos % 60 == 0:
        return f"{segundos // 60} min"
    return f"{segundos} s"


# ------------------------------------------------------------- tres vistas

def _vista_dia(informe: Informe) -> list[ft.Control]:
    """Barras por día local + totales por semana debajo."""
    dias = informe.por_dia
    max_seg = max((d.segundos for d in dias), default=0)
    marcas = _marcas_eje(max_seg)

    grupos = [
        BarChartGroup(
            x=i,
            rods=[
                BarChartRod(
                    to_y=d.segundos,
                    color=ft.Colors.PRIMARY,
                    tooltip=(
                        f"{_fecha(d.dia)} · {fmt.duracion_legible(d.segundos)}"
                    ),
                )
            ],
        )
        for i, d in enumerate(dias)
    ]
    # Etiqueta del eje X como máximo cada ~12 días para que no se pisen.
    paso_etiqueta = max(1, (len(dias) + 11) // 12)
    eje_x = ChartAxis(
        labels=[
            ChartAxisLabel(value=i, label=f"{d.dia.day:02d}/{d.dia.month:02d}")
            for i, d in enumerate(dias)
            if i % paso_etiqueta == 0
        ],
        label_size=44,
    )
    eje_y = (
        ChartAxis(
            labels=[
                ChartAxisLabel(value=m, label=_etiqueta_marca(m))
                for m in marcas
            ],
            label_size=48,
        )
        if marcas
        else ChartAxis(show_labels=False)
    )
    rejilla = (
        ChartGridLines(
            interval=marcas[1] - marcas[0],
            color=ft.Colors.OUTLINE_VARIANT,
            width=1,
        )
        if len(marcas) > 1
        else None
    )
    grafico = BarChart(
        groups=grupos,
        left_axis=eje_y,
        bottom_axis=eje_x,
        horizontal_grid_lines=rejilla,
        min_y=0,
        height=280,
    )

    semanas: list[ft.Control] = [
        ft.Divider(height=1),
        theme.titulo("Por semana"),
    ]
    for i, sem in enumerate(informe.por_semana):
        if i:
            semanas.append(ft.Divider(height=1))
        plural = "" if sem.intervalos == 1 else "s"
        semanas.append(
            ft.Row(
                [
                    ft.Text(
                        f"Semana del {_fecha(sem.lunes)}",
                        size=14,
                        expand=True,
                    ),
                    ft.Text(
                        f"{fmt.duracion_legible(sem.segundos)} · "
                        f"{sem.intervalos} intervalo{plural}",
                        size=13,
                        color=ft.Colors.OUTLINE,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    return [theme.apoyo("Duración por día (hora local)"), grafico, *semanas]


def _vista_tarea(informe: Informe) -> list[ft.Control]:
    """Tarta del reparto por tarea + leyenda con totales y porcentajes."""
    total = informe.segundos
    sections: list[PieChartSection] = []
    leyenda: list[ft.Control] = []
    for i, tarea in enumerate(informe.por_tarea):
        color = _PALETA[i % len(_PALETA)]
        pct = int(round(100 * tarea.segundos / total)) if total else 0
        if tarea.segundos > 0:
            sections.append(
                PieChartSection(
                    value=tarea.segundos, color=color, title=f"{pct}%"
                )
            )
        if i:
            leyenda.append(ft.Divider(height=1))
        leyenda.append(
            ft.Row(
                [
                    ft.Container(
                        width=12, height=12, border_radius=6, bgcolor=color
                    ),
                    ft.Text(tarea.nombre, size=14, expand=True, max_lines=1),
                    ft.Text(
                        f"{fmt.duracion_legible(tarea.segundos)} · {pct} %",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    controles: list[ft.Control] = [
        theme.apoyo("Reparto del tiempo por tarea")
    ]
    if sections:
        controles.append(PieChart(sections=sections, height=300))
        controles.append(ft.Divider(height=1))
    controles.extend(leyenda)
    return controles


def _vista_detalle(
    informe: Informe,
    tareas: list[Task],
    sesiones: list[Session],
    on_exportar: Callable[[], None],
) -> list[ft.Control]:
    """Tabla detallada de los intervalos filtrados + exportación CSV."""
    filas = [
        ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(fmt.fecha_corta(e.started_at), size=13)),
                ft.DataCell(
                    ft.Text(logica.nombre_tarea(tareas, e.task_id), size=13)
                ),
                ft.DataCell(
                    ft.Text(
                        logica.nombre_sesion(sesiones, e.session_id), size=13
                    )
                ),
                ft.DataCell(
                    ft.Text(fmt.rango_horas(e.started_at, e.ended_at), size=13)
                ),
                ft.DataCell(
                    ft.Text(fmt.hhmmss(e.duration_seconds or 0), size=13)
                ),
            ]
        )
        for e in informe.entries
    ]
    tabla = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Fecha")),
            ft.DataColumn(ft.Text("Tarea")),
            ft.DataColumn(ft.Text("Sesión")),
            ft.DataColumn(ft.Text("Horario")),
            ft.DataColumn(ft.Text("Duración"), numeric=True),
        ],
        rows=filas,
        column_spacing=16,
        horizontal_margin=0,
        heading_row_height=36,
        data_row_min_height=32,
    )
    plural = "" if informe.intervalos == 1 else "s"
    cabecera = ft.Row(
        [
            theme.titulo(f"Detalle: {informe.intervalos} intervalo{plural}"),
            ft.OutlinedButton(
                "Exportar CSV",
                icon=ft.Icons.DOWNLOAD,
                on_click=lambda e: on_exportar(),
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    # Scroll horizontal (el eje lo fija el propio Row en Flet 1.x): evita
    # que nombres largos desborden los 740 px.
    return [cabecera, ft.Row([tabla], scroll=ft.ScrollMode.AUTO)]


def _contenido_vista(
    vista: str,
    informe: Informe,
    tareas: list[Task],
    sesiones: list[Session],
    on_exportar: Callable[[], None],
) -> list[ft.Control]:
    """Cuerpo de la vista activa (placeholder si no hay datos en el filtro)."""
    if informe.intervalos == 0:
        return [
            ft.Text(
                "Sin datos para los filtros seleccionados.",
                size=13,
                color=ft.Colors.OUTLINE,
                text_align=ft.TextAlign.CENTER,
            )
        ]
    if vista == "tarea":
        return _vista_tarea(informe)
    if vista == "detalle":
        return _vista_detalle(informe, tareas, sesiones, on_exportar)
    return _vista_dia(informe)


# ------------------------------------------------------------ construcción

def construir_vista_informe(
    informe: Informe,
    *,
    sesiones: list[Session],
    tareas: list[Task],
    filtros: logica.FiltrosInforme,
    on_preset: Callable[[str], None],
    on_vista: Callable[[str], None],
    on_elegir_desde: Callable[[], None],
    on_elegir_hasta: Callable[[], None],
    on_sesion: Callable[[int | None], None],
    on_tarea: Callable[[int | None], None],
    on_exportar: Callable[[], None],
    on_volver: Callable[[], None],
) -> ft.View:
    """`View` de informes (`/informes`).

    - **Filtros**: rango (SegmentedButton), fechas del rango personalizado
      (los `DatePicker` los abre `ui/app.py`), sesión y tarea (Dropdown).
    - **Resumen**: total del rango, nº de intervalos y aviso de los
      excluidos por estar en curso (decisión Fase 3).
    - **Tres vistas** conmutables: barras por día, tarta por tarea y tabla
      detallada exportable a CSV.
    """
    controles: list[ft.Control] = []

    # ---------------------------------------------------------- filtros
    selector_rango = ft.SegmentedButton(
        segments=[
            ft.Segment(value="hoy", label=ft.Text("Hoy")),
            ft.Segment(value="7d", label=ft.Text("7 días")),
            ft.Segment(value="30d", label=ft.Text("30 días")),
            ft.Segment(value="todo", label=ft.Text("Todo")),
            ft.Segment(value="personalizado", label=ft.Text("Personalizado")),
        ],
        selected=[filtros.preset],
        on_change=lambda e: _al_cambiar_valor(e, on_preset),
    )

    opciones_sesion = [
        ft.dropdown.Option(key="todas", text="Todas las sesiones")
    ]
    opciones_sesion += [
        ft.dropdown.Option(key=str(s.id), text=s.name)
        for s in sesiones
        if s.id is not None
    ]
    dd_sesion = ft.Dropdown(
        label="Sesión",
        value="todas" if filtros.sesion_id is None else str(filtros.sesion_id),
        options=opciones_sesion,
        expand=True,
        on_select=lambda e: on_sesion(_id_de_clave(_valor_dropdown(e))),
    )

    opciones_tarea = [ft.dropdown.Option(key="todas", text="Todas las tareas")]
    opciones_tarea += [
        ft.dropdown.Option(key=str(t.id), text=t.name)
        for t in tareas
        if t.id is not None
    ]
    dd_tarea = ft.Dropdown(
        label="Tarea",
        value="todas" if filtros.tarea_id is None else str(filtros.tarea_id),
        options=opciones_tarea,
        expand=True,
        on_select=lambda e: on_tarea(_id_de_clave(_valor_dropdown(e))),
    )

    filas_filtro: list[ft.Control] = [
        ft.Row([selector_rango], alignment=ft.MainAxisAlignment.START)
    ]
    if filtros.preset == "personalizado":
        filas_filtro.append(
            ft.Row(
                [
                    ft.OutlinedButton(
                        f"Desde: {_fecha(filtros.desde)}",
                        icon=ft.Icons.CALENDAR_MONTH,
                        on_click=lambda e: on_elegir_desde(),
                    ),
                    ft.OutlinedButton(
                        f"Hasta: {_fecha(filtros.hasta)}",
                        icon=ft.Icons.CALENDAR_MONTH,
                        on_click=lambda e: on_elegir_hasta(),
                    ),
                ],
                spacing=12,
            )
        )
    filas_filtro.append(ft.Row([dd_sesion, dd_tarea], spacing=12))

    controles.append(
        theme.tarjeta(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.FILTER_ALT,
                            color=ft.Colors.PRIMARY,
                            size=18,
                        ),
                        theme.titulo("Filtros"),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                *filas_filtro,
            ]
        )
    )

    # ---------------------------------------------------------- resumen
    plural = "" if informe.intervalos == 1 else "s"
    resumen: list[ft.Control] = [
        ft.Row(
            [
                theme.titulo("Resumen"),
                theme.apoyo(_etiqueta_rango(informe, filtros)),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        ft.Row(
            [
                ft.Text(
                    fmt.duracion_legible(informe.segundos),
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.PRIMARY,
                ),
                ft.Column(
                    [
                        ft.Text(
                            f"{informe.intervalos} intervalo{plural}",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            fmt.hhmmss(informe.segundos),
                            size=13,
                            color=ft.Colors.OUTLINE,
                        ),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    ]
    if informe.excluidas:
        s = "" if informe.excluidas == 1 else "s"
        resumen.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING, color=ft.Colors.AMBER, size=18),
                    ft.Text(
                        f"{informe.excluidas} intervalo{s} en curso sin hora "
                        f"de fin: excluido{s} del informe.",
                        size=13,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
    controles.append(theme.tarjeta(resumen))

    # ------------------------------------------------------ tres vistas
    selector_vista = ft.SegmentedButton(
        segments=[
            ft.Segment(value="dia", label=ft.Text("Por día")),
            ft.Segment(value="tarea", label=ft.Text("Por tarea")),
            ft.Segment(value="detalle", label=ft.Text("Detalle")),
        ],
        selected=[filtros.vista],
        on_change=lambda e: _al_cambiar_valor(e, on_vista),
    )
    contenido = _contenido_vista(
        filtros.vista, informe, tareas, sesiones, on_exportar
    )
    controles.append(
        theme.tarjeta(
            [
                ft.Row(
                    [selector_vista], alignment=ft.MainAxisAlignment.START
                ),
                ft.Divider(height=1),
                *contenido,
            ]
        )
    )

    # ----------------------------------------------------------- appbar
    appbar = ft.AppBar(
        title=ft.Text("Informes", weight=ft.FontWeight.BOLD),
        actions=[
            ft.IconButton(
                ft.Icons.HOME,
                tooltip="Volver al inicio",
                on_click=lambda e: on_volver(),
            ),
        ],
    )
    return theme.vista(logica.RUTA_INFORMES, appbar, controles)
