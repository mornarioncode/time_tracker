"""Tests de casos de uso de `TimeTrackerService` sobre SQLite real (tmp_path).

Contrato v2 (Fase 1b, §5.3 del plan):
- catálogo GLOBAL de tareas: `añadir_tarea(nombre)` sin sesión, homónimo →
  `DuplicateTaskError`, `listar_tareas()` global;
- `iniciar_tarea` ancla `task_id` + `session_id` de la sesión seleccionada
  (cerrada → `SessionClosedError`; sin selección → `ValidationError`);
- SESIÓN ÚNICA ABIERTA: `crear_sesion` cierra todas las abiertas + la entry
  global con un único `now` en una transacción;
- sesiones cerradas = solo lectura: `seleccionar_sesion` NO lanza, las
  escrituras posteriores sí;
- `eliminar_sesion` borra sus entries en cascada pero el catálogo sobrevive.
Reloj inyectado: duraciones exactas, sin sleeps.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.exceptions import (
    DuplicateTaskError,
    SessionClosedError,
    SessionNotFoundError,
    TaskNotFoundError,
    ValidationError,
)
from tests.conftest import HORA_BASE


# ------------------------------------------------------------- crear_sesion

def test_crear_sesion_deja_la_sesion_actual(service, clock):
    s = service.crear_sesion("  Semana 47 — App web  ")
    assert s.id is not None
    assert s.name == "Semana 47 — App web"  # strip() en el servicio
    assert s.is_open
    assert s.created_at == clock()
    assert service.sesion_actual == s


@pytest.mark.parametrize("nombre", ["", "   ", "\t"])
def test_crear_sesion_nombre_vacio(service, nombre):
    with pytest.raises(ValidationError):
        service.crear_sesion(nombre)
    assert service.sesion_actual is None


@pytest.mark.parametrize("nombre", [None, 7])
def test_crear_sesion_nombre_no_str(service, nombre):
    with pytest.raises(ValidationError):
        service.crear_sesion(nombre)


def test_listar_sesiones_mas_reciente_primero(service, clock):
    a = service.crear_sesion("A")
    clock.advance(60)
    b = service.crear_sesion("B")
    clock.advance(0)  # mismo instante: desempate por id DESC
    c = service.crear_sesion("C")
    assert [s.id for s in service.listar_sesiones()] == [c.id, b.id, a.id]


def test_crear_sesion_cierra_la_anterior_con_un_unico_now(service, clock):
    """§5.3.2 — sesión única abierta: crear B cierra la A + la entry global
    con el MISMO `now` (transacción con reloj único)."""
    a = service.crear_sesion("A")
    tarea = service.añadir_tarea("Trabajo")
    service.iniciar_tarea(tarea.id)
    clock.advance(600)
    b = service.crear_sesion("B")  # cierra A + entry en la transacción

    assert b.is_open
    assert service.sesion_actual.id == b.id
    assert service.entry_abierta() is None
    # releído de la BD: SOLO B está abierta
    abiertas = [s for s in service.listar_sesiones() if s.is_open]
    assert [s.id for s in abiertas] == [b.id]

    a_leida = service.seleccionar_sesion(a.id)
    assert not a_leida.is_open
    assert a_leida.ended_at == clock()  # mismo now que la creación de B
    intervalos = service.listar_intervalos(a.id)
    assert len(intervalos) == 1
    assert intervalos[0].ended_at == clock()  # entry cerrada con ese mismo now
    assert intervalos[0].duration_seconds == 600


def test_crear_sesion_invalida_no_cierra_la_abierta(service, clock):
    """El nombre se valida ANTES de cerrar nada: una creación inválida no
    debe tocar la sesión abierta anterior."""
    a = service.crear_sesion("A")
    clock.advance(60)
    with pytest.raises(ValidationError):
        service.crear_sesion("   ")
    assert service.seleccionar_sesion(a.id).is_open
    assert service.entry_abierta() is None


def test_crear_sesion_es_atomica_rollback(service, db, clock):
    """Si el cierre dentro de la transacción de `crear_sesion` falla (reloj
    por debajo del created_at de la sesión abierta), NO se cierra nada ni se
    crea la nueva sesión: o ocurre todo o no cambia nada.

    Con el reloj retrocedido, `close_open_entry` SÍ escribe (now >=
    started_at) y `set_ended_at` falla después (now < created_at) → el cierre
    escrito debe revertirse junto con el resto.
    """
    a = service.crear_sesion("A")             # created_at = HORA_BASE
    tarea = service.añadir_tarea("Trabajo")
    clock.set(HORA_BASE - timedelta(hours=1))  # reloj retrocede
    e1 = service.iniciar_tarea(tarea.id)       # entry abierta: started < created_at de A

    with pytest.raises(ValidationError):
        service.crear_sesion("B")

    # rollback: la entry sigue abierta (la UPDATE se revirtió), A sigue
    # abierta y B no existe
    abierta = service.entry_abierta()
    assert abierta is not None and abierta.id == e1.id
    assert abierta.ended_at is None
    assert [s.name for s in service.listar_sesiones()] == ["A"]
    assert service.seleccionar_sesion(a.id).is_open


def test_seleccionar_sesion(service, sesion):
    otra = service.crear_sesion("Otra")
    elegida = service.seleccionar_sesion(sesion.id)
    assert elegida.id == sesion.id
    assert service.sesion_actual.id == sesion.id
    assert service.sesion_actual.name == "Sesión de prueba"
    assert otra.id != sesion.id


def test_seleccionar_sesion_inexistente(service):
    with pytest.raises(SessionNotFoundError):
        service.seleccionar_sesion(999)


def test_seleccionar_sesion_cerrada_permite_lectura(service, sesion, tarea, clock):
    """§5.3.4 — las cerradas son historial de solo lectura: seleccionar no
    lanza y las consultas siguen funcionando."""
    service.iniciar_tarea(tarea.id)
    clock.advance(120)
    service.cerrar_sesion()

    cerrada = service.seleccionar_sesion(sesion.id)  # NO lanza
    assert not cerrada.is_open
    assert service.sesion_actual.id == sesion.id
    intervalos = service.listar_intervalos()
    assert len(intervalos) == 1
    assert intervalos[0].duration_seconds == 120
    assert len(service.listar_tareas()) == 1


def test_seleccionar_sesion_cerrada_prohibe_escritura(service, sesion, tarea):
    """§5.3.4 — seleccionar una cerrada NO permite escribir sobre ella."""
    service.cerrar_sesion()
    service.seleccionar_sesion(sesion.id)
    with pytest.raises(SessionClosedError):
        service.iniciar_tarea(tarea.id)
    with pytest.raises(SessionClosedError):
        service.cerrar_sesion()
    assert service.detener_tarea() is None  # sin entry abierta: no-op inocuo


# -------------------------------------------------------------- añadir_tarea

def test_anadir_tarea_es_global_sin_sesion(service, clock):
    """§5.3.3 — el catálogo es global: no requiere ni usa sesión."""
    t = service.añadir_tarea("   Escribir tests   ")
    assert t.id is not None
    assert t.name == "Escribir tests"  # strip() (servicio + modelo)
    assert t.created_at == clock()
    assert not hasattr(t, "session_id")  # v2: la tarea no pertenece a nadie
    assert [x.id for x in service.listar_tareas()] == [t.id]


def test_anadir_tarea_sin_sesion_seleccionada(service):
    """Añadir al catálogo NO toca sesiones: funciona sin nada seleccionado."""
    t = service.añadir_tarea("T")
    assert t.id is not None
    assert [x.name for x in service.listar_tareas()] == ["T"]


@pytest.mark.parametrize("nombre", ["", "  ", None])
def test_anadir_tarea_nombre_vacio(service, nombre):
    with pytest.raises(ValidationError):
        service.añadir_tarea(nombre)


def test_anadir_tarea_duplicada(service):
    service.añadir_tarea("Tarea X")
    with pytest.raises(DuplicateTaskError):
        service.añadir_tarea("Tarea X")


def test_anadir_tarea_duplicada_tras_strip(service):
    """' Tarea X ' y 'Tarea X' son la misma tarea tras el strip()."""
    service.añadir_tarea("Tarea X")
    with pytest.raises(DuplicateTaskError):
        service.añadir_tarea("  Tarea X  ")


def test_anadir_tarea_mismo_nombre_en_otra_sesion_es_duplicada(service):
    """v2: el catálogo es GLOBAL → homónimo aunque cambies de sesión."""
    service.añadir_tarea("Tarea X")
    service.crear_sesion("Otra sesión")  # cambia de jornada, no de catálogo
    with pytest.raises(DuplicateTaskError):
        service.añadir_tarea("Tarea X")


def test_listar_tareas_orden_creacion(service, clock):
    t1 = service.añadir_tarea("Una")
    clock.advance(5)
    t2 = service.añadir_tarea("Dos")
    clock.advance(5)
    t3 = service.añadir_tarea("Tres")
    assert [t.id for t in service.listar_tareas()] == [t1.id, t2.id, t3.id]


# -------------------------------------------------------------- iniciar_tarea

def test_iniciar_tarea_abre_intervalo_anclado_a_la_sesion(service, sesion, tarea, clock):
    e = service.iniciar_tarea(tarea.id)
    assert e.id is not None
    assert e.task_id == tarea.id
    assert e.session_id == sesion.id  # v2: ancla a la sesión seleccionada
    assert e.started_at == clock()
    assert e.is_open
    abierta = service.entry_abierta()
    assert abierta is not None and abierta.id == e.id


def test_iniciar_tarea_misma_tarea_es_no_op(service, sesion, tarea, clock):
    e1 = service.iniciar_tarea(tarea.id)
    clock.advance(60)
    e2 = service.iniciar_tarea(tarea.id)  # ya está corriendo: no-op
    assert e2.id == e1.id
    assert e2.started_at == e1.started_at  # sin micro-intervalos
    intervalos = service.listar_intervalos()
    assert len(intervalos) == 1
    assert service.entry_abierta().id == e1.id


def test_cambiar_de_tarea_cierra_la_anterior(service, sesion, clock):
    t1 = service.añadir_tarea("Primera")
    t2 = service.añadir_tarea("Segunda")
    e1 = service.iniciar_tarea(t1.id)
    clock.advance(300)
    e2 = service.iniciar_tarea(t2.id)

    intervalos = service.listar_intervalos()
    assert len(intervalos) == 2

    cerrada = intervalos[0]
    assert cerrada.id == e1.id
    assert cerrada.ended_at == e1.started_at + timedelta(seconds=300)
    assert cerrada.duration_seconds == 300
    assert cerrada.session_id == sesion.id

    abierta = service.entry_abierta()
    assert abierta.id == e2.id == intervalos[1].id
    assert abierta.session_id == sesion.id
    assert intervalos[1].ended_at is None


def test_solo_una_entry_abierta_tras_varios_cambios(service, sesion, clock):
    tareas = [service.añadir_tarea(f"T{i}") for i in range(4)]
    for i, t in enumerate(tareas):
        service.iniciar_tarea(t.id)
        clock.advance(60 * (i + 1))
    abiertas = [e for e in service.listar_intervalos() if e.is_open]
    assert len(abiertas) == 1
    assert service.entry_abierta().task_id == tareas[-1].id


def test_iniciar_tarea_en_sesion_cerrada(service, sesion, tarea):
    service.cerrar_sesion()
    with pytest.raises(SessionClosedError):
        service.iniciar_tarea(tarea.id)


def test_iniciar_tarea_sin_sesion_seleccionada(service):
    """§5.3.3 — sin sesión seleccionada no hay dónde anclar la entry."""
    t = service.añadir_tarea("T")  # el catálogo no requiere sesión…
    with pytest.raises(ValidationError):
        service.iniciar_tarea(t.id)  # …pero iniciar sí


def test_iniciar_tarea_tarea_inexistente(service, sesion):
    with pytest.raises(TaskNotFoundError):
        service.iniciar_tarea(4242)


def test_iniciar_tarea_contrae_todo_en_una_transaccion(service, db, sesion, tarea, clock):
    """Rollback de `iniciar_tarea`: si algo falla, nada cambió en la BD.

    El reloj se retrocede para que el cierre de la entry actual sea inválido
    (`ended_at < started_at`): la transacción debe abortar dejando la entry
    abierta y sin crear la nueva.
    """
    e1 = service.iniciar_tarea(tarea.id)
    t2 = service.añadir_tarea("Otra")
    clock.set(e1.started_at - timedelta(seconds=60))

    with pytest.raises(ValidationError):
        service.iniciar_tarea(t2.id)

    abierta = service.entry_abierta()
    assert abierta is not None and abierta.id == e1.id
    assert abierta.ended_at is None
    assert len(service.listar_intervalos()) == 1  # no se creó la nueva entry
    # sin estados intermedios residuales: la BD admite una transacción nueva
    with db.transaction():
        pass


# -------------------------------------------------------------- detener_tarea

def test_detener_tarea_cierra_con_duracion_exacta(service, sesion, tarea, clock):
    service.iniciar_tarea(tarea.id)
    clock.advance(450)
    cerrada = service.detener_tarea()
    assert cerrada is not None
    assert cerrada.ended_at == clock()
    assert cerrada.duration_seconds == 450
    assert service.entry_abierta() is None


def test_detener_tarea_sin_entry_abierta_devuelve_none(service):
    assert service.entry_abierta() is None
    assert service.detener_tarea() is None


def test_detener_tarea_segunda_vez_devuelve_none(service, sesion, tarea, clock):
    service.iniciar_tarea(tarea.id)
    assert service.detener_tarea() is not None
    assert service.detener_tarea() is None


# -------------------------------------------------------------- cerrar_sesion

def test_cerrar_sesion_cierra_entry_y_sesion(service, sesion, tarea, clock):
    service.iniciar_tarea(tarea.id)
    clock.advance(600)
    cerrada = service.cerrar_sesion()

    assert not cerrada.is_open
    assert cerrada.ended_at == clock()
    assert service.entry_abierta() is None
    intervalos = service.listar_intervalos()
    assert len(intervalos) == 1
    assert intervalos[0].duration_seconds == 600


def test_cerrar_sesion_sin_entry_abierta(service, sesion, clock):
    clock.advance(30)
    cerrada = service.cerrar_sesion()
    assert not cerrada.is_open
    assert cerrada.ended_at == clock()


def test_cerrar_sesion_dos_vez_lanza_session_closed(service, sesion):
    service.cerrar_sesion()
    with pytest.raises(SessionClosedError):
        service.cerrar_sesion()


def test_cerrar_sesion_sin_sesion_seleccionada(service):
    with pytest.raises(ValidationError):
        service.cerrar_sesion()


def test_cerrar_sesion_es_atomica_rollback(service, db, sesion, tarea, clock):
    """Rollback de `cerrar_sesion`: el cierre de la entry (UPDATE escrita
    DENTRO de la transacción) se revierte si `set_ended_at` falla después.

    Se consigue con el reloj retrocedido por debajo del created_at de la
    sesión (HORA_BASE) pero por encima del started_at de la entry: el cierre
    de la entry es válido y se ESCRIBE, y luego el cierre de sesión falla
    → la transacción entera debe revertirse.
    """
    # reloj retrocede ANTES de iniciar: la entry queda con started_at <
    # created_at de la sesión, de modo que en cerrar_sesion el cierre de la
    # entry SÍ se escribe y el cierre de sesión falla después
    clock.set(HORA_BASE - timedelta(hours=1))
    e1 = service.iniciar_tarea(tarea.id)  # started_at = HORA_BASE - 1 h

    with pytest.raises(ValidationError):
        service.cerrar_sesion()

    # la UPDATE de la entry se hizo dentro de la transacción → revertida
    abierta = service.entry_abierta()
    assert abierta is not None and abierta.id == e1.id
    assert abierta.ended_at is None
    assert service.sesion_actual.is_open
    assert len(service.listar_intervalos()) == 1
    # la BD admite una transacción nueva (sin estado colgante)
    with db.transaction():
        pass


def test_cerrar_sesion_por_id_explicito_distinto_de_la_actual(service, clock):
    """`cerrar_sesion(id)` cierra la sesión indicada aunque no sea la actual."""
    a = service.crear_sesion("A")   # se cierra sola al crear B
    clock.advance(60)
    b = service.crear_sesion("B")   # única abierta
    a_leida = service.seleccionar_sesion(a.id)  # actual = A (cerrada)
    cerrada = service.cerrar_sesion(b.id)       # cierra B (abierta)
    assert cerrada.id == b.id
    assert not cerrada.is_open
    # A no se toca: conserva su auto-cierre del instante en que se creó B
    assert service.seleccionar_sesion(a.id).ended_at == a_leida.ended_at
    # y sobre una ya cerrada → SessionClosedError
    with pytest.raises(SessionClosedError):
        service.cerrar_sesion(a.id)


# ------------------------------------------- operaciones sobre sesión cerrada

def test_anadir_tarea_en_sesion_cerrada_no_lanza(service, sesion, tarea):
    """v2: el catálogo es global → cerrar la sesión NO bloquea `añadir_tarea`
    (a diferencia de `iniciar_tarea`, que sigue prohibido)."""
    service.cerrar_sesion()
    nueva = service.añadir_tarea("Nueva")  # no lanza SessionClosedError
    assert nueva.id is not None
    with pytest.raises(SessionClosedError):
        service.iniciar_tarea(tarea.id)
    with pytest.raises(SessionClosedError):
        service.iniciar_tarea(nueva.id)


def test_listar_en_sesion_cerrada_es_permitido(service, sesion, tarea):
    """Las lecturas sobre una sesión cerrada deben seguir funcionando."""
    service.iniciar_tarea(tarea.id)
    service.cerrar_sesion()
    assert len(service.listar_tareas()) == 1
    assert len(service.listar_intervalos()) == 1


# --------------------------------------------------------------- eliminar

def test_eliminar_sesion_borra_entries_pero_el_catalogo_sobrevive(
    service, db, sesion, clock
):
    """§5.2 regla 3 — la cascada es SOLO sobre time_entries: las tareas del
    catálogo global sobreviven al borrado de la sesión."""
    t1 = service.añadir_tarea("Uno")
    t2 = service.añadir_tarea("Dos")
    service.iniciar_tarea(t1.id)
    clock.advance(60)
    service.iniciar_tarea(t2.id)  # cierra t1 y abre t2
    clock.advance(60)
    service.detener_tarea()

    sid = sesion.id
    service.eliminar_sesion(sid)

    assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM time_entries").fetchone()[0] == 0  # cascada
    assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2  # sobreviven
    assert [t.name for t in service.listar_tareas()] == ["Uno", "Dos"]  # catálogo vivo
    assert service.sesion_actual is None
    assert service.entry_abierta() is None
    with pytest.raises(ValidationError):
        service.listar_intervalos()  # sin sesión actual
    with pytest.raises(SessionNotFoundError):
        service.seleccionar_sesion(sid)


def test_eliminar_sesion_inexistente(service):
    with pytest.raises(SessionNotFoundError):
        service.eliminar_sesion(12345)


def test_eliminar_otra_sesion_no_limpia_la_actual(service, sesion):
    otra = service.crear_sesion("Para borrar")
    service.seleccionar_sesion(sesion.id)
    service.eliminar_sesion(otra.id)
    assert service.sesion_actual.id == sesion.id


def test_sesion_actual_se_autolimpia_si_la_sesion_se_borra_fuera_del_servicio(
    service, db, sesion
):
    """Si la sesión actual desaparece de la BD sin pasar por `eliminar_sesion`
    (p. ej. borrado externo), `sesion_actual` debe devolver None en vez de fallar."""
    assert service.sesion_actual.id == sesion.id
    db.execute("DELETE FROM sessions WHERE id = ?", (sesion.id,))
    assert service.sesion_actual is None
    assert service.sesion_actual is None  # el id quedó reseteado
    with pytest.raises(ValidationError):
        service.listar_intervalos()  # sin sesión actual


def test_eliminar_sesion_con_entry_abierta(service, db, sesion, tarea, clock):
    service.iniciar_tarea(tarea.id)
    sid = sesion.id
    service.eliminar_sesion(sid)
    assert service.entry_abierta() is None
    assert db.execute("SELECT COUNT(*) FROM time_entries").fetchone()[0] == 0


def test_reutilizar_tarea_en_dos_sesiones(service, clock):
    """Caso de uso real del usuario (§5.3.3): la tarea "Correo" corre el
    LUNES y el MARTES sin recrearla — un solo elemento en el catálogo y una
    entry por jornada."""
    lunes = service.crear_sesion("Lunes")
    correo = service.añadir_tarea("Correo")  # se crea UNA vez
    service.iniciar_tarea(correo.id)          # entry en el lunes
    clock.advance(3_600)
    martes = service.crear_sesion("Martes")   # cierra lunes + entry (auto-cierre)
    service.iniciar_tarea(correo.id)          # MISMA tarea, otra jornada
    clock.advance(1_800)
    service.detener_tarea()

    assert [t.id for t in service.listar_tareas()] == [correo.id]  # 1 sola tarea
    assert len(service.listar_tareas()) == 1

    e_lunes = service.listar_intervalos(lunes.id)
    e_martes = service.listar_intervalos(martes.id)
    assert len(e_lunes) == 1 and len(e_martes) == 1
    assert e_lunes[0].session_id == lunes.id
    assert e_martes[0].session_id == martes.id
    assert e_lunes[0].task_id == e_martes[0].task_id == correo.id
    assert e_lunes[0].duration_seconds == 3_600
    assert e_martes[0].duration_seconds == 1_800
    assert service.entry_abierta() is None


# -------------------------------------------------- listar_intervalos / flujo

def test_listar_intervalos_relee_modelos_inmutables(service, sesion, tarea, clock):
    e1 = service.iniciar_tarea(tarea.id)
    clock.advance(100)
    service.detener_tarea()

    intervalos = service.listar_intervalos()
    assert len(intervalos) == 1
    assert intervalos[0].id == e1.id
    assert intervalos[0].duration_seconds == 100
    # son objetos nuevos en cada lectura (dataclasses congeladas)
    assert intervalos[0] is not service.listar_intervalos()[0]


def test_listar_intervalos_sin_sesion_seleccionada(service):
    with pytest.raises(ValidationError):
        service.listar_intervalos()


def test_listar_intervalos_por_session_id(service, sesion, tarea, clock):
    service.iniciar_tarea(tarea.id)
    clock.advance(120)
    service.detener_tarea()
    s2 = service.crear_sesion("Segunda")
    assert service.listar_intervalos(s2.id) == []
    assert len(service.listar_intervalos(sesion.id)) == 1


def test_sesion_unica_abierta_relee_de_la_bd(service, clock):
    """§5.3.2 — NO se permiten varias sesiones abiertas: al crear la tercera,
    solo la última queda abierta (releído de la BD, no de los objetos)."""
    a = service.crear_sesion("A")
    b = service.crear_sesion("B")
    c = service.crear_sesion("C")
    abiertas = [s for s in service.listar_sesiones() if s.is_open]
    assert [s.id for s in abiertas] == [c.id]
    assert service.sesion_actual.id == c.id
    assert service.entry_abierta() is None
    # las anteriores quedaron cerradas con ended_at asignado
    por_id = {s.id: s for s in service.listar_sesiones()}
    assert not por_id[a.id].is_open and por_id[a.id].ended_at is not None
    assert not por_id[b.id].is_open and por_id[b.id].ended_at is not None


def test_entry_abierta_global_entre_sesiones(service, clock):
    """La única entry abierta es global: crear otra sesión cierra la anterior
    y la nueva entry se ancla a la sesión seleccionada."""
    s1 = service.crear_sesion("A")
    t1 = service.añadir_tarea("T1")
    service.iniciar_tarea(t1.id)               # entry abierta en A
    s2 = service.crear_sesion("B")             # cierra A + su entry
    t2 = service.añadir_tarea("T2")
    e2 = service.iniciar_tarea(t2.id)          # abre en B

    abierta = service.entry_abierta()
    assert abierta.id == e2.id
    assert abierta.task_id == t2.id
    assert abierta.session_id == s2.id  # anclada a la sesión seleccionada

    # solo 1 abierta en total; la de A quedó cerrada por el auto-cierre
    assert [e for e in service.listar_intervalos(s1.id) if e.is_open] == []
    assert len(service.listar_intervalos(s1.id)) == 1
    assert [e.id for e in service.listar_intervalos(s2.id) if e.is_open] == [e2.id]


def test_flujo_completo_con_duraciones_exactas(service, clock):
    """Escenario punta a punta: crear sesión → tareas → cambiar → detener →
    cerrar, con la suma de intervalos cuadrando con el tiempo transcurrido."""
    s = service.crear_sesion("Proyecto X")
    t1 = service.añadir_tarea("Diseño")
    t2 = service.añadir_tarea("Código")
    t3 = service.añadir_tarea("Tests")

    service.iniciar_tarea(t1.id)   # T0
    clock.advance(600)             # 10 min
    service.iniciar_tarea(t2.id)   # cierra t1 a los 600 s
    clock.advance(1_200)           # 20 min
    service.iniciar_tarea(t3.id)   # cierra t2 a los 1200 s
    clock.advance(300)             # 5 min
    service.detener_tarea()        # cierra t3 a los 300 s
    clock.advance(999)             # muerto el reloj: no afecta a los intervalos
    cerrada = service.cerrar_sesion()

    intervalos = service.listar_intervalos(s.id)
    assert [e.duration_seconds for e in intervalos] == [600, 1_200, 300]
    assert sum(e.duration_seconds for e in intervalos) == 2_100
    assert all(e.session_id == s.id for e in intervalos)  # v2: todos anclados
    assert not cerrada.is_open
    assert service.entry_abierta() is None
    # la sesión cerrada sigue siendo seleccionable y consultable
    assert service.seleccionar_sesion(s.id).name == "Proyecto X"
    assert len(service.listar_tareas()) == 3
    assert HORA_BASE < cerrada.ended_at
