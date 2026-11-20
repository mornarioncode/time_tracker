"""Tests de coordinación de `ui/app.py` (TimeTrackerApp) con página simulada.

Sin GUI real: `PaginaFalsa` sustituye a `ft.Page` (navegación, pila de vistas,
diálogos) y el servicio es el real sobre SQLite en `tmp_path` con reloj
inyectado. Cubre arranque (tema §6.1), navegación por rutas, confirmaciones
de "Terminar"/"Eliminar" y que **jamás** se pinte una traza o SQL en un
SnackBar.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import flet as ft

from core.exceptions import StorageError
from core.models import utc_now
from ui.app import TimeTrackerApp
from tests.ui_util import (
    PaginaFalsa,
    al_pulsar,
    boton,
    controles,
    dialogos_modales,
    texto_dialogo,
    texto_snack,
)

ISO = "2026-11-18T09:00:00Z"   # timestamp en texto ISO 'Z' (formato de la BD)


# --------------------------------------------------------------- arranque

def test_arrancar_configura_tema_system_y_geometria(service):
    """§6.1: `ThemeMode.SYSTEM` y ventana 1120×800 (mín. 800×600)."""
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app.arrancar()

    assert page.title == "Time Tracker"
    assert page.theme_mode == ft.ThemeMode.SYSTEM
    assert page.window.width == 1120
    assert page.window.height == 800
    assert page.window.min_width == 800
    assert page.window.min_height == 600
    assert page.on_route_change is not None
    assert page.on_view_pop is not None
    # primer pintado de la portada + cronómetro lanzado (y descartado en test)
    assert [v.route for v in page.views] == ["/"]


def test_arrancar_recupera_la_sesion_abierta(service):
    anterior = service.crear_sesion("A")   # se cierra sola al crear B
    service.crear_sesion("B")             # única abierta
    service.seleccionar_sesion(anterior.id)  # estado "sucio": actual = A (cerrada)
    abierta = next(s for s in service.listar_sesiones() if s.is_open)

    app = TimeTrackerApp(PaginaFalsa(), service)
    app.arrancar()

    assert service.sesion_actual.id == abierta.id
    assert service.sesion_actual.name == "B"


# ------------------------------------------------------------- navegación

def test_pintar_sesion_pila_con_atras(service):
    """§6.1: pila `[inicio, sesión]` para el "atrás" nativo de Flet."""
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    sesion = service.crear_sesion("A")

    app._pintar(f"/sesion/{sesion.id}")

    assert [v.route for v in page.views] == ["/", f"/sesion/{sesion.id}"]
    assert page.actualizaciones >= 1

    # el botón "Volver al inicio" de la vista llama al handler del app
    vista_sesion = page.views[1]
    volver = next(
        c for c in controles(vista_sesion)
        if isinstance(c, ft.IconButton) and c.tooltip == "Volver al inicio"
    )
    al_pulsar(volver)(None)
    assert page.navegaciones == ["/"]


def test_pintar_sesion_inexistente_vuelve_al_inicio(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)

    app._pintar("/sesion/999999")

    assert page.navegaciones == ["/"]
    assert page.views == []   # abortó antes de pintar: no se apila nada


def test_al_cambiar_ruta_pinta_la_ruta_del_evento(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    sesion = service.crear_sesion("A")

    app._al_cambiar_ruta(SimpleNamespace(route=f"/sesion/{sesion.id}"))

    assert [v.route for v in page.views] == ["/", f"/sesion/{sesion.id}"]


def test_al_cerrar_vista_atras_reconstruye_la_anterior(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    sesion = service.crear_sesion("A")
    # Flet ya habría actualizado page.route antes del evento de navegación
    page.route = f"/sesion/{sesion.id}"
    app._pintar(page.route)
    vista_sesion = page.views[1]

    asyncio.run(app._al_cerrar_vista(SimpleNamespace(view=vista_sesion)))

    assert page.navegaciones == ["/"]      # push_route al inicio
    assert page.route == "/"
    assert [v.route for v in page.views] == ["/"]


def test_al_cerrar_vista_con_solo_la_portada_repinta_a_mano(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app._pintar()                          # pila = [portada]
    vista_portada = page.views[0]
    antes = page.actualizaciones

    asyncio.run(app._al_cerrar_vista(SimpleNamespace(view=vista_portada)))

    assert page.actualizaciones > antes    # misma ruta: repintado manual
    assert [v.route for v in page.views] == ["/"]


# ------------------------------------------------------------ crear/abrir

def test_crear_sesion_navega_a_su_vista(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)

    app._crear_sesion("Nueva sesión")

    nueva = service.listar_sesiones()[0]
    assert nueva.name == "Nueva sesión"
    assert page.navegaciones == [f"/sesion/{nueva.id}"]

    # el fake no dispara route_change: pintamos a mano y debe apilarse
    app._pintar(page.route)
    assert [v.route for v in page.views] == ["/", f"/sesion/{nueva.id}"]


def test_crear_sesion_invalida_muestra_snack_espanol_sin_navegar(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)

    app._crear_sesion("   ")

    assert service.listar_sesiones() == []
    assert page.navegaciones == []
    texto = texto_snack(page)
    assert "no puede estar vacío" in texto   # error de dominio, en español
    assert "Traceback" not in texto


def test_abrir_sesion_inexistente_muestra_error_de_dominio(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)

    app._abrir_sesion(999_999)

    assert page.navegaciones == []
    assert "No existe la sesión" in texto_snack(page)


# -------------------------------------------------------- terminar sesión

def test_terminar_sesion_sin_tarea_cierra_directo_sin_dialogo(service):
    """§6.1: confirmación SOLO si hay tarea cronometrada."""
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    app = TimeTrackerApp(page, service)
    app._pintar()

    app._terminar_sesion(sesion.id)

    assert dialogos_modales(page) == []           # sin confirmación
    assert not service.seleccionar_sesion(sesion.id).is_open
    assert "Sesión terminada" in texto_snack(page)


def test_terminar_sesion_con_tarea_pide_confirmacion(service):
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    tarea = service.añadir_tarea("Correo")
    service.iniciar_tarea(tarea.id)
    app = TimeTrackerApp(page, service)
    app._pintar()

    app._terminar_sesion(sesion.id)

    dlg = dialogos_modales(page)[-1]
    titulo, cuerpo = texto_dialogo(dlg)
    assert titulo == "Terminar sesión"
    assert "Correo" in cuerpo and "en curso" in cuerpo
    assert service.seleccionar_sesion(sesion.id).is_open  # aún NO cerrada

    # Cancelar → se cierra el diálogo y no cambia nada
    al_pulsar(boton(dlg, "Cancelar"))(None)
    assert page.dialogos == []
    assert service.seleccionar_sesion(sesion.id).is_open

    # Aceptar → cierra entry + sesión y confirma con snack
    app._terminar_sesion(sesion.id)
    dlg2 = dialogos_modales(page)[-1]
    al_pulsar(boton(dlg2, "Terminar"))(None)
    assert not service.seleccionar_sesion(sesion.id).is_open
    assert service.entry_abierta() is None
    assert "Sesión terminada" in texto_snack(page)


# -------------------------------------------------------- eliminar sesión

def test_eliminar_sesion_pide_confirmacion_y_el_catalogo_sobrevive(service):
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    service.añadir_tarea("Uno")
    service.añadir_tarea("Dos")
    app = TimeTrackerApp(page, service)
    app._pintar()

    app._eliminar_sesion(sesion.id, "A")

    dlg = dialogos_modales(page)[-1]
    titulo, cuerpo = texto_dialogo(dlg)
    assert titulo == "Eliminar sesión"
    assert "catálogo global se conservan" in cuerpo   # §6.1: aviso obligatorio
    assert len(service.listar_sesiones()) == 1        # aún no eliminada

    al_pulsar(boton(dlg, "Eliminar"))(None)

    assert service.listar_sesiones() == []
    assert len(service.listar_tareas()) == 2          # catálogo SOBREVIVE
    assert "eliminada" in texto_snack(page)


# ------------------------------------------- feedback de errores (sin refresco)

def test_anadir_tarea_duplicada_snack_y_no_refresca(service):
    """§6.1: sin refresco tras un error → el campo conserva lo escrito."""
    page = PaginaFalsa()
    service.añadir_tarea("Correo")
    app = TimeTrackerApp(page, service)
    app._pintar()
    antes = page.actualizaciones

    app._anadir_tarea("Correo")

    assert texto_snack(page) == "Ya existe la tarea 'Correo' en el catálogo"
    assert page.actualizaciones == antes  # NO se repinta nada


def test_storage_error_en_snack_es_generico_sin_sql(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)

    app._mostrar_error(
        StorageError(
            "Error de SQLite al ejecutar 'INSERT INTO tasks (name) "
            "VALUES (NULL)': NOT NULL constraint failed"
        )
    )

    texto = texto_snack(page)
    assert texto == "No se pudieron guardar los datos. Inténtalo de nuevo."
    for prohibido in ("SQLite", "INSERT", "NOT NULL", "Traceback"):
        assert prohibido not in texto


# --------------------------------------------------------------- cronómetro

def test_tick_cronometro_sin_entry_no_hace_nada(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    assert app._lbl_crono is None
    app._tick_cronometro()   # no-op sin control vivo (no lanza)
    assert app._lbl_crono is None


def test_tick_cronometro_recalcula_desde_started_at(service):
    """§6.1: el tick recalcula desde el `started_at` real de la entry."""
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app._lbl_crono = ft.Text("00:00:00")
    app._crono_inicio = utc_now() - timedelta(seconds=42)

    app._tick_cronometro()

    partes = app._lbl_crono.value.split(":")
    segundos = int(partes[0]) * 3600 + int(partes[1]) * 60 + int(partes[2])
    assert partes[0] == "00"            # menos de una hora en el test
    assert 42 <= segundos <= 120        # >= lo transcurrido desde started_at


def test_bucle_cronometro_lat_y_se_detiene(service):
    """Bucle de 1 s (`page.run_task` en el arranque): corre y se cancela
    limpio; tras ~1 s el tick ha actualizado el label."""
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app._lbl_crono = ft.Text("00:00:00")
    app._crono_inicio = utc_now() - timedelta(seconds=1)

    async def probar():
        tarea = asyncio.create_task(app._bucle_cronometro())
        await asyncio.sleep(1.05)        # deja pasar UN tick
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("el bucle del cronómetro debía cancelarse")

    asyncio.run(probar())

    assert app._lbl_crono.value != "00:00:00"   # el tick latió al menos una vez


# ------------------------------------------- handlers: éxito y error (§6.1)

def test_pintar_sesion_con_entry_en_curso_coloca_cronometro_verde(service):
    """El snapshot de sesión con entry en curso crea el control vivo verde
    (lo que después actualiza el tick de 1 s)."""
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    sesion = service.crear_sesion("A")
    tarea = service.añadir_tarea("Correo")
    service.iniciar_tarea(tarea.id)
    entry = service.entry_abierta()

    page.route = f"/sesion/{sesion.id}"
    antes = utc_now()
    app._pintar(page.route)
    despues = utc_now()

    lbl = app._lbl_crono
    assert lbl is not None
    assert lbl.color == ft.Colors.GREEN
    assert app._crono_inicio == entry.started_at
    partes = lbl.value.split(":")
    segundos = int(partes[0]) * 3600 + int(partes[1]) * 60 + int(partes[2])
    # acotado por el reloj real entre las dos llamadas a utc_now()
    assert _segundos(entry.started_at, antes) <= segundos <= _segundos(
        entry.started_at, despues
    )


def test_abrir_sesion_existente_navega_y_selecciona(service):
    page = PaginaFalsa()
    service.crear_sesion("A")          # se cierra sola al crear B
    b = service.crear_sesion("B")      # actual = B
    a = next(s for s in service.listar_sesiones() if s.name == "A")
    app = TimeTrackerApp(page, service)

    app._abrir_sesion(a.id)

    assert service.sesion_actual.id == a.id
    assert page.navegaciones == [f"/sesion/{a.id}"]
    assert b.is_open                   # abrir no toca a nadie: solo selecciona


def test_confirmar_eliminar_con_sesion_ya_borrada_muestra_snack(service, db):
    """La confirmación puede llegar tarde (sesión borrada fuera): snack de
    dominio, sin traza y sin refresco."""
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    app = TimeTrackerApp(page, service)
    app._pintar()
    app._eliminar_sesion(sesion.id, "A")
    dlg = dialogos_modales(page)[-1]
    antes = page.actualizaciones

    db.execute("DELETE FROM sessions WHERE id = ?", (sesion.id,))  # borrado externo
    al_pulsar(boton(dlg, "Eliminar"))(None)

    texto = texto_snack(page)
    assert "No existe la sesión" in texto
    assert "Traceback" not in texto
    assert page.actualizaciones == antes   # el error no refresca


def test_anadir_tarea_valida_refresca_la_vista(service):
    page = PaginaFalsa()
    app = TimeTrackerApp(page, service)
    app._pintar()
    antes = page.actualizaciones

    app._anadir_tarea("Correo")

    assert [t.name for t in service.listar_tareas()] == ["Correo"]
    assert page.actualizaciones > antes   # éxito → relee y repinta


def test_iniciar_tarea_desde_handler_exito_y_error(service):
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    tarea = service.añadir_tarea("Correo")
    app = TimeTrackerApp(page, service)
    app._pintar()
    antes = page.actualizaciones

    # éxito: abre la entry anclada a la sesión y repinta
    app._iniciar_tarea(tarea.id)
    assert service.entry_abierta().task_id == tarea.id
    assert service.entry_abierta().session_id == sesion.id
    assert page.actualizaciones > antes

    # error de dominio: tarea inexistente → snack en español, sin refresco
    parado = page.actualizaciones
    app._iniciar_tarea(999_999)
    assert "No existe la tarea" in texto_snack(page)
    assert page.actualizaciones == parado


def test_detener_desde_handler_cierra_y_refresca(service):
    page = PaginaFalsa()
    service.crear_sesion("A")
    tarea = service.añadir_tarea("Correo")
    service.iniciar_tarea(tarea.id)
    app = TimeTrackerApp(page, service)
    app._pintar()
    antes = page.actualizaciones

    app._detener()

    assert service.entry_abierta() is None
    assert page.actualizaciones > antes


def test_detener_con_datos_inconsistentes_muestra_snack(service, db):
    """BD con DOS entries abiertas (inconsistencia externa): el servicio
    lanza `MultipleOpenEntriesError` → snack de dominio, sin traza."""
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    tarea = service.añadir_tarea("Correo")
    db.execute(
        "INSERT INTO time_entries (task_id, session_id, started_at)"
        " VALUES (?, ?, ?), (?, ?, ?)",
        (tarea.id, sesion.id, ISO, tarea.id, sesion.id, ISO),
    )
    app = TimeTrackerApp(page, service)
    app._pintar()
    antes = page.actualizaciones

    app._detener()

    texto = texto_snack(page)
    assert "intervalos abiertos" in texto
    assert "Traceback" not in texto
    assert page.actualizaciones == antes


def test_cerrar_sesion_ya_cerrada_muestra_snack_sin_refrescar(service):
    page = PaginaFalsa()
    sesion = service.crear_sesion("A")
    app = TimeTrackerApp(page, service)
    app._pintar()

    app._cerrar_sesion(sesion.id)               # primera: todo bien
    assert "Sesión terminada" in texto_snack(page)

    antes = page.actualizaciones
    app._cerrar_sesion(sesion.id)               # segunda: SessionClosedError
    assert "ya está cerrada" in texto_snack(page)
    assert page.actualizaciones == antes


# ----------------------------------------------------------------- auxiliar

def _segundos(inicio, hasta) -> int:
    return max(0, int((hasta - inicio).total_seconds()))
