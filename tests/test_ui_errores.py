"""Tests de `ui.errores.mensaje_usuario` — traducción de errores a la UI.

Contrato de §6.1: error de dominio → **tal cual, en español**; `StorageError`
y excepciones inesperadas → mensaje **genérico**; **jamás** una traza ni SQL
en pantalla. SQLite real en `tmp_path` para los errores de servicio.
"""

from __future__ import annotations

import pytest

from core.exceptions import (
    DuplicateTaskError,
    SessionClosedError,
    SessionNotFoundError,
    StorageError,
    TimeTrackerError,
    ValidationError,
)
from ui.errores import mensaje_usuario

GENERICO_STORAGE = "No se pudieron guardar los datos. Inténtalo de nuevo."
GENERICO_INESPERADO = "Ha ocurrido un error inesperado. Inténtalo de nuevo."
GENERICO_VACIO = "La operación no se pudo completar."


# -------------------------------------------------- errores de dominio → tal cual

def test_errores_de_dominio_se_muestran_tal_cual():
    casos = [
        ValidationError("El nombre de la sesión no puede estar vacío"),
        DuplicateTaskError("Ya existe la tarea 'Correo' en el catálogo"),
        SessionClosedError("La sesión 'Semana 47' ya está cerrada"),
        SessionNotFoundError("No existe la sesión con id 999"),
    ]
    for exc in casos:
        assert mensaje_usuario(exc) == str(exc)
        assert mensaje_usuario(exc)  # nunca vacío


def test_errores_reales_del_servicio_llegan_en_espanol(service):
    """Cadena real: servicio → `mensaje_usuario` conserva el texto en español."""
    with pytest.raises(ValidationError) as vacio:
        service.crear_sesion("   ")
    assert mensaje_usuario(vacio.value) == str(vacio.value)
    assert "no puede estar vacío" in mensaje_usuario(vacio.value)

    service.añadir_tarea("Correo")
    with pytest.raises(DuplicateTaskError) as dup:
        service.añadir_tarea("Correo")
    assert mensaje_usuario(dup.value) == str(dup.value)
    assert "Correo" in mensaje_usuario(dup.value)

    service.crear_sesion("Sesión real")   # necesaria para poder cerrarla
    service.cerrar_sesion()
    with pytest.raises(SessionClosedError) as cerrada:
        service.cerrar_sesion()
    assert mensaje_usuario(cerrada.value) == str(cerrada.value)


# ------------------------------------------------------- StorageError → genérico

def test_storage_error_es_generico_sin_volcar_sql():
    con_sql = StorageError(
        "Error de SQLite al ejecutar 'INSERT INTO tasks (name, created_at) "
        "VALUES (NULL, ?)': NOT NULL constraint failed: tasks.name"
    )
    texto = mensaje_usuario(con_sql)
    assert texto == GENERICO_STORAGE
    for prohibido in ("SQLite", "INSERT", "tasks", "constraint", "Traceback"):
        assert prohibido not in texto


def test_storage_error_no_usa_su_propio_mensaje():
    """`StorageError` es subclase de dominio: debe ganar la rama genérica."""
    assert issubclass(StorageError, TimeTrackerError)
    assert mensaje_usuario(StorageError("detalle interno")) != "detalle interno"


# ------------------------------------- excepciones inesperadas → genérico, sin traza

def test_excepcion_inesperada_es_generica_sin_traza():
    con_traza = Exception(
        "Traceback (most recent call last):\n"
        "  File \"C:\\dev\\app\\ui\\app.py\", line 12, in _pintar\n"
        "KeyError: 'sesion'"
    )
    texto = mensaje_usuario(con_traza)
    assert texto == GENERICO_INESPERADO
    for prohibido in ("Traceback", "File", "KeyError", "app.py", "line 12"):
        assert prohibido not in texto


def test_excepcion_de_biblioteca_es_generica():
    assert mensaje_usuario(KeyError("clave")) == GENERICO_INESPERADO
    assert mensaje_usuario(RuntimeError("boom")) == GENERICO_INESPERADO


def test_dominio_sin_mensaje_cae_en_generico():
    """Un `TimeTrackerError` sin texto no pinta un SnackBar vacío."""
    assert mensaje_usuario(TimeTrackerError("")) == GENERICO_VACIO
    assert mensaje_usuario(TimeTrackerError("   ")) == GENERICO_VACIO
