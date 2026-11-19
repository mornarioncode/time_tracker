"""Tests de validación de los dataclasses de dominio (`core.models`) — DDL v2.

Reglas verificadas:
- datetimes *aware* UTC (naive → `ValidationError`);
- `ended_at >= started_at` / `ended_at >= created_at`;
- nombres no vacíos, **normalizados con `strip()` en el propio modelo**;
- `duration_seconds` en segundos enteros (`None` si la entry está abierta);
- dataclasses congeladas (inmutables);
- v2: `Task` es del catálogo GLOBAL (**sin `session_id`**; `session_id` → `TypeError`);
  `TimeEntry` ancla `task_id` + `session_id` obligatorios.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from core.exceptions import ValidationError
from core.models import Session, Task, TimeEntry, utc_now

UTC = timezone.utc
T0 = datetime(2026, 11, 18, 9, 0, 0, tzinfo=UTC)


# ------------------------------------------------------------------- utc_now

def test_utc_now_es_aware_en_utc():
    ahora = utc_now()
    assert isinstance(ahora, datetime)
    assert ahora.tzinfo is not None
    assert ahora.utcoffset() == timedelta(0)


# ------------------------------------------------------------------- Session

def test_session_abierta_por_defecto():
    s = Session(name="Semana 47", created_at=T0)
    assert s.id is None
    assert s.ended_at is None
    assert s.is_open is True


@pytest.mark.parametrize("nombre", ["", "   ", "\t\n ", "  \t  "])
def test_session_rechaza_nombre_vacio(nombre):
    with pytest.raises(ValidationError):
        Session(name=nombre, created_at=T0)


@pytest.mark.parametrize("nombre", [None, 42, ["x"]])
def test_session_rechaza_nombre_no_str(nombre):
    with pytest.raises(ValidationError):
        Session(name=nombre, created_at=T0)


def test_session_normaliza_nombre_con_strip_en_el_modelo():
    """§5.3 (dos capas): el modelo strippea además del servicio (idempotente)."""
    assert Session(name="  Semana 47  ", created_at=T0).name == "Semana 47"


def test_session_rechaza_created_at_naive():
    with pytest.raises(ValidationError):
        Session(name="S", created_at=datetime(2026, 11, 18, 9, 0, 0))


def test_session_rechaza_ended_at_naive():
    with pytest.raises(ValidationError):
        Session(
            name="S",
            created_at=T0,
            ended_at=datetime(2026, 11, 18, 10, 0, 0),
        )


def test_session_rechaza_ended_at_anterior_a_created():
    with pytest.raises(ValidationError):
        Session(name="S", created_at=T0, ended_at=T0 - timedelta(seconds=1))


def test_session_ended_at_igual_a_created_es_valida():
    s = Session(name="S", created_at=T0, ended_at=T0)
    assert s.is_open is False


def test_session_acepta_zonas_horarias_distintas():
    # created 11:00+02:00 = 09:00Z; ended 09:30Z > 09:00Z (mismo instante)
    s = Session(
        name="S",
        created_at=datetime(2026, 11, 18, 11, 0, 0, tzinfo=timezone(timedelta(hours=2))),
        ended_at=datetime(2026, 11, 18, 9, 30, 0, tzinfo=UTC),
    )
    assert s.is_open is False


def test_session_rechaza_no_datetime():
    with pytest.raises(ValidationError):
        Session(name="S", created_at="2026-11-18T09:00:00Z")


def test_session_es_inmutable():
    s = Session(name="S", created_at=T0)
    with pytest.raises(FrozenInstanceError):
        s.name = "Otro"


# ----------------------------------------------- Task (catálogo global v2)

def test_task_valida():
    t = Task(name="  Implementar  ", created_at=T0)
    assert t.id is None
    assert t.name == "Implementar"  # strip en el propio modelo (§5.3)


@pytest.mark.parametrize("nombre", ["", "   "])
def test_task_rechaza_nombre_vacio(nombre):
    with pytest.raises(ValidationError):
        Task(name=nombre, created_at=T0)


def test_task_normaliza_nombre_con_strip():
    assert Task(name="   Correo\t", created_at=T0).name == "Correo"


def test_task_rechaza_kwarg_session_id():
    """v2: `Task` ya NO pertenece a una sesión → `session_id` → TypeError."""
    with pytest.raises(TypeError):
        Task(name="T", session_id=1, created_at=T0)


def test_task_rechaza_created_at_naive():
    with pytest.raises(ValidationError):
        Task(name="T", created_at=datetime(2026, 11, 18, 9, 0, 0))


def test_task_rechaza_no_datetime():
    with pytest.raises(ValidationError):
        Task(name="T", created_at=1763466000)


def test_task_es_inmutable():
    t = Task(name="T", created_at=T0)
    with pytest.raises(FrozenInstanceError):
        t.created_at = T0 + timedelta(hours=1)


# --------------------------------------------------------------- TimeEntry

def test_timeentry_abierta_duration_none():
    e = TimeEntry(task_id=1, session_id=2, started_at=T0)
    assert e.id is None
    assert e.task_id == 1
    assert e.session_id == 2  # v2: ancla a la sesión/jornada
    assert e.is_open is True
    assert e.duration_seconds is None


def test_timeentry_duration_segundos_exactos():
    e = TimeEntry(
        task_id=1, session_id=2, started_at=T0, ended_at=T0 + timedelta(seconds=90)
    )
    assert e.is_open is False
    assert e.duration_seconds == 90


def test_timeentry_duration_cero():
    e = TimeEntry(task_id=1, session_id=2, started_at=T0, ended_at=T0)
    assert e.duration_seconds == 0


def test_timeentry_duration_trunca_decimales():
    e = TimeEntry(
        task_id=1,
        session_id=2,
        started_at=T0,
        ended_at=T0 + timedelta(seconds=1, microseconds=900_000),
    )
    assert e.duration_seconds == 1


def test_timeentry_duration_con_zonas_distintas():
    # 12:00+02:00 = 10:00Z → 10:01:30Z = 90 s
    e = TimeEntry(
        task_id=1,
        session_id=2,
        started_at=datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone(timedelta(hours=2))),
        ended_at=datetime(2026, 11, 18, 10, 1, 30, tzinfo=UTC),
    )
    assert e.duration_seconds == 90


def test_timeentry_rechaza_ended_anterior_a_started():
    with pytest.raises(ValidationError):
        TimeEntry(
            task_id=1, session_id=2, started_at=T0, ended_at=T0 - timedelta(seconds=1)
        )


def test_timeentry_rechaza_started_naive():
    with pytest.raises(ValidationError):
        TimeEntry(task_id=1, session_id=2, started_at=datetime(2026, 11, 18, 9, 0, 0))


def test_timeentry_rechaza_ended_naive():
    with pytest.raises(ValidationError):
        TimeEntry(
            task_id=1,
            session_id=2,
            started_at=T0,
            ended_at=datetime(2026, 11, 18, 10, 0, 0),
        )


def test_timeentry_rechaza_task_id_none():
    with pytest.raises(ValidationError):
        TimeEntry(task_id=None, session_id=2, started_at=T0)


def test_timeentry_rechaza_session_id_none():
    """v2: sin `session_id` la entry no está anclada a ninguna jornada."""
    with pytest.raises(ValidationError):
        TimeEntry(task_id=1, session_id=None, started_at=T0)


def test_timeentry_rechaza_no_datetime():
    with pytest.raises(ValidationError):
        TimeEntry(task_id=1, session_id=2, started_at="2026-11-18T09:00:00Z")


def test_timeentry_es_inmutable():
    e = TimeEntry(task_id=1, session_id=2, started_at=T0)
    with pytest.raises(FrozenInstanceError):
        e.started_at = T0 + timedelta(hours=1)
