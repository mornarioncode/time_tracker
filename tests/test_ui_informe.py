"""Tests de la pantalla de informes (Fase 3): navegación, vistas y callbacks.

Patrón de la Fase 2 (§6.1, sin GUI real):

- `PaginaFalsa` sustituye a `ft.Page` para coordinar `TimeTrackerApp`.
- Las `ft.View` se construyen headless con datos falsos (`Informe` sembrado
  con `reports/stats`) y su árbol se recorre con `tests/ui_util`.
- Los `BarChart` / `PieChart` de `flet-charts` son objetos Python normales
  (subclases de `ft.Control`): se construyen y se leen sin Flutter.

Cubre: portada → `/informes` (pila `[inicio, informes]`), las tres vistas
(barras por día, tarta por tarea, tabla + CSV), el aviso de intervalos en
curso, el placeholder "Sin datos", los snacks de rango inválido (en español,
sin traza) y el saneo de filtros sobre datos borrados.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import flet as ft
import pytest
from flet_charts import BarChart, PieChart

from core.models import Session, Task, TimeEntry
from reports import stats
from ui import logica
from ui.app import TimeTrackerApp, destino_csv
from ui.logica import FiltrosInforme
from ui.pages.informe import (
    _al_cambiar_valor,
    _etiqueta_marca,
    _id_de_clave,
    _marcas_eje,
    _primer_segmento,
    _valor_dropdown,
    construir_vista_informe,
)
from ui.pages.inicio import construir_vista_inicio
from tests.ui_util import (
    PaginaFalsa,
    al_pulsar,
    boton,
    controles,
    etiquetas_botones,
    iconos_con_tooltip,
    texto_snack,
    textos,
    snacks,
    valor,
)

UTC = timezone.utc
CABECERA_CSV = "Fecha;Tarea;Sesión;Inicio;Fin;Duración (s)"
CREADO = datetime(2026, 11, 1, tzinfo=UTC)

# Datos sembrados (reloj fijo): dos semanas ISO, 4 cerradas + 1 en curso.
D0 = date(2026, 11, 10)   # martes (semana del lunes 9-nov)
D1 = date(2026, 11, 19)   # jueves (semana del lunes 16-nov)
D2 = date(2026, 11, 20)   # viernes
AHORA = datetime.combine(D2, time(18, 0)).astimezone()

# Instantes locales del semillero (naive → aware: fecha local garantizada)
D0_11 = datetime.combine(D0, time(11, 0)).astimezone()
D1_10 = datetime.combine(D1, time(10, 0)).astimezone()
D1_12 = datetime.combine(D1, time(12, 0)).astimezone()
D2_09 = datetime.combine(D2, time(9, 0)).astimezone()
D2_15 = datetime.combine(D2, time(15, 0)).astimezone()

TAREAS = [Task(id=1, name="Correo", created_at=CREADO),
          Task(id=2, name="Reuniones", created_at=CREADO)]
SESIONES = [Session(id=1, name="Semana 48", created_at=CREADO)]

ENTRADAS = [
    TimeEntry(id=5, task_id=2, session_id=1,
              started_at=D0_11,
              ended_at=D0_11 + timedelta(minutes=30)),                    # 1800
    TimeEntry(id=1, task_id=1, session_id=1,
              started_at=D1_10, ended_at=D1_10 + timedelta(minutes=30)),  # 1800
    TimeEntry(id=2, task_id=2, session_id=1,
              started_at=D1_12, ended_at=D1_12 + timedelta(minutes=15)),  # 900
    TimeEntry(id=3, task_id=1, session_id=1,
              started_at=D2_09, ended_at=D2_09 + timedelta(hours=1)),     # 3600
    TimeEntry(id=4, task_id=2, session_id=1,
              started_at=D2_15),                                          # abierta
]
RANGO_TODO = stats.rango_preset("todo", AHORA)
INFORME = stats.informe(ENTRADAS, TAREAS, rango=RANGO_TODO, ahora=AHORA)
INFORME_VACIO = stats.informe([], TAREAS, rango=RANGO_TODO, ahora=AHORA)


def _local(d: date, hora: int = 10, minuto: int = 0) -> datetime:
    """Instante aware en la hora local del sistema para el día `d`."""
    return datetime.combine(d, time(hora, minuto)).astimezone()


# ------------------------------------------------------------------ helpers

def _vista(
    informe: stats.Informe = INFORME,
    *,
    filtros: FiltrosInforme | None = None,
    sesiones: list[Session] = SESIONES,
    tareas: list[Task] = TAREAS,
    llamadas: list | None = None,
) -> ft.View:
    """Vista de informes headless; los callbacks registran en `llamadas`."""
    llamadas = [] if llamadas is None else llamadas
    filtros = FiltrosInforme() if filtros is None else filtros
    return construir_vista_informe(
        informe,
        sesiones=sesiones,
        tareas=tareas,
        filtros=filtros,
        on_preset=lambda v: llamadas.append(("preset", v)),
        on_vista=lambda v: llamadas.append(("vista", v)),
        on_elegir_desde=lambda: llamadas.append(("desde",)),
        on_elegir_hasta=lambda: llamadas.append(("hasta",)),
        on_sesion=lambda v: llamadas.append(("sesion", v)),
        on_tarea=lambda v: llamadas.append(("tarea", v)),
        on_exportar=lambda: llamadas.append(("exportar",)),
        on_volver=lambda: llamadas.append(("volver",)),
    )


def _segmentado(vista, claves: set[str]) -> ft.SegmentedButton:
    """El SegmentedButton cuyos segmentos son exactamente esas claves."""
    for c in controles(vista):
        if isinstance(c, ft.SegmentedButton):
            segs = valor(c, "segments") or []
            if {valor(s, "value") for s in segs} == claves:
                return c
    raise AssertionError(f"Falta el SegmentedButton {sorted(claves)}")


def _dropdown(vista, etiqueta: str) -> ft.Dropdown:
    for c in controles(vista):
        if isinstance(c, ft.Dropdown) and valor(c, "label") == etiqueta:
            return c
    raise AssertionError(f"Falta el Dropdown {etiqueta!r}")


def _disparar(control, data, evento: str = "on_change") -> None:
    """Dispara el callback del control con un evento headless."""
    cb = getattr(control, evento, None)
    if cb is None:
        cb = control._values.get(evento)
    assert cb is not None, f"{control} no expone {evento}"
    cb(SimpleNamespace(data=data, control=control))


def _textos_fila(fila) -> list[str]:
    """Texto de cada celda de un `ft.DataRow`."""
    return [
        valor(valor(celda, "content"), "value")
        for celda in valor(fila, "cells")
    ]


def _barra(vista) -> BarChart:
    barras = [c for c in controles(vista) if isinstance(c, BarChart)]
    assert len(barras) == 1, f"se esperaba 1 BarChart, hay {len(barras)}"
    return barras[0]


def _tabla(vista) -> ft.DataTable:
    tablas = [c for c in controles(vista) if isinstance(c, ft.DataTable)]
    assert len(tablas) == 1, f"se esperaba 1 DataTable, hay {len(tablas)}"
    return tablas[0]


def _arrancar_en_informes(service) -> tuple[PaginaFalsa, TimeTrackerApp]:
    """App arrancada en la portada y navegada a `/informes` (pila de 2)."""
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app.arrancar()
    page.navigate(logica.RUTA_INFORMES)   # el fake no dispara route_change
    app._pintar(page.route)
    assert [v.route for v in page.views] == [
        logica.RUTA_INICIO, logica.RUTA_INFORMES
    ]
    return page, app


# ------------------------------------------------------------- portada → /informes

def test_boton_informes_de_la_portada_navega_y_apila_la_vista(service, clock):
    _sembrar_intervalo_cerrado(service, clock)   # datos para pintar barras
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app.arrancar()
    assert page.views[0].route == logica.RUTA_INICIO

    al_pulsar(boton(page.views[0], "Informes y estadísticas"))(None)

    assert page.navegaciones == [logica.RUTA_INFORMES]
    # el cliente Flet notificaría el cambio de ruta (el fake, no)
    app._al_cambiar_ruta(SimpleNamespace(route=page.route))
    assert [v.route for v in page.views] == [
        logica.RUTA_INICIO, logica.RUTA_INFORMES
    ]
    assert any(isinstance(c, BarChart) for c in controles(page.views[1]))


def test_volver_desde_informes_regresa_a_la_portada(service):
    page, app = _arrancar_en_informes(service)

    volver = next(
        c for c in controles(page.views[1])
        if isinstance(c, ft.IconButton) and valor(c, "tooltip") == "Volver al inicio"
    )
    al_pulsar(volver)(None)

    assert page.navegaciones[-1] == logica.RUTA_INICIO
    app._al_cambiar_ruta(SimpleNamespace(route=page.route))
    assert [v.route for v in page.views] == [logica.RUTA_INICIO]


def test_portada_sin_callback_no_ofrece_informes():
    vista = construir_vista_inicio(
        [], on_crear=lambda n: None, on_abrir=lambda i: None,
        on_eliminar=lambda i, n: None,
    )
    assert "Informes y estadísticas" not in etiquetas_botones(vista)


def test_boton_de_informes_dispara_su_callback():
    llamadas: list = []
    vista = construir_vista_inicio(
        [], on_crear=lambda n: None, on_abrir=lambda i: None,
        on_eliminar=lambda i, n: None,
        on_informes=lambda: llamadas.append("informes"),
    )
    al_pulsar(boton(vista, "Informes y estadísticas"))(None)
    assert llamadas == ["informes"]


# --------------------------------------------------------------- tres vistas

def test_vista_dia_pinta_barras_resumen_y_totales_por_semana():
    vista = _vista()

    # el semillero cuadra: 4 cerradas (8100 s) + 1 en curso excluida
    assert (INFORME.segundos, INFORME.intervalos, INFORME.excluidas) == (8100, 4, 1)

    b = _barra(vista)
    grupos = valor(b, "groups")
    assert len(grupos) == len(INFORME.por_dia) == 3
    assert [valor(valor(g, "rods")[0], "to_y") for g in grupos] == [
        1800, 2700, 3600
    ]
    tooltips = [valor(valor(g, "rods")[0], "tooltip") for g in grupos]
    assert tooltips == [
        "10 nov 2026 · 30 min",
        "19 nov 2026 · 45 min",
        "20 nov 2026 · 1 h",
    ]
    assert [valor(l, "label")
            for l in valor(valor(b, "bottom_axis"), "labels")] == [
        "10/11", "19/11", "20/11"
    ]
    assert [valor(l, "label")
            for l in valor(valor(b, "left_axis"), "labels")] == [
        "0", "15 min", "30 min", "45 min", "1 h"
    ]
    assert valor(valor(b, "horizontal_grid_lines"), "interval") == 900

    visibles = textos(vista)
    assert "Duración por día (hora local)" in visibles
    assert "Por semana" in visibles
    assert "Semana del 09 nov 2026" in visibles          # ISO lunes 9-nov
    assert "Semana del 16 nov 2026" in visibles
    assert "30 min · 1 intervalo" in visibles            # singular
    assert "1 h 45 min · 3 intervalos" in visibles
    assert "2 h 15 min" in visibles                      # resumen
    assert "4 intervalos" in visibles
    assert "02:15:00" in visibles
    assert "Todo el historial" in visibles
    assert valor(_segmentado(vista, {"dia", "tarea", "detalle"}),
                 "selected") == ["dia"]


def test_vista_tarea_pinta_tarta_y_leyenda_con_porcentajes():
    vista = _vista(filtros=FiltrosInforme(vista="tarea"))

    tartas = [c for c in controles(vista) if isinstance(c, PieChart)]
    assert len(tartas) == 1
    secciones = valor(tartas[0], "sections")
    assert [valor(s, "value") for s in secciones] == [5400, 2700]
    assert [valor(s, "title") for s in secciones] == ["67%", "33%"]

    visibles = textos(vista)
    assert "Reparto del tiempo por tarea" in visibles
    assert "Correo" in visibles and "Reuniones" in visibles
    assert "1 h 30 min · 67 %" in visibles
    assert "45 min · 33 %" in visibles


def test_vista_detalle_pinta_tabla_y_boton_csv():
    llamadas: list = []
    vista = _vista(filtros=FiltrosInforme(vista="detalle"), llamadas=llamadas)

    t = _tabla(vista)
    assert [
        valor(valor(col, "label"), "value") for col in valor(t, "columns")
    ] == ["Fecha", "Tarea", "Sesión", "Horario", "Duración"]
    filas = valor(t, "rows")
    assert len(filas) == 4            # las 4 cerradas, de más reciente a más antigua
    assert _textos_fila(filas[0]) == [
        "20 nov 2026", "Correo", "Semana 48", "09:00 - 10:00", "01:00:00"
    ]
    assert _textos_fila(filas[1]) == [
        "19 nov 2026", "Reuniones", "Semana 48", "12:00 - 12:15", "00:15:00"
    ]
    assert _textos_fila(filas[2]) == [
        "19 nov 2026", "Correo", "Semana 48", "10:00 - 10:30", "00:30:00"
    ]
    assert _textos_fila(filas[3]) == [
        "10 nov 2026", "Reuniones", "Semana 48", "11:00 - 11:30", "00:30:00"
    ]
    assert "Detalle: 4 intervalos" in textos(vista)

    assert "Exportar CSV" in etiquetas_botones(vista)
    al_pulsar(boton(vista, "Exportar CSV"))(None)
    assert llamadas == [("exportar",)]


def test_vista_detalle_identificadores_para_datos_huerfanos():
    """Entries de una sesión/tarea ya fuera del catálogo → `Tarea #99` /
    `Sesión #77` (defensivo, Fase 3)."""
    entrada = TimeEntry(task_id=99, session_id=77,
                        started_at=_local(D2, 9),
                        ended_at=_local(D2, 9, 30))
    inf = stats.informe([entrada], TAREAS, rango=RANGO_TODO, ahora=AHORA)
    vista = _vista(informe=inf, filtros=FiltrosInforme(vista="detalle"),
                   sesiones=[])

    assert _textos_fila(valor(_tabla(vista), "rows")[0])[1:3] == [
        "Tarea #99", "Sesión #77"
    ]


def test_sin_datos_muestra_placeholder_en_las_tres_vistas():
    for clave in logica.VISTAS_INFORME:
        vista = _vista(informe=INFORME_VACIO,
                       filtros=FiltrosInforme(vista=clave))
        visibles = textos(vista)
        assert "Sin datos para los filtros seleccionados." in visibles
        assert not any(
            isinstance(c, (BarChart, PieChart, ft.DataTable))
            for c in controles(vista)
        ), f"la vista {clave!r} pintó gráficos sin datos"
        assert "Exportar CSV" not in etiquetas_botones(vista)


def test_aviso_de_intervalos_en_curso_singular_y_plural():
    # singular (el semillero tiene UNA abierta)
    assert "1 intervalo en curso sin hora de fin: excluido del informe." in textos(
        _vista()
    )
    # plural: dos en curso
    dos = ENTRADAS + [TimeEntry(id=9, task_id=1, session_id=1,
                                started_at=_local(D2, 16))]
    inf = stats.informe(dos, TAREAS, rango=RANGO_TODO, ahora=AHORA)
    assert inf.excluidas == 2
    assert "2 intervalos en curso sin hora de fin: excluidos del informe." in textos(
        _vista(informe=inf)
    )


def test_sin_abiertas_no_se_muestra_el_aviso():
    cerradas = [e for e in ENTRADAS if e.ended_at is not None]
    inf = stats.informe(cerradas, TAREAS, rango=RANGO_TODO, ahora=AHORA)
    assert inf.excluidas == 0
    assert not any(
        "en curso sin hora de fin" in t for t in textos(_vista(informe=inf))
    )


def test_vista_tarea_con_cero_segundos_no_pinta_tarta():
    """Intervalos de 0 s: hay datos (la leyenda sale) pero la tarta, no."""
    cero = TimeEntry(task_id=1, session_id=1, started_at=_local(D1, 10),
                     ended_at=_local(D1, 10))
    inf = stats.informe([cero], TAREAS, rango=RANGO_TODO, ahora=AHORA)
    assert inf.intervalos == 1 and inf.segundos == 0

    vista = _vista(informe=inf, filtros=FiltrosInforme(vista="tarea"))
    assert not any(isinstance(c, PieChart) for c in controles(vista))
    visibles = textos(vista)
    assert "Correo" in visibles
    assert any("0 s · 0 %" in t for t in visibles)


def test_vista_dia_de_cero_segundos_sin_rejilla_del_eje():
    cero = TimeEntry(task_id=1, session_id=1, started_at=_local(D1, 10),
                     ended_at=_local(D1, 10))
    inf = stats.informe([cero], TAREAS, rango=RANGO_TODO, ahora=AHORA)

    b = _barra(_vista(informe=inf))
    assert valor(b, "horizontal_grid_lines") is None      # sin marcas → sin rejilla
    assert valor(valor(b, "left_axis"), "show_labels") is False


# ---------------------------------------------------------- etiquetas de rango

@pytest.mark.parametrize("clave,etiqueta", [
    ("hoy", "Hoy"),
    ("7d", "Últimos 7 días"),
    ("30d", "Últimos 30 días"),
    ("todo", "Todo el historial"),
])
def test_resumen_etiqueta_el_rango_activo(clave, etiqueta):
    rango = stats.rango_preset(clave, AHORA)
    inf = stats.informe(ENTRADAS, TAREAS, rango=rango, ahora=AHORA)
    vista = _vista(informe=inf, filtros=FiltrosInforme(preset=clave))
    assert etiqueta in textos(vista)


def test_rango_personalizado_muestra_fechas_y_botones_del_calendario():
    filtros = FiltrosInforme(preset="personalizado", desde=D1, hasta=D2)
    rango = stats.rango_fechas(D1, D2)
    inf = stats.informe(ENTRADAS, TAREAS, rango=rango, ahora=AHORA)
    llamadas: list = []
    vista = _vista(informe=inf, filtros=filtros, llamadas=llamadas)

    assert "19 nov 2026 - 20 nov 2026" in textos(vista)
    assert "Desde: 19 nov 2026" in etiquetas_botones(vista)
    assert "Hasta: 20 nov 2026" in etiquetas_botones(vista)
    assert valor(_segmentado(vista, {"hoy", "7d", "30d", "todo", "personalizado"}),
                 "selected") == ["personalizado"]

    # los botones abren los DatePicker (los maneja `ui/app`)
    al_pulsar(boton(vista, "Desde: 19 nov 2026"))(None)
    al_pulsar(boton(vista, "Hasta: 20 nov 2026"))(None)
    assert llamadas == [("desde",), ("hasta",)]


# ------------------------------------------------------- callbacks de la vista

def test_callbacks_de_preset_vista_y_filtros_desde_los_controles():
    llamadas: list = []
    vista = _vista(llamadas=llamadas)

    _disparar(_segmentado(vista, {"hoy", "7d", "30d", "todo", "personalizado"}),
              ["30d"])
    assert llamadas[-1] == ("preset", "30d")

    _disparar(_segmentado(vista, {"dia", "tarea", "detalle"}), ["detalle"])
    assert llamadas[-1] == ("vista", "detalle")

    dd_sesion = _dropdown(vista, "Sesión")
    assert [valor(o, "text") for o in valor(dd_sesion, "options")] == [
        "Todas las sesiones", "Semana 48"
    ]
    dd_sesion.value = "1"
    _disparar(dd_sesion, None, evento="on_select")
    assert llamadas[-1] == ("sesion", 1)
    dd_sesion.value = "todas"
    _disparar(dd_sesion, None, evento="on_select")
    assert llamadas[-1] == ("sesion", None)

    dd_tarea = _dropdown(vista, "Tarea")
    assert [valor(o, "text") for o in valor(dd_tarea, "options")] == [
        "Todas las tareas", "Correo", "Reuniones"
    ]
    dd_tarea.value = "2"
    _disparar(dd_tarea, None, evento="on_select")
    assert llamadas[-1] == ("tarea", 2)

    assert iconos_con_tooltip(vista) == ["Volver al inicio"]
    al_pulsar(next(c for c in controles(vista)
                   if isinstance(c, ft.IconButton)))(None)
    assert llamadas[-1] == ("volver",)


def test_eventos_de_segmento_malformados_no_disparan_callback():
    """`data` documentado; `selected` como respaldo; sin ninguno → no-op."""
    llamadas: list = []
    anadir = lambda v: llamadas.append(v)  # noqa: E731

    _al_cambiar_valor(SimpleNamespace(data=["7d"]), anadir)
    _al_cambiar_valor(SimpleNamespace(data=[], control=SimpleNamespace(selected=["hoy"])),
                      anadir)
    _al_cambiar_valor(SimpleNamespace(data=None, control=SimpleNamespace(selected=None)),
                      anadir)
    assert llamadas == ["7d", "hoy"]


def test_primer_segmento_y_valor_dropdown_como_respaldo():
    assert _valor_dropdown(
        SimpleNamespace(control=SimpleNamespace(value="3"))
    ) == "3"
    assert _valor_dropdown(
        SimpleNamespace(control=SimpleNamespace(value=None), data="4")
    ) == "4"
    assert _valor_dropdown(
        SimpleNamespace(control=SimpleNamespace(value=None), data=5)
    ) is None
    assert _valor_dropdown(SimpleNamespace()) is None

    assert _primer_segmento(SimpleNamespace(data=["a"])) == "a"
    assert _primer_segmento(
        SimpleNamespace(data=[], control=SimpleNamespace(selected=[7]))
    ) == "7"
    assert _primer_segmento(SimpleNamespace()) is None


def test_id_de_clave_de_los_dropdowns():
    assert _id_de_clave(None) is None
    assert _id_de_clave("todas") is None
    assert _id_de_clave("12") == 12
    assert _id_de_clave("abc") is None   # ValueError → None (nunca lanza)


def test_marcas_y_etiquetas_del_eje_y():
    assert _marcas_eje(0) == []
    assert _marcas_eje(3600) == [0, 900, 1800, 2700, 3600]
    # > 28 días de máximo → paso semanal (tope de la lista de pasos)
    grandes = _marcas_eje(10_000_000)
    assert grandes[:2] == [0, 7 * 24 * 3600]
    assert max(grandes) >= 10_000_000
    assert [_etiqueta_marca(s) for s in (0, 86400, 3 * 86400, 7200, 2700, 45)] == [
        "0", "1 d", "3 d", "2 h", "45 min", "45 s"
    ]


# ------------------------------------------------- handlers de `ui/app.py`

def test_cambiar_preset_valido_refresca_el_filtro(service):
    page, app = _arrancar_en_informes(service)
    antes = page.actualizaciones

    _disparar(_segmentado(page.views[1],
                          {"hoy", "7d", "30d", "todo", "personalizado"}), ["7d"])

    assert app._filtros.preset == "7d"
    assert page.actualizaciones > antes
    assert snacks(page) == []


def test_preset_personalizado_valido_guarda_el_filtro_y_repinta(service):
    page, app = _arrancar_en_informes(service)
    app._filtros.desde = date(2026, 11, 1)
    app._filtros.hasta = date(2026, 11, 30)

    _disparar(_segmentado(page.views[1],
                          {"hoy", "7d", "30d", "todo", "personalizado"}),
              ["personalizado"])

    assert app._filtros.preset == "personalizado"
    assert snacks(page) == []
    assert "01 nov 2026 - 30 nov 2026" in textos(page.views[1])


def test_preset_invalido_snack_espanol_sin_traza_y_filtro_inalterado(service):
    """Rango personalizado incoherente (desde > hasta): el filtro NO cambia."""
    page, app = _arrancar_en_informes(service)
    app._filtros.hasta = date(2026, 11, 10)
    app._filtros.desde = date(2026, 11, 20)
    antes = page.actualizaciones

    _disparar(_segmentado(page.views[1],
                          {"hoy", "7d", "30d", "todo", "personalizado"}),
              ["personalizado"])

    texto = texto_snack(page)
    assert "no puede ser posterior" in texto
    assert "Traceback" not in texto and "ValidationError" not in texto
    assert app._filtros.preset == "todo"
    assert page.actualizaciones == antes   # sin refresco: nada comprometido


def test_preset_desconocido_snack_espanol_sin_cambiar_nada(service):
    page, app = _arrancar_en_informes(service)

    _disparar(_segmentado(page.views[1],
                          {"hoy", "7d", "30d", "todo", "personalizado"}),
              ["semanas"])

    assert texto_snack(page) == "Rango desconocido: semanas"
    assert "Traceback" not in texto_snack(page)
    assert app._filtros.preset == "todo"


def test_cambiar_vista_refresca_e_ignora_claves_invalidas(service):
    page, app = _arrancar_en_informes(service)
    seg = _segmentado(page.views[1], {"dia", "tarea", "detalle"})
    antes = page.actualizaciones

    _disparar(seg, ["detalle"])
    assert app._filtros.vista == "detalle"
    assert page.actualizaciones > antes

    parado = page.actualizaciones
    _disparar(seg, ["inventada"])   # fuera de VISTAS_INFORME → se ignora
    assert app._filtros.vista == "detalle"
    assert page.actualizaciones == parado


def test_filtro_de_sesion_y_tarea_desde_los_dropdowns(service):
    sesion = service.crear_sesion("Semana 48")
    tarea = service.añadir_tarea("Correo")
    page, app = _arrancar_en_informes(service)
    antes = page.actualizaciones

    dd_sesion = _dropdown(page.views[1], "Sesión")
    dd_sesion.value = str(sesion.id)
    _disparar(dd_sesion, None, evento="on_select")
    assert app._filtros.sesion_id == sesion.id
    assert page.actualizaciones > antes

    dd_tarea = _dropdown(page.views[1], "Tarea")
    dd_tarea.value = str(tarea.id)
    _disparar(dd_tarea, None, evento="on_select")
    assert app._filtros.tarea_id == tarea.id

    dd_todas = _dropdown(page.views[1], "Sesión")
    dd_todas.value = "todas"
    _disparar(dd_todas, None, evento="on_select")
    assert app._filtros.sesion_id is None


def test_filtros_que_apuntan_a_datos_borrados_se_sanean(service):
    sesion = service.crear_sesion("Semana 48")
    tarea = service.añadir_tarea("Correo")
    page, app = _arrancar_en_informes(service)

    app._filtros.sesion_id = sesion.id + 1000   # borrados "mientras tanto"
    app._filtros.tarea_id = tarea.id + 1000
    app._refrescar()
    assert app._filtros.sesion_id is None
    assert app._filtros.tarea_id is None

    app._filtros.sesion_id = sesion.id          # el válido NO se sanea
    app._refrescar()
    assert app._filtros.sesion_id == sesion.id


# ------------------------------------------------------------ DatePicker

def test_elegir_fecha_desde_valida_actualiza_y_cierra_el_picker(service):
    page, app = _arrancar_en_informes(service)
    app._filtros.hasta = date(2026, 11, 30)
    app._elegir_fecha("desde")
    picker = page.dialogos[-1]
    assert isinstance(picker, ft.DatePicker)
    assert picker.open is True
    antes = page.actualizaciones

    picker.value = datetime.combine(date(2026, 11, 10), time.min).astimezone()
    _disparar(picker, None)

    assert app._filtros.desde == date(2026, 11, 10)
    assert app._filtros.preset == "personalizado"
    assert page.dialogos == []            # se cierra al confirmar
    assert page.actualizaciones > antes
    assert snacks(page) == []


def test_elegir_fecha_hasta_valida_actualiza_hasta(service):
    page, app = _arrancar_en_informes(service)
    app._filtros.desde = date(2026, 11, 1)
    app._elegir_fecha("hasta")
    picker = page.dialogos[-1]

    picker.value = datetime.combine(date(2026, 11, 25), time.min).astimezone()
    _disparar(picker, None)

    assert app._filtros.hasta == date(2026, 11, 25)
    assert app._filtros.preset == "personalizado"
    assert page.dialogos == []


def test_elegir_fecha_invalida_snack_sin_traza_sin_cerrar_ni_cambiar(service):
    page, app = _arrancar_en_informes(service)
    app._filtros.hasta = date(2026, 11, 10)
    app._filtros.desde = date(2026, 11, 1)   # válido: no debe tocarse
    app._elegir_fecha("desde")
    picker = page.dialogos[-1]
    antes = page.actualizaciones

    picker.value = datetime.combine(date(2026, 11, 20), time.min).astimezone()
    _disparar(picker, None)

    texto = texto_snack(page)
    assert "no puede ser posterior" in texto
    assert "Traceback" not in texto
    assert app._filtros.desde == date(2026, 11, 1)
    assert app._filtros.preset == "todo"
    # el picker NO se cierra (sigue ahí para corregir; el snack va detrás)
    assert page.dialogos[0] is picker
    assert page.actualizaciones == antes


def test_elegir_fecha_sin_valor_no_hace_nada(service):
    page, app = _arrancar_en_informes(service)
    app._elegir_fecha("desde")
    picker = page.dialogos[-1]
    antes_desde = app._filtros.desde

    picker.value = None
    _disparar(picker, None)

    assert app._filtros.desde == antes_desde
    assert app._filtros.preset == "todo"
    assert page.dialogos == [picker]
    assert snacks(page) == []


def test_elegir_fecha_con_picker_ya_cerrado_no_popea_de_mas(service):
    """Si el cliente ya cerró el diálogo (`open=False`), no se poppea."""
    page, app = _arrancar_en_informes(service)
    app._filtros.hasta = date(2026, 11, 30)
    app._elegir_fecha("desde")
    picker = page.dialogos[-1]
    picker.open = False

    picker.value = datetime.combine(date(2026, 11, 10), time.min).astimezone()
    _disparar(picker, None)

    assert app._filtros.desde == date(2026, 11, 10)
    assert app._filtros.preset == "personalizado"
    assert page.dialogos == [picker]   # sin pop: el cliente ya lo cerró


# ------------------------------------------------------------ exportar CSV

def _sembrar_intervalo_cerrado(service, clock, segundos: int = 1800):
    service.crear_sesion("Semana 48")
    tarea = service.añadir_tarea("Correo")
    service.iniciar_tarea(tarea.id)
    clock.advance(segundos)
    service.detener_tarea()


def test_exportar_sin_datos_snack_y_no_escribe_nada(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)         # cwd = tmp_path (nada fuera de aquí)
    monkeypatch.setattr("ui.app.destino_csv", lambda: tmp_path)  # defensa
    page, app = _arrancar_en_informes(service)

    app._informe_exportar()

    assert texto_snack(page) == "No hay datos que exportar."
    assert list(tmp_path.glob("informe_*.csv")) == []


def test_exportar_con_datos_escribe_csv_con_bom_utf8(service, clock,
                                                     tmp_path, monkeypatch):
    _sembrar_intervalo_cerrado(service, clock)
    monkeypatch.chdir(tmp_path)
    # Fase 4: el CSV va a `~/Documents`; lo redirigimos a tmp_path para que ni
    # el snack ni el fichero toquen el home real del usuario.
    monkeypatch.setattr("ui.app.destino_csv", lambda: tmp_path)
    page, app = _arrancar_en_informes(service)

    app._informe_exportar()

    assert texto_snack(page).startswith("CSV guardado en")
    assert str(tmp_path) in texto_snack(page)
    ficheros = list(tmp_path.glob("informe_*.csv"))
    assert len(ficheros) == 1

    crudo = ficheros[0].read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")   # BOM UTF-8 para Excel
    lineas = crudo.decode("utf-8-sig").splitlines()
    assert lineas[0] == CABECERA_CSV
    assert lineas[1].split(";")[1:3] == ["Correo", "Semana 48"]
    assert lineas[1].split(";")[-1] == "1800"


def test_exportar_con_error_de_disco_snack_generico_sin_traza(service, clock,
                                                              tmp_path, monkeypatch):
    _sembrar_intervalo_cerrado(service, clock)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ui.app.destino_csv", lambda: tmp_path)  # sin tocar ~/Documents

    def disco_lleno(self, *args, **kwargs):
        raise OSError("Disco lleno: acceso denegado")

    monkeypatch.setattr(Path, "write_text", disco_lleno)
    page, app = _arrancar_en_informes(service)

    app._informe_exportar()

    texto = texto_snack(page)
    assert texto == "Ha ocurrido un error inesperado. Inténtalo de nuevo."
    for prohibido in ("Traceback", "OSError", "Disco", "Path"):
        assert prohibido not in texto
    assert list(tmp_path.glob("informe_*.csv")) == []


def test_destino_csv_crea_documents_y_de_fallback_a_cwd_si_falla(tmp_path,
                                                                 monkeypatch):
    """Fase 4: `~/Documents` si se puede crear; si `mkdir` lanza `OSError` → cwd.

    Fase 1 (rama feliz): `Path.home()` = tmp_path → se crea `tmp_path/Documents`
    y se devuelve (sin tocar el home real del usuario).

    Fase 2 (rama `except OSError`): `Path.home()` apunta a un FICHERO, así que
    `Documents/` nunca podrá crearse bajo él y `mkdir` lanza un `OSError` real
    (en Windows `FileNotFoundError`, en POSIX `NotADirectoryError`) → fallback
    al directorio de trabajo, sin traza.
    """
    monkeypatch.chdir(tmp_path)               # cwd = tmp_path

    # rama feliz: Documents se crea bajo un "home" válido
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    destino_ok = destino_csv()                # no debe lanzar
    assert destino_ok == tmp_path / "Documents"
    assert destino_ok.is_dir()

    # rama de fallo: el "home" es un fichero → mkdir lanza OSError → cwd
    bloqueador = tmp_path / "no_es_un_directorio.txt"
    bloqueador.write_text("x")
    monkeypatch.setattr(Path, "home", lambda: bloqueador)

    destino = destino_csv()                   # no debe lanzar (sin traza)

    assert destino == Path.cwd() == tmp_path  # fallback al directorio de trabajo
    assert not (bloqueador / "Documents").exists()  # nada creado donde no toca
