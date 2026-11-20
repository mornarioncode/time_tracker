"""Tests de las vistas Flet (`ui.pages`) construidas SIN GUI real.

Los controles Flet son objetos Python: aquí se construyen las `ft.View` con
callbacks falsos y se recorre su árbol de controles (`tests/ui_util`).

Test clave de la fase (§6.1, "solo lectura en dos capas"): la vista de una
sesión **cerrada no contiene NINGÚN control de escritura** (añadir, iniciar,
detener, terminar); la de una sesión **abierta sí**. Nada de ventanas ni
Flutter en estos tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import flet as ft

from core.models import Session, Task, TimeEntry
from ui import format as fmt
from ui.logica import ResumenSesion
from ui.pages.inicio import construir_vista_inicio
from ui.pages.sesion import construir_vista_sesion
from tests.ui_util import (
    al_pulsar,
    boton,
    campos_texto,
    controles,
    etiquetas_botones,
    iconos_con_tooltip,
    textos,
    valor,
)

UTC = timezone.utc
T0 = datetime(2026, 11, 19, 9, 0, 0, tzinfo=UTC)


def _no_op(*_args, **_kwargs) -> None:
    """Callback falso por defecto (smoke: solo importa que se pueda invocar)."""
    return None


# ------------------------------------------------------------------ portada

def test_vista_inicio_sin_sesiones():
    llamadas = {"crear": [], "abrir": [], "eliminar": []}
    vista = construir_vista_inicio(
        [],
        on_crear=lambda n: llamadas["crear"].append(n),
        on_abrir=lambda i: llamadas["abrir"].append(i),
        on_eliminar=lambda i, n: llamadas["eliminar"].append((i, n)),
    )

    assert vista.route == "/"
    assert any("Aún no hay sesiones" in t for t in textos(vista))
    assert "Crear y empezar" in etiquetas_botones(vista)
    assert "Continuar sesión" not in etiquetas_botones(vista)  # no hay abierta
    assert not any(isinstance(c, ft.ListTile) for c in controles(vista))
    assert llamadas == {"crear": [], "abrir": [], "eliminar": []}


def test_vista_inicio_lista_sesiones_abierta_y_cerrada():
    resumenes = [
        ResumenSesion(
            id=1, nombre="Semana 48", fecha="19 nov 2026", estado="Abierta",
            duracion="5 min", intervalos=1, abierta=True,
        ),
        ResumenSesion(
            id=2, nombre="Semana 47", fecha="12 nov 2026", estado="Cerrada",
            duracion="1 h 23 min", intervalos=3, abierta=False,
        ),
    ]
    vista = construir_vista_inicio(
        resumenes, on_crear=_no_op, on_abrir=_no_op, on_eliminar=_no_op
    )

    visibles = textos(vista)
    assert "Semana 48" in visibles and "Semana 47" in visibles
    assert "Abierta" in visibles and "Cerrada" in visibles
    assert "19 nov 2026 · 5 min · 1 intervalo" in visibles
    assert any("1 h 23 min" in t and "3 intervalos" in t for t in visibles)

    # Aviso de sesión en curso + acción Continuar (solo la abierta)
    assert "Sesión en curso" in visibles
    assert "Continuar sesión" in etiquetas_botones(vista)

    # Papelera en cada fila (la confirmación modal la dispara el handler)
    assert iconos_con_tooltip(vista).count("Eliminar sesión") == 2
    assert sum(1 for c in controles(vista) if isinstance(c, ft.ListTile)) == 2


def test_vista_inicio_callbacks_disparan_con_los_datos_correctos():
    resumenes = [
        ResumenSesion(
            id=1, nombre="Abierta", fecha="19 nov 2026", estado="Abierta",
            duracion="0 s", intervalos=0, abierta=True,
        ),
        ResumenSesion(
            id=2, nombre="Cerrada", fecha="12 nov 2026", estado="Cerrada",
            duracion="1 h 23 min", intervalos=3, abierta=False,
        ),
    ]
    llamadas: list = []
    vista = construir_vista_inicio(
        resumenes,
        on_crear=lambda n: llamadas.append(("crear", n)),
        on_abrir=lambda i: llamadas.append(("abrir", i)),
        on_eliminar=lambda i, n: llamadas.append(("eliminar", i, n)),
    )

    # formulario: escribir nombre y pulsar "Crear y empezar"
    campo = campos_texto(vista)[0]
    campo.value = "Nueva sesión"
    al_pulsar(boton(vista, "Crear y empezar"))(None)
    assert llamadas[-1] == ("crear", "Nueva sesión")

    # la fila entera abre la sesión (la cerrada también: historial)
    filas = [c for c in controles(vista) if isinstance(c, ft.ListTile)]
    al_pulsar(filas[0])(None)
    assert llamadas[-1] == ("abrir", 1)
    al_pulsar(filas[1])(None)
    assert llamadas[-1] == ("abrir", 2)

    # papelera → on_eliminar(id, nombre) para el diálogo de confirmación
    papeleras = [
        c for c in controles(vista)
        if isinstance(c, ft.IconButton) and c.tooltip == "Eliminar sesión"
    ]
    al_pulsar(papeleras[1])(None)
    assert llamadas[-1] == ("eliminar", 2, "Cerrada")


# ------------------------------------------------------------ vista de sesión

def _datos_sesion(*, abierta: bool, entrada=None, intervalos=None, tareas=None):
    """(sesión, kwargs) para `construir_vista_sesion` con callbacks falsos."""
    sesion = Session(
        id=1,
        name="Semana 48",
        created_at=T0,
        ended_at=None if abierta else T0 + timedelta(hours=1),
    )
    kwargs = dict(
        tareas=tareas if tareas is not None else [],
        intervalos=intervalos or [],
        entrada=entrada,
        ahora=T0 + timedelta(seconds=30),
        lbl_crono=ft.Text("00:00:30", size=44),
        on_anadir_tarea=_no_op,
        on_iniciar_tarea=_no_op,
        on_detener=_no_op,
        on_terminar_sesion=_no_op,
        on_volver=_no_op,
    )
    return sesion, kwargs


def test_vista_sesion_abierta_tiene_controles_de_escritura():
    tarea = Task(id=5, name="Correo", created_at=T0)
    sesion, kwargs = _datos_sesion(abierta=True, tareas=[tarea])

    llamadas: list = []
    vista = construir_vista_sesion(
        sesion,
        **{**kwargs, "on_iniciar_tarea": lambda tid: llamadas.append(tid)},
    )
    assert vista.route == "/sesion/1"

    # escribir: campo "Nueva tarea" + botón Añadir (catálogo global)
    campos = campos_texto(vista)
    assert len(campos) == 1
    assert valor(campos[0], "label") == "Nueva tarea"

    etiquetas = etiquetas_botones(vista)
    assert "Añadir" in etiquetas
    assert "Terminar sesión" in etiquetas
    assert "Detener" not in etiquetas  # sin entry en curso: aún no

    # pulsar la tarea la inicia (callback con su id)
    filas = [
        c for c in controles(vista)
        if isinstance(c, ft.ListTile) and c.title.value == "Correo"
    ]
    assert len(filas) == 1
    assert filas[0].on_click is not None
    al_pulsar(filas[0])(None)
    assert llamadas == [5]

    # botón de play de la fila (iniciar sin clicar la fila entera)
    play = [
        c for c in controles(vista)
        if isinstance(c, ft.IconButton) and c.tooltip == "Iniciar 'Correo'"
    ]
    assert len(play) == 1, "falta el botón de iniciar de la fila"
    al_pulsar(play[0])(None)
    assert llamadas == [5, 5]


def test_vista_sesion_abierta_con_entry_muestra_detener_y_corriendo():
    tarea = Task(id=5, name="Correo", created_at=T0)
    entry = TimeEntry(id=9, task_id=5, session_id=1, started_at=T0)
    sesion, kwargs = _datos_sesion(
        abierta=True, tareas=[tarea], entrada=entry, intervalos=[entry]
    )
    vista = construir_vista_sesion(sesion, **kwargs)

    etiquetas = etiquetas_botones(vista)
    assert "Detener" in etiquetas            # hay tarea corriendo
    assert "Terminar sesión" in etiquetas
    assert "Añadir" in etiquetas

    visibles = textos(vista)
    assert any(t.startswith("Corriendo: Correo") for t in visibles)
    # duración del intervalo en curso y rango "09:00 - en curso"
    assert "00:00:30" in visibles
    assert any(t.endswith(" - en curso") for t in visibles)
    # el control vivo del cronómetro que trae app.py está colocado
    assert any(isinstance(c, ft.Text) and c.size == 44 for c in controles(vista))


def test_vista_sesion_cerrada_no_tiene_ningun_control_de_escritura():
    """§6.1 — LA regla clave: sesión cerrada = historial de solo lectura.
    Ni Añadir, ni Iniciar, ni Detener, ni Terminar sesión en toda la vista."""
    tareas = [
        Task(id=5, name="Correo", created_at=T0),
        Task(id=6, name="Reuniones", created_at=T0),
    ]
    intervalo = TimeEntry(
        id=9, task_id=5, session_id=1,
        started_at=T0, ended_at=T0 + timedelta(minutes=1),
    )
    sesion, kwargs = _datos_sesion(
        abierta=False, tareas=tareas, intervalos=[intervalo]
    )
    vista = construir_vista_sesion(sesion, **kwargs)
    todos = controles(vista)

    # aviso de solo lectura visible
    assert any("historial de solo lectura" in t for t in textos(vista))

    # NI UN SOLO control de escritura
    assert not any(
        isinstance(c, (ft.FilledButton, ft.OutlinedButton, ft.TextButton))
        for c in todos
    ), "una sesión cerrada no puede exponer ningún botón de acción"
    assert campos_texto(vista) == [], "sin campo para añadir tareas"

    # las tareas se listan pero NO son pulsables (sin on_click ni play):
    # se distinguen de los intervalos porque llevan `leading` (icono de tarea)
    filas_tareas = [
        c for c in todos
        if isinstance(c, ft.ListTile)
        and c.title.value in ("Correo", "Reuniones")
        and c._values.get("leading") is not None
    ]
    assert len(filas_tareas) == 2
    for fila in filas_tareas:
        assert fila.on_click is None
        assert fila._values.get("trailing") is None

    # la navegación (volver al inicio) SÍ sigue permitida
    assert iconos_con_tooltip(vista) == ["Volver al inicio"]

    # los intervalos siguen pintándose (historial consultable)
    visibles = textos(vista)
    assert "Correo" in visibles
    assert "00:01:00" in visibles
    assert fmt.rango_horas(intervalo.started_at, intervalo.ended_at) in visibles
    assert "Detenida" in visibles  # estado sin entry en curso


def test_vista_sesion_abierta_sin_entry_no_ofrece_detener():
    tarea = Task(id=5, name="Correo", created_at=T0)
    sesion, kwargs = _datos_sesion(abierta=True, tareas=[tarea])
    vista = construir_vista_sesion(sesion, **kwargs)
    assert "Detener" not in etiquetas_botones(vista)
    assert "Sin tarea en curso" in textos(vista)


def test_vista_sesion_sin_tareas_ni_intervalos_muestra_placeholders():
    sesion, kwargs = _datos_sesion(abierta=True)
    vista = construir_vista_sesion(sesion, **kwargs)
    visibles = textos(vista)
    assert any("El catálogo está vacío" in t for t in visibles)
    assert any("Sin intervalos todavía" in t for t in visibles)


def test_vista_sesion_varios_intervalos_separados_con_dividers():
    tareas = [Task(id=5, name="Correo", created_at=T0)]
    intervalos = [
        TimeEntry(
            id=1, task_id=5, session_id=1,
            started_at=T0, ended_at=T0 + timedelta(minutes=1),
        ),
        TimeEntry(
            id=2, task_id=5, session_id=1,
            started_at=T0 + timedelta(minutes=2),
            ended_at=T0 + timedelta(minutes=4),
        ),
    ]
    sesion, kwargs = _datos_sesion(
        abierta=True, tareas=tareas, intervalos=intervalos
    )
    vista = construir_vista_sesion(sesion, **kwargs)

    visibles = textos(vista)
    assert "00:01:00" in visibles
    assert "00:02:00" in visibles
    # las filas de intervalo van separadas por un Divider
    assert sum(1 for c in controles(vista) if isinstance(c, ft.Divider)) >= 1
