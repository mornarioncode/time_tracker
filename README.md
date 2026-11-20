# Time Tracker

Aplicación de *time tracking* sencilla estilo Toggl: **sesiones → tareas → intervalos → reporting**. Python + Flet (UI) + SQLite (persistencia).

**Estado actual:** **Fases 0-2 completadas** — núcleo de dominio (`core/`), persistencia SQLite con **modelo v2 de tareas globales** (`storage/`) y **UI Flet** (`ui/`: portada, sesión, cronómetro e intervalos — **✅ completada y verificada el 20/11/2026**). **225 tests en verde y 100 % de cobertura** (`core`, `storage` y `ui`); ver detalle y decisiones en **[PLAN_DESARROLLO.md](PLAN_DESARROLLO.md)** §6.1. El detalle por fases y las decisiones de diseño viven en **[PLAN_DESARROLLO.md](PLAN_DESARROLLO.md)** (documento maestro).

## Requisitos

- Python **≥ 3.11**
- **[uv](https://docs.astral.sh/uv/)** como gestor de dependencias (fijado por decisión del usuario)

## Puesta en marcha

```bash
uv sync                          # crea/actualiza .venv con las dependencias
uv run flet run main.py          # abre la app (ventana Flet: portada + sesión)
uv run pytest                    # suite completa (225 tests)
uv run pytest --cov=core --cov=storage   # tests + cobertura (hoy: 100 %)
```

> **⚠ Trampa de Flet 1.x:** en `pyproject.toml` deben mantenerse juntos `flet` + `flet-cli` + `flet-desktop` (además de `flet-charts`). Flet 1.x separó la CLI del runtime: si falta `flet-cli`, el `flet.exe` intenta **autoinstalarse en el Python del sistema**. Además, la **primera ejecución** muestra *"Preparing Flet v1.1.2…"*: es la preparación única de los assets de Flutter, no un fallo.

## Base de datos

- **Ruta:** `~/.time_tracker/time_tracker.db` — se crean también los ficheros auxiliares `-wal` y `-shm` (modo WAL).
- **Timestamps en UTC**, formato ISO-8601 terminado en `Z` (p. ej. `2026-11-18T09:12:00Z`); se localizan al mostrar.
- **Duraciones en enteros de segundos**; el formateo (`1 h 23 min`) lo hace la UI.
- Esquema versionado con `PRAGMA user_version` (**v2 actual** — tareas globales; las BDs en v1 se migran automáticamente al arrancar, ver PLAN §5.2); conexiones atadas a texto (`TEXT`).
- Para un path alternativo (tests, experimental): `create_service(db_path=...)` desde `storage.factory`.

## Estructura de carpetas

Según el plan: arquitectura en capas con dependencias unidireccionales **`ui → core → storage`** (`core` no conoce a `ui` ni a `storage`; la persistencia se abstrae tras repositorios):

```
time-tracker/
├── main.py                # punto de entrada (arranca la app Flet)
├── pyproject.toml         # dependencias (uv) — flet==1.1.2 + flet-cli + flet-desktop + flet-charts
├── PLAN_DESARROLLO.md     # documento maestro del proyecto
├── core/                  # lógica de negocio: models, services, repository (abstracción), exceptions
├── storage/               # persistencia SQLite: db.py (conexión única + migraciones),
│                          #   sqlite_repository.py (CRUD), factory.py (composición de arranque)
├── ui/                    # presentación Flet (Fase 2, completada y verificada 20/11/2026):
│                          #   app.py, theme.py, pages/ (inicio, sesión), capas puras format/errores/logica
├── reports/               # consultas/agregaciones de reporting (Fase 3; aún vacío)
└── tests/                 # suite pytest: 225 tests (100 % cobertura core+storage+ui)
```

## Documentación

- **[PLAN_DESARROLLO.md](PLAN_DESARROLLO.md)** — documento maestro: requisitos, arquitectura, modelo de datos, roadmap por fases (Fases 0–5), riesgos, criterios de aceptación e historial de cambios.
