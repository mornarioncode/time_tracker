"""Tests de `ui.format` — capa pura de formateo (sin Flet, sin BD).

Cubre las decisiones de formato de §6.1: intervalos `hh:mm:ss` con horas
> 23 h, totales legibles (`1 h 23 min`), fechas/horas en locale español y
estado de sesión. Los instantes llegan *aware* en UTC y se convierten a la
hora local del sistema.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ui.format import (
    duracion_legible,
    estado_sesion,
    fecha_corta,
    hora,
    hhmmss,
    rango_horas,
)

UTC = timezone.utc
T0 = datetime(2026, 11, 19, 9, 0, 0, tzinfo=UTC)

MESES = ("ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic")
RE_FECHA = re.compile(r"^\d{2} (ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic) \d{4}$")
RE_HORA = re.compile(r"^\d{2}:\d{2}$")


# ------------------------------------------------------------------ hhmmss

def test_hhmmss_cero():
    assert hhmmss(0) == "00:00:00"


def test_hhmmss_intervalo_corto():
    assert hhmmss(3661) == "01:01:01"
    assert hhmmss(59) == "00:00:59"
    assert hhmmss(86_399) == "23:59:59"


def test_hhmmss_mas_de_24_horas():
    """§6.1: los cronómetros pueden pasar de 23 h (decision del coordinador)."""
    assert hhmmss(90_061) == "25:01:01"        # 25 h 1 min 1 s
    assert hhmmss(100 * 3600) == "100:00:00"   # 3 dígitos de hora
    assert hhmmss(7 * 24 * 3600) == "168:00:00"


def test_hhmmss_negativo_no_baja_de_cero():
    assert hhmmss(-1) == "00:00:00"
    assert hhmmss(-99_999) == "00:00:00"


def test_hhmmss_trunca_decimales():
    assert hhmmss(59.9) == "00:00:59"
    assert hhmmss(3_600.5) == "01:00:00"


# --------------------------------------------------------- duracion_legible

def test_duracion_legible_segundos():
    assert duracion_legible(0) == "0 s"
    assert duracion_legible(45) == "45 s"
    assert duracion_legible(59) == "59 s"


def test_duracion_legible_minutos():
    assert duracion_legible(60) == "1 min"
    assert duracion_legible(599) == "9 min"
    assert duracion_legible(3_599) == "59 min"


def test_duracion_legible_horas():
    """§6.1: totales de portada legibles (`1 h 23 min`)."""
    assert duracion_legible(3_600) == "1 h"
    assert duracion_legible(3_660) == "1 h 1 min"
    assert duracion_legible(5_000) == "1 h 23 min"
    assert duracion_legible(86_400) == "24 h"


def test_duracion_legible_negativo_no_baja_de_cero():
    assert duracion_legible(-30) == "0 s"


# ------------------------------------------------------------- estado_sesion

def test_estado_sesion():
    assert estado_sesion(True) == "Abierta"
    assert estado_sesion(False) == "Cerrada"


# ---------------------------------------------------------------- fecha/hora

def test_fecha_corta_tiene_formato_espanol():
    texto = fecha_corta(T0)
    assert RE_FECHA.match(texto), texto
    assert texto.endswith("2026")


def test_fecha_corta_usa_el_mes_abreviado_local():
    """Convierte a la hora local del sistema y usa la tabla de meses en español."""
    local = T0.astimezone()
    esperado = f"{local.day:02d} {MESES[local.month - 1]} {local.year}"
    assert fecha_corta(T0) == esperado


def test_fecha_corta_mismo_instante_en_cualquier_zona():
    en_utc = T0
    en_otra_zona = T0.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert fecha_corta(en_utc) == fecha_corta(en_otra_zona)


def test_hora_en_local_con_formato_24h():
    texto = hora(T0)
    assert RE_HORA.match(texto), texto
    assert texto == T0.astimezone().strftime("%H:%M")


def test_hora_mismo_instante_en_cualquier_zona():
    assert hora(T0) == hora(T0.astimezone(timezone(timedelta(hours=-4))))


# --------------------------------------------------------------- rango_horas

def test_rango_horas_abierto_termina_en_en_curso():
    texto = rango_horas(T0, None)
    assert texto.endswith(" - en curso")
    assert texto == f"{hora(T0)} - en curso"


def test_rango_horas_cerrado_entre_dos_horas():
    fin = T0 + timedelta(hours=1, minutes=30)
    texto = rango_horas(T0, fin)
    assert texto == f"{hora(T0)} - {hora(fin)}"
    assert " - " in texto
