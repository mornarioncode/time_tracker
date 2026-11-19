"""Tests de `storage.factory.create_service`: composición core + storage."""

from __future__ import annotations

from datetime import datetime, timezone

from storage.db import Database
from storage.factory import create_service


def test_create_service_devuelve_bd_inicializada_y_servicio(db_path):
    db, service = create_service(db_path)
    try:
        assert isinstance(db, Database)
        assert db.path == db_path
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2  # DDL v2
        s = service.crear_sesion("Trabajo")
        assert s.id is not None
        assert service.sesion_actual.id == s.id
    finally:
        db.close()


def test_create_service_acepta_reloj_inyectado(db_path, clock):
    db, service = create_service(db_path, now=clock)
    try:
        s = service.crear_sesion("Con reloj")
        assert s.created_at == clock()
        clock.advance(120)
        t = service.añadir_tarea("T")
        assert t.created_at == clock()
    finally:
        db.close()


def test_create_service_reloj_por_defecto_es_aware_utc(db_path):
    antes = datetime.now(timezone.utc)
    db, service = create_service(db_path)
    try:
        s = service.crear_sesion("Sin reloj")
        despues = datetime.now(timezone.utc)
        assert s.created_at.tzinfo is not None
        assert antes <= s.created_at <= despues
    finally:
        db.close()


def test_create_service_crea_directorio_padre(tmp_path):
    ruta = tmp_path / "sub" / "directorio" / "t.db"
    db, service = create_service(ruta)
    try:
        assert ruta.exists()
        assert service.crear_sesion("X").id is not None
    finally:
        db.close()


def test_create_service_reabre_bd_existente(tmp_path):
    """Llamadas sucesivas sobre el mismo fichero: esquema idempotente y datos
    persistidos (reinicio de la app)."""
    ruta = tmp_path / "reabrir.db"
    db1, svc1 = create_service(ruta)
    sid = svc1.crear_sesion("Persistida").id
    db1.close()

    db2, svc2 = create_service(ruta)
    try:
        assert db2.execute("PRAGMA user_version").fetchone()[0] == 2
        assert svc2.seleccionar_sesion(sid).name == "Persistida"
    finally:
        db2.close()
