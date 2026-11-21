"""Tests de `reports/stats.py` (Fase 3): agregaciones puras con datos sembrados.

Sin Flet y sin BD (§7: "Reporting | agregaciones con datasets sembrados
incl. bordes: días sin datos, entry en curso"): se siembran `TimeEntry` /
`Task` / `Session` (dataclasses de `core.models`) con reloj fijo.

Zona horaria: en Windows no existe `time.tzset`, así que la tz local del
sistema no se puede fijar desde el test. Por eso:

- los instantes "del día d" se construyen en hora LOCAL (`local`, naive →
  aware), de modo que su fecha local es `d` en cualquier zona;
- las medianoches esperadas se derivan del offset real del sistema con
  `medianoche_esperada` (sondeado en el mediodía UTC del día anterior:
  coincide con el de la medianoche local incluso los días de cambio de hora,
  porque las transiciones ocurren de madrugada).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta, timezone

import pytest

from core.exceptions import ValidationError
from core.models import Session, Task, TimeEntry
from reports import stats
from reports.stats import (
    PRESETS_RANGO,
    Rango,
    TotalDia,
    TotalTarea,
    csv_detalle,
    excluidas_abiertas,
    filtrar,
    informe,
    rango_fechas,
    rango_preset,
    totales_por_dia,
    totales_por_semana,
    totales_por_tarea,
)

UTC = timezone.utc
CABECERA_CSV = "Fecha;Tarea;Sesión;Inicio;Fin;Duración (s)"


# ------------------------------------------------------------------ helpers

def local(d: date, hora: int = 10, minuto: int = 0) -> datetime:
    """Instante aware en la hora LOCAL del sistema para el día `d`.

    Naive → aware usa la zona del sistema: la fecha local resultante es `d`
    sea cual sea la tz (los tests no dependen de un offset concreto).
    """
    return datetime.combine(d, time(hora, minuto)).astimezone()


def medianoche_esperada(d: date) -> datetime:
    """Medianoche local de `d` expresada como instante UTC.

    El offset se sondea en el mediodía UTC del día ANTERIOR: es el de la
    medianoche local de `d` también en los días de cambio de hora (las
    transiciones de la zona del sistema ocurren de madrugada, después de
    medianoche y antes del día siguiente).
    """
    sonda = datetime(d.year, d.month, d.day, 12, tzinfo=UTC) - timedelta(days=1)
    offset = sonda.astimezone().utcoffset()
    return datetime(d.year, d.month, d.day, tzinfo=UTC) - offset


def cerrada(
    task_id: int, session_id: int, inicio: datetime, segundos: int,
    id: int | None = None,
) -> TimeEntry:
    """Intervalo cerrado de `segundos` segundos que empieza en `inicio`."""
    return TimeEntry(
        id=id, task_id=task_id, session_id=session_id,
        started_at=inicio, ended_at=inicio + timedelta(seconds=segundos),
    )


def abierta(
    task_id: int, session_id: int, inicio: datetime, id: int | None = None,
) -> TimeEntry:
    """Intervalo en curso (sin `ended_at`)."""
    return TimeEntry(
        id=id, task_id=task_id, session_id=session_id, started_at=inicio,
    )


def tarea(id: int | None, nombre: str) -> Task:
    return Task(id=id, name=nombre, created_at=datetime(2026, 1, 1, tzinfo=UTC))


def sesion(id: int | None, nombre: str) -> Session:
    return Session(id=id, name=nombre, created_at=datetime(2026, 1, 1, tzinfo=UTC))


def _filas_csv(texto: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(texto), delimiter=";"))


# ------------------------------------------------------------------ presets

def test_presets_disponibles():
    """§6 Fase 3: hoy / 7 días / 30 días / todo / personalizado."""
    assert PRESETS_RANGO == ("hoy", "7d", "30d", "todo", "personalizado")


def test_preset_hoy_es_la_medianoche_local_de_hoy():
    ahora = local(date(2026, 11, 21), 12, 34)
    r = rango_preset("hoy", ahora)

    assert r.clave == "hoy"
    assert r.fin is None
    assert r.inicio == medianoche_esperada(date(2026, 11, 21))
    # medianoche LOCAL (hora 0 en la zona del sistema)
    assert r.inicio.astimezone().hour == 0
    assert r.inicio.astimezone().date() == date(2026, 11, 21)


def test_preset_hoy_en_el_primer_dia_del_ano():
    """Borde de año: "hoy" sigue siendo la medianoche del 1 de enero."""
    ahora = local(date(2026, 1, 1), 0, 30)
    r = rango_preset("hoy", ahora)

    assert r.inicio == medianoche_esperada(date(2026, 1, 1))
    assert r.inicio.astimezone().date() == date(2026, 1, 1)


def test_preset_7d_y_30d_cruzan_el_año_desde_el_primer_dia_de_enero():
    """Borde de año: 7d → 26-dic (año anterior); 30d → 3-dic."""
    ahora = local(date(2026, 1, 1), 9, 0)
    r7 = rango_preset("7d", ahora)
    r30 = rango_preset("30d", ahora)

    assert r7.inicio.astimezone().date() == date(2025, 12, 26)
    assert r30.inicio.astimezone().date() == date(2025, 12, 3)
    for r in (r7, r30):
        assert r.fin is None
        assert r.inicio == medianoche_esperada(r.inicio.astimezone().date())
        assert r.inicio.astimezone().hour == 0   # medianoche local


def test_preset_en_ultimo_dia_del_ano():
    ahora = local(date(2026, 12, 31), 23, 59)
    r_hoy = rango_preset("hoy", ahora)
    r7 = rango_preset("7d", ahora)
    r30 = rango_preset("30d", ahora)

    assert r_hoy.inicio.astimezone().date() == date(2026, 12, 31)
    assert r7.inicio.astimezone().date() == date(2026, 12, 25)
    assert r30.inicio.astimezone().date() == date(2026, 12, 2)


def test_preset_30d_cruza_el_borde_de_mes():
    """1-mar: 7d → 23-feb y 30d → 31-ene (febrero de 28 días, no bisiesto)."""
    ahora = local(date(2026, 3, 1), 8, 0)
    assert rango_preset("7d", ahora).inicio.astimezone().date() == date(2026, 2, 23)
    assert rango_preset("30d", ahora).inicio.astimezone().date() == date(2026, 1, 31)


def test_preset_7d_y_30d_incluyen_el_dia_actual():
    """7d = hoy-6 … hoy inclusive (ambas extreme entran por `started_at`)."""
    dia = date(2026, 11, 21)
    ahora = local(dia, 18, 0)
    r7 = rango_preset("7d", ahora)

    primer_dia = dia - timedelta(days=6)
    justo_al_principio = cerrada(1, 1, local(primer_dia, 0, 0), 60)
    dia_anterior = cerrada(1, 1, local(dia - timedelta(days=7), 23, 59), 60)
    hoy = cerrada(1, 1, local(dia, 17, 59), 60)

    assert r7.inicio <= ahora   # el rango cubre "ahora"
    assert filtrar(
        [justo_al_principio, dia_anterior, hoy], rango=r7
    ) == [justo_al_principio, hoy]

    r30 = rango_preset("30d", ahora)
    assert r30.inicio.astimezone().date() == dia - timedelta(days=29)


def test_preset_todo_sin_limites():
    r = rango_preset("todo", local(date(2026, 11, 21), 12))
    assert r == Rango(clave="todo")
    assert r.inicio is None and r.fin is None
    # sin límites: cualquier intervalo cerrado encaja
    e = cerrada(1, 1, datetime(2000, 1, 1, tzinfo=UTC), 60)
    assert filtrar([e], rango=r) == [e]


def test_preset_personalizado_lanza_validation_error():
    """`personalizado` exige `rango_fechas(desde, hasta)` (§6 Fase 3)."""
    with pytest.raises(ValidationError) as exc:
        rango_preset("personalizado", local(date(2026, 11, 21), 12))
    assert "desde" in str(exc.value) and "hasta" in str(exc.value)


def test_preset_desconocido_lanza_validation_error():
    for clave in ("semana", "", "7 dias"):
        with pytest.raises(ValidationError) as exc:
            rango_preset(clave, local(date(2026, 11, 21), 12))
        assert f"Rango desconocido: {clave}" == str(exc.value)


# -------------------------------------------------------------- rango_fechas

def test_rango_fechas_desde_posterior_a_hasta_lanza_error():
    with pytest.raises(ValidationError) as exc:
        rango_fechas(date(2026, 5, 20), date(2026, 5, 12))
    assert "no puede ser posterior" in str(exc.value)


def test_rango_fechas_mismo_dia_inicio_y_fin_exclusivo():
    d = date(2026, 5, 12)
    r = rango_fechas(d, d)

    assert r.clave == "personalizado"
    assert r.inicio == medianoche_esperada(d)
    assert r.fin == medianoche_esperada(d + timedelta(days=1))   # exclusivo


def test_rango_fechas_ambas_inclusive_y_fin_exclusivo_con_entries():
    """Desde 00:00 incluido hasta 23:59:59 incluido; la medianoche de FIN
    (00:00 del día siguiente) ya queda FUERA."""
    d = date(2026, 5, 12)
    r = rango_fechas(d, d)

    en_inicio = cerrada(1, 1, local(d, 0, 0), 60)
    ultima_del_dia = cerrada(1, 1, local(d, 23, 59), 60)
    justo_en_fin = cerrada(1, 1, local(d + timedelta(days=1), 0, 0), 60)

    assert filtrar(
        [en_inicio, ultima_del_dia, justo_en_fin], rango=r
    ) == [en_inicio, ultima_del_dia]


# ------------------------------------------------------------------- filtrar

def test_filtrar_por_started_at_entry_que_empieza_antes_queda_fuera():
    """Se filtra por `started_at`: aunque termine DENTRO del rango."""
    d = date(2026, 5, 12)
    r = rango_fechas(d, d)
    empieza_antes = TimeEntry(
        task_id=1, session_id=1,
        started_at=local(d - timedelta(days=1), 23, 0),
        ended_at=local(d, 1, 0),
    )
    dentro = cerrada(1, 1, local(d, 9), 300)

    assert empieza_antes.ended_at >= r.inicio   # termina dentro del rango
    assert filtrar([empieza_antes, dentro], rango=r) == [dentro]


def test_filtrar_excluye_las_abiertas():
    d = date(2026, 5, 12)
    r = rango_fechas(d, d)
    en_curso = abierta(1, 1, local(d, 12))
    cerrado = cerrada(1, 1, local(d, 9), 60)

    assert filtrar([en_curso, cerrado], rango=r) == [cerrado]


def test_filtrar_por_sesion_y_tarea_cruzados():
    base = local(date(2026, 5, 12), 9)
    entries = [
        cerrada(1, 1, base, 100),
        cerrada(2, 1, base + timedelta(hours=1), 200),
        cerrada(1, 2, base + timedelta(hours=2), 400),
        cerrada(2, 2, base + timedelta(hours=3), 800),
    ]
    assert filtrar(entries, session_id=1) == entries[:2]
    assert filtrar(entries, task_id=2) == [entries[1], entries[3]]
    assert filtrar(entries, session_id=1, task_id=2) == [entries[1]]
    assert filtrar(entries, session_id=2, task_id=1) == [entries[2]]
    # sin filtros y sin rango: todas las cerradas, en su orden
    assert filtrar(entries) == entries


def test_filtrar_sin_rango_ignora_las_fechas():
    vieja = cerrada(1, 1, datetime(2000, 1, 1, tzinfo=UTC), 60)
    futura = cerrada(1, 1, datetime(2099, 1, 1, tzinfo=UTC), 60)
    assert filtrar([vieja, futura], rango=None) == [vieja, futura]


# --------------------------------------------------------- excluidas_abiertas

def test_excluidas_abiertas_solo_las_que_encajan_en_el_rango():
    d = date(2026, 5, 12)
    r = rango_fechas(d, d)
    en_curso_dentro = abierta(1, 1, local(d, 12))
    en_curso_fuera = abierta(1, 1, local(d - timedelta(days=1), 12))
    cerrada_dentro = cerrada(1, 1, local(d, 9), 60)
    entries = [en_curso_dentro, en_curso_fuera, cerrada_dentro]

    assert excluidas_abiertas(entries, rango=r) == [en_curso_dentro]
    assert filtrar(entries, rango=r) == [cerrada_dentro]


def test_excluidas_abiertas_con_filtros_de_sesion_y_tarea():
    base = local(date(2026, 5, 12), 9)
    en_curso_s1 = abierta(1, 1, base)
    en_curso_s2 = abierta(1, 2, base)
    assert excluidas_abiertas([en_curso_s1, en_curso_s2], session_id=2) == [
        en_curso_s2
    ]
    assert excluidas_abiertas([en_curso_s1, en_curso_s2], task_id=1) == [
        en_curso_s1, en_curso_s2
    ]
    assert excluidas_abiertas([en_curso_s1], task_id=99) == []


# --------------------------------------------------------- totales_por_tarea

def test_totales_por_tarea_orden_desc_y_agrupacion():
    base = local(date(2026, 5, 12), 9)
    entries = [
        cerrada(1, 1, base, 60),
        cerrada(1, 1, base + timedelta(hours=1), 40),
        cerrada(2, 1, base + timedelta(hours=2), 500),
        abierta(3, 1, base + timedelta(hours=3)),   # en curso: fuera
    ]
    totales = totales_por_tarea(
        entries, [tarea(1, "Correo"), tarea(2, "Reuniones"), tarea(3, "Estudio")]
    )

    assert [(t.task_id, t.segundos, t.intervalos) for t in totales] == [
        (2, 500, 1),
        (1, 100, 2),
    ]


def test_totales_por_tarea_empate_se_ordena_por_nombre():
    base = local(date(2026, 5, 12), 9)
    entries = [cerrada(1, 1, base, 600), cerrada(2, 1, base, 600)]
    totales = totales_por_tarea(entries, [tarea(1, "Zeta"), tarea(2, "Alfa")])
    assert [t.nombre for t in totales] == ["Alfa", "Zeta"]


def test_totales_por_tarea_huerfanas_se_etiquetan_con_su_id():
    """BD heredada con entries de una tarea ya fuera del catálogo."""
    base = local(date(2026, 5, 12), 9)
    totales = totales_por_tarea(
        [cerrada(99, 1, base, 300)], [tarea(1, "Correo")]
    )
    assert totales == [TotalTarea(task_id=99, nombre="Tarea #99",
                                 segundos=300, intervalos=1)]


def test_totales_por_tarea_ignora_las_abiertas_defensivamente():
    """Los totales ignoran cualquier intervalo en curso que llegue suelto."""
    base = local(date(2026, 5, 12), 9)
    assert totales_por_tarea([abierta(1, 1, base)], [tarea(1, "Correo")]) == []


# ---------------------------------------------------------- totales_por_dia

def test_totales_por_dia_union_mismo_dia_local_y_orden_asc():
    """Dos entries del mismo día local se suman; días asc."""
    d1, d2 = date(2026, 5, 12), date(2026, 5, 14)
    entries = [
        cerrada(1, 1, local(d1, 9), 600),
        cerrada(1, 1, local(d1, 18), 400),
        cerrada(1, 1, local(d2, 10), 50),
    ]
    assert [(t.dia, t.segundos, t.intervalos) for t in totales_por_dia(entries)] == [
        (d1, 1000, 2),
        (d2, 50, 1),
    ]


def test_totales_por_dia_agrupa_por_fecha_local_no_por_utc():
    """La entry de las 00:30 locales pertenece al día local (puede ser del
    día anterior en UTC en zonas con offset positivo)."""
    d = date(2026, 6, 10)
    e = cerrada(1, 1, local(d, 0, 30), 600)
    dias = totales_por_dia([e])
    assert len(dias) == 1
    assert dias[0].dia == d


def test_totales_por_dia_rellena_con_cero_y_anade_los_que_falten():
    d1, d2, d3, d4 = (date(2026, 5, i) for i in (12, 13, 14, 15))
    entries = [cerrada(1, 1, local(d4, 10), 50)]

    # días pedidos sin datos → a 0; día CON datos que no estaba en la lista
    # → se añade (nunca se pierde información).
    assert [
        (t.dia, t.segundos, t.intervalos)
        for t in totales_por_dia(entries, dias=[d1, d2, d3])
    ] == [(d1, 0, 0), (d2, 0, 0), (d3, 0, 0), (d4, 50, 1)]


def test_totales_por_dia_sin_lista_solo_los_dias_con_datos():
    d1, d2 = date(2026, 5, 12), date(2026, 5, 15)
    entries = [cerrada(1, 1, local(d1, 9), 10), cerrada(1, 1, local(d2, 9), 20)]
    assert [t.dia for t in totales_por_dia(entries)] == [d1, d2]


def test_totales_por_dia_ignora_las_abiertas():
    d = date(2026, 5, 12)
    assert totales_por_dia([abierta(1, 1, local(d, 9))]) == []


# -------------------------------------------------------- totales_por_semana

def test_totales_por_semana_lunes_iso():
    """Miércoles 7-ene-2026 → semana del lunes 5-ene-2026."""
    d = date(2026, 1, 7)
    semanas = totales_por_semana([cerrada(1, 1, local(d, 10), 600)])
    assert len(semanas) == 1
    assert semanas[0].lunes == date(2026, 1, 5)
    assert (semanas[0].segundos, semanas[0].intervalos) == (600, 1)


def test_totales_por_semana_cruce_de_años():
    """30-dic-2025 (mar) y 2-ene-2026 (vie) caen en la semana del
    lunes 29-dic-2025: una sola semana ISO que cruza años."""
    e1 = cerrada(1, 1, local(date(2025, 12, 30), 10), 600)
    e2 = cerrada(1, 1, local(date(2026, 1, 2), 10), 300)
    semanas = totales_por_semana([e1, e2])

    assert [(s.lunes, s.segundos, s.intervalos) for s in semanas] == [
        (date(2025, 12, 29), 900, 2)
    ]


def test_totales_por_semana_asc_e_ignora_abiertas():
    entries = [
        cerrada(1, 1, local(date(2026, 1, 12), 10), 300),   # lunes 12-ene
        cerrada(1, 1, local(date(2026, 1, 7), 10), 600),    # semana del 5-ene
        abierta(1, 1, local(date(2026, 1, 13), 10)),        # en curso: fuera
    ]
    assert [
        (s.lunes, s.segundos, s.intervalos)
        for s in totales_por_semana(entries)
    ] == [
        (date(2026, 1, 5), 600, 1),
        (date(2026, 1, 12), 300, 1),
    ]


# ------------------------------------------------------------------ informe

def test_informe_totales_coherentes_excluidas_aparte_y_entries_desc():
    d_viejo, d1, d2 = date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 8)
    r = rango_fechas(d1, d2)
    entries = [
        cerrada(1, 1, local(d1, 10), 1800),
        cerrada(2, 1, local(d1, 12), 900),
        cerrada(1, 2, local(d2, 9), 3600),
        cerrada(1, 1, local(d_viejo, 9), 999),   # antes del rango: fuera
        abierta(1, 1, local(d1, 15)),            # en curso: EXCLUIDA (aparte)
    ]
    inf = informe(entries, [tarea(1, "Correo"), tarea(2, "Reuniones")],
                  rango=r, ahora=local(d2, 18))

    assert inf.rango == r
    assert (inf.segundos, inf.intervalos, inf.excluidas) == (6300, 3, 1)
    # entradas filtradas, de más reciente a más antigua y todas cerradas
    assert len(inf.entries) == 3
    assert all(e.ended_at is not None for e in inf.entries)
    assert [e.started_at for e in inf.entries] == sorted(
        (e.started_at for e in inf.entries), reverse=True
    )
    # los totales cuadran con la suma de las entries filtradas
    assert sum(e.duration_seconds for e in inf.entries) == inf.segundos
    assert sum(t.segundos for t in inf.por_tarea) == inf.segundos
    assert sum(t.segundos for t in inf.por_dia) == inf.segundos
    assert sum(t.segundos for t in inf.por_semana) == inf.segundos
    assert sum(t.intervalos for t in inf.por_tarea) == inf.intervalos
    # el rango acotado rellena todos sus días
    assert [t.dia for t in inf.por_dia] == [d1, d2]


def test_informe_todo_solo_dias_con_datos():
    """Rango `todo` (sin `inicio`): histórico largo → sin relleno (§6)."""
    d1, d2 = date(2026, 1, 5), date(2026, 3, 2)
    entries = [cerrada(1, 1, local(d1, 9), 600), cerrada(1, 1, local(d2, 9), 300)]
    inf = informe(entries, [tarea(1, "Correo")],
                  rango=rango_preset("todo", local(d2, 12)),
                  ahora=local(d2, 12))

    assert [(t.dia, t.segundos) for t in inf.por_dia] == [(d1, 600), (d2, 300)]


def test_informe_rango_acotado_rellena_hasta_92_dias():
    """Tope de relleno: hasta 92 días de barras a cero (_DIAS_MAX_RANGO)."""
    desde = date(2026, 1, 1)
    hasta = desde + timedelta(days=91)          # 92 días inclusive
    r = rango_fechas(desde, hasta)
    entries = [cerrada(1, 1, local(desde, 9), 3600)]
    inf = informe(entries, [tarea(1, "Correo")], rango=r, ahora=local(hasta, 12))

    assert len(inf.por_dia) == 92
    assert inf.por_dia[0] == TotalDia(dia=desde, segundos=3600, intervalos=1)
    assert inf.por_dia[-1].dia == hasta
    assert all((t.segundos, t.intervalos) == (0, 0) for t in inf.por_dia[1:])


def test_informe_rango_de_mas_de_92_dias_no_rellena():
    desde = date(2026, 1, 1)
    hasta = desde + timedelta(days=92)          # 93 días > tope
    r = rango_fechas(desde, hasta)
    entries = [cerrada(1, 1, local(desde, 9), 3600)]
    inf = informe(entries, [tarea(1, "Correo")], rango=r, ahora=local(hasta, 12))

    assert [(t.dia, t.segundos) for t in inf.por_dia] == [(desde, 3600)]


def test_informe_rango_acotado_sin_fin_rellena_hasta_la_entry_mas_futura():
    """7d no tiene `fin`: el eje llega a hoy (o a la entry más futura)."""
    dia = date(2026, 11, 21)
    ahora = local(dia, 18)
    r = rango_preset("7d", ahora)
    entries = [cerrada(1, 1, local(dia + timedelta(days=1), 10), 600)]
    inf = informe(entries, [tarea(1, "Correo")], rango=r, ahora=ahora)

    # 7 días del rango + el día futuro de la entry = 8 barras
    assert len(inf.por_dia) == 8
    assert inf.por_dia[-1].dia == dia + timedelta(days=1)
    assert inf.por_dia[-1].segundos == 600


def test_informe_con_rango_vacio_no_lleno_defensivo():
    """Si `fin` es anterior a `inicio` (dato incoherente), el eje se queda
    en el día de `inicio` en vez de reventar (línea defensiva)."""
    r = Rango(clave="raro",
              inicio=local(date(2026, 6, 1)),
              fin=local(date(2026, 5, 1)))
    inf = informe([], [], rango=r, ahora=local(date(2026, 6, 2), 12))

    assert [(t.dia, t.segundos) for t in inf.por_dia] == [(date(2026, 6, 1), 0)]


def test_informe_con_filtros_de_sesion_y_tarea():
    base = local(date(2026, 1, 7), 9)
    entries = [
        cerrada(1, 1, base, 100),
        cerrada(2, 1, base + timedelta(hours=1), 200),
        cerrada(1, 2, base + timedelta(hours=2), 400),
        cerrada(2, 2, base + timedelta(hours=3), 800),
        abierta(1, 2, base + timedelta(hours=4)),   # en curso, s2
        abierta(1, 1, base + timedelta(hours=5)),   # en curso, s1
    ]
    tareas = [tarea(1, "Correo"), tarea(2, "Reuniones")]
    kwargs = dict(rango=Rango(clave="todo"),
                  ahora=base + timedelta(hours=6))

    por_sesion = informe(entries, tareas, session_id=1, **kwargs)
    assert (por_sesion.segundos, por_sesion.intervalos, por_sesion.excluidas) == (
        300, 2, 1
    )   # la abierta de la sesión 2 no cuenta ni como excluida
    assert [t.segundos for t in por_sesion.por_tarea] == [200, 100]

    por_tarea = informe(entries, tareas, task_id=2, **kwargs)
    assert (por_tarea.segundos, por_tarea.intervalos, por_tarea.excluidas) == (
        1000, 2, 0
    )   # las dos abiertas son de la tarea 1

    cruzado = informe(entries, tareas, session_id=1, task_id=1, **kwargs)
    assert (cruzado.segundos, cruzado.intervalos, cruzado.excluidas) == (100, 1, 1)
    assert [t.nombre for t in cruzado.por_tarea] == ["Correo"]


def test_informe_vacio():
    d = date(2026, 1, 7)
    r = rango_fechas(d, d)
    inf = informe([], [], rango=r, ahora=local(d, 12))

    assert inf.rango == r
    assert (inf.segundos, inf.intervalos, inf.excluidas) == (0, 0, 0)
    assert inf.entries == []
    assert inf.por_tarea == []
    assert inf.por_semana == []
    # el rango acotado sí rellena su único día con cero
    assert inf.por_dia == [TotalDia(dia=d, segundos=0, intervalos=0)]


# -------------------------------------------------------------- csv_detalle

def test_csv_cabecera_exacta_separador_y_seis_columnas():
    d = date(2026, 5, 12)
    entries = [
        cerrada(1, 1, local(d, 10), 1800),
        cerrada(2, 1, local(d, 12), 900),
    ]
    texto = csv_detalle(entries, [tarea(1, "Correo"), tarea(2, "Reuniones")],
                        [sesion(1, "Semana 48")])

    assert texto.splitlines()[0] == CABECERA_CSV
    assert "\r" not in texto                          # fin de línea \n
    filas = _filas_csv(texto)
    assert len(filas) == 3                            # cabecera + 2 datos
    assert all(len(f) == 6 for f in filas)
    # horas en hora LOCAL y duración en segundos
    assert filas[1] == [d.isoformat(), "Reuniones", "Semana 48",
                        "12:00", "12:15", "900"]


def test_csv_sin_abiertas_y_orden_desc():
    d1, d2 = date(2026, 5, 12), date(2026, 5, 13)
    entries = [
        cerrada(1, 1, local(d1, 10), 60),
        cerrada(1, 1, local(d2, 11), 120),
        abierta(1, 1, local(d2, 12)),
    ]
    filas = _filas_csv(csv_detalle(
        entries, [tarea(1, "Correo")], [sesion(1, "Semana 48")]
    ))

    assert len(filas) == 3   # la abierta NO se exporta
    assert filas[1][0] == d2.isoformat()   # primero lo más reciente
    assert filas[2][0] == d1.isoformat()


def test_csv_datos_huerfanos_se_etiquetan_con_su_id():
    d = date(2026, 5, 12)
    filas = _filas_csv(csv_detalle(
        [cerrada(99, 88, local(d, 10), 60)], [], []
    ))
    assert filas[1][1] == "Tarea #99"
    assert filas[1][2] == "Sesión #88"


def test_csv_sin_entries_solo_la_cabecera():
    assert csv_detalle([], [], []) == CABECERA_CSV + "\n"


# ------------------------------------------------------------ casos borde

def test_sin_entries_todo_vacio():
    d = date(2026, 1, 7)
    r = rango_fechas(d, d)

    assert filtrar([]) == []
    assert excluidas_abiertas([]) == []
    assert totales_por_tarea([], []) == []
    assert totales_por_dia([]) == []
    assert [
        (t.dia, t.segundos, t.intervalos)
        for t in totales_por_dia([], dias=[d, d + timedelta(days=1)])
    ] == [(d, 0, 0), (d + timedelta(days=1), 0, 0)]
    assert totales_por_semana([]) == []

    inf = informe([], [], rango=r, ahora=local(d, 12))
    assert (inf.segundos, inf.intervalos, inf.excluidas) == (0, 0, 0)
    assert inf.entries == [] and inf.por_tarea == [] and inf.por_semana == []


def test_entries_de_cero_segundos():
    """Intervalo cerrado al instante (duración 0): cuenta como intervalo
    pero suma 0 s, y sale también en el CSV."""
    d = date(2026, 1, 7)
    e = cerrada(1, 1, local(d, 9), 0)
    assert e.duration_seconds == 0

    assert totales_por_tarea([e], [tarea(1, "Cero")]) == [
        TotalTarea(task_id=1, nombre="Cero", segundos=0, intervalos=1)
    ]
    assert [(t.dia, t.segundos, t.intervalos) for t in totales_por_dia([e])] == [
        (d, 0, 1)
    ]

    inf = informe([e], [tarea(1, "Cero")],
                  rango=rango_preset("todo", local(d, 12)),
                  ahora=local(d, 12))
    assert (inf.segundos, inf.intervalos, inf.excluidas) == (0, 1, 0)
    assert inf.por_dia == [TotalDia(dia=d, segundos=0, intervalos=1)]
    assert inf.por_tarea == [TotalTarea(task_id=1, nombre="Cero",
                                        segundos=0, intervalos=1)]

    filas = _filas_csv(csv_detalle([e], [tarea(1, "Cero")], []))
    assert filas[1][-1] == "0"
