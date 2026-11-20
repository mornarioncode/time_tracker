"""Tests de `ui.logica` — lógica de presentación pura (sin Flet, sin BD).

Cubre: rutas `/sesion/<id>`, cronómetro (`segundos_desde` nunca negativo),
filtro de la entry global a SU sesión (`entrada_de_sesion`), duraciones
(`segundos_entry` — una sesión cerrada **no acumula** — y `total_sesion`),
`nombre_tarea` defensivo y `resumen_sesion` de la portada con datos reales
sembrados en `tmp_path` (fixtures `service`/`clock`).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from core.models import Session, Task, TimeEntry
from ui.logica import (
    RUTA_INICIO,
    entrada_de_sesion,
    id_sesion_de_ruta,
    nombre_tarea,
    resumen_sesion,
    ruta_sesion,
    segundos_desde,
    segundos_entry,
    total_sesion,
)

UTC = timezone.utc
T0 = datetime(2026, 11, 19, 9, 0, 0, tzinfo=UTC)


# ------------------------------------------------------------------- rutas

def test_ruta_sesion():
    assert RUTA_INICIO == "/"
    assert ruta_sesion(7) == "/sesion/7"
    assert ruta_sesion(1) == "/sesion/1"


def test_id_sesion_de_ruta_parsea_la_ruta():
    assert id_sesion_de_ruta("/sesion/7") == 7
    assert id_sesion_de_ruta(ruta_sesion(42)) == 42


def test_id_sesion_de_ruta_rutas_que_no_son_de_sesion():
    assert id_sesion_de_ruta(RUTA_INICIO) is None
    assert id_sesion_de_ruta(None) is None
    assert id_sesion_de_ruta("") is None
    assert id_sesion_de_ruta("/otra") is None
    assert id_sesion_de_ruta("/sesion/") is None      # id vacío
    assert id_sesion_de_ruta("/sesion/abc") is None   # id no numérico
    assert id_sesion_de_ruta("/sesion/12/extra") is None


# --------------------------------------------------------------- cronómetro

def test_segundos_desde_transcurrido():
    assert segundos_desde(T0, T0) == 0
    assert segundos_desde(T0, T0 + timedelta(seconds=90)) == 90


def test_segundos_desde_con_reloj_retrocedido_nunca_negativo():
    """El reloj puede retroceder (o la entry venir del futuro): jamás < 0."""
    assert segundos_desde(T0, T0 - timedelta(seconds=100)) == 0
    assert segundos_desde(T0, T0 - timedelta(microseconds=1)) == 0


def test_segundos_desde_trunca_a_enteros():
    assert segundos_desde(T0, T0 + timedelta(seconds=90, microseconds=900_000)) == 90


# -------------------------------------------------- entry global → esta sesión

def test_entrada_de_sesion_devuelve_la_de_esta_sesion():
    entrada = TimeEntry(id=1, task_id=2, session_id=5, started_at=T0)
    assert entrada_de_sesion(entrada, 5) is entrada


def test_entrada_de_sesion_ignora_la_de_otra_sesion():
    """La única entry abierta es global: en otra sesión no debe pintarse."""
    entrada = TimeEntry(id=1, task_id=2, session_id=5, started_at=T0)
    assert entrada_de_sesion(entrada, 6) is None


def test_entrada_de_sesion_sin_entry():
    assert entrada_de_sesion(None, 5) is None


# --------------------------------------------------------------- duraciones

def test_segundos_entry_cerrada():
    entry = TimeEntry(
        id=1, task_id=2, session_id=5,
        started_at=T0, ended_at=T0 + timedelta(seconds=125),
    )
    assert segundos_entry(entry, T0 + timedelta(hours=3), True) == 125


def test_segundos_entry_abierta_en_sesion_abierta_acumula_hasta_ahora():
    entry = TimeEntry(id=1, task_id=2, session_id=5, started_at=T0)
    assert segundos_entry(entry, T0 + timedelta(seconds=30), True) == 30


def test_segundos_entry_abierta_en_sesion_cerrada_es_cero():
    """§6.1: una sesión cerrada nunca acumula tiempo (estado inalcanzable,
    pero la capa de presentación lo blinda)."""
    entry = TimeEntry(id=1, task_id=2, session_id=5, started_at=T0)
    assert segundos_entry(entry, T0 + timedelta(hours=8), False) == 0


def test_segundos_entry_nunca_negativa():
    """Con el reloj por debajo del `started_at`: 0, no un valor negativo."""
    entry = TimeEntry(id=1, task_id=2, session_id=5, started_at=T0)
    assert segundos_entry(entry, T0 - timedelta(seconds=60), True) == 0
    assert segundos_entry(entry, T0 - timedelta(seconds=60), False) == 0


def test_total_sesion_suma_sus_intervalos():
    cerrada = TimeEntry(
        id=1, task_id=2, session_id=5,
        started_at=T0, ended_at=T0 + timedelta(seconds=600),
    )
    abierta = TimeEntry(id=2, task_id=3, session_id=5, started_at=T0 + timedelta(seconds=600))
    ahora = T0 + timedelta(seconds=720)

    assert total_sesion([cerrada], ahora, True) == 600
    assert total_sesion([cerrada, abierta], ahora, True) == 720   # la abierta suma 120
    assert total_sesion([cerrada, abierta], ahora, False) == 600  # cerrada: la abierta = 0
    assert total_sesion([], ahora, True) == 0


# ------------------------------------------------------------- presentación

def test_nombre_tarea_del_catalogo():
    tareas = [
        Task(id=5, name="Correo", created_at=T0),
        Task(id=9, name="Reuniones", created_at=T0),
    ]
    assert nombre_tarea(tareas, 9) == "Reuniones"
    assert nombre_tarea(tareas, 5) == "Correo"


def test_nombre_tarea_ausente_es_defensivo():
    """El catálogo no se borra en cascada; si falta, id legible, sin crash."""
    assert nombre_tarea([], 77) == "Tarea #77"
    assert nombre_tarea([Task(id=5, name="X", created_at=T0)], 6) == "Tarea #6"


def test_resumen_sesion_de_la_portada(service, clock):
    """Resumen de portada con datos reales en `tmp_path`: primero abierta
    (cronómetro corriendo) y después cerrada."""
    sesion = service.crear_sesion("Semana 48")
    service.añadir_tarea("Correo")
    service.iniciar_tarea(service.listar_tareas()[0].id)
    clock.advance(300)

    abierta = resumen_sesion(sesion, service.listar_intervalos(sesion.id), clock())
    assert abierta.id == sesion.id
    assert abierta.nombre == "Semana 48"
    assert abierta.estado == "Abierta"
    assert abierta.abierta is True
    assert abierta.duracion == "5 min"
    assert abierta.intervalos == 1
    assert re.match(r"^\d{2} nov 2026$", abierta.fecha)

    service.detener_tarea()
    service.cerrar_sesion()
    leida = service.seleccionar_sesion(sesion.id)
    cerrada = resumen_sesion(leida, service.listar_intervalos(sesion.id), clock())
    assert cerrada.estado == "Cerrada"
    assert cerrada.abierta is False
    assert cerrada.duracion == "5 min"
    assert cerrada.intervalos == 1


def test_resumen_sesion_sin_id_y_sin_intervalos():
    """Sesión recién construida (id aún no asignado) e sin intervalos."""
    sesion = Session(name="Sin id", created_at=T0)
    r = resumen_sesion(sesion, [], T0)
    assert r.id == 0
    assert r.nombre == "Sin id"
    assert r.estado == "Abierta"
    assert r.duracion == "0 s"
    assert r.intervalos == 0


def test_resumen_sesion_cerrada_con_entry_abierta_no_acumula():
    """Estado inalcanzable blindado en presentación: 0 s, nunca un robo."""
    sesion = Session(id=3, name="Vieja", created_at=T0, ended_at=T0 + timedelta(hours=1))
    entry = TimeEntry(id=1, task_id=2, session_id=3, started_at=T0)
    r = resumen_sesion(sesion, [entry], T0 + timedelta(hours=8))
    assert r.estado == "Cerrada"
    assert r.duracion == "0 s"
    assert r.intervalos == 1
