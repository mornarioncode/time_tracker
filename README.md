# Time Tracker

Aplicación de *time tracking* sencilla estilo Toggl: **sesiones → tareas → intervalos → reporting**. Python + Flet (UI) + SQLite (persistencia).

**Estado actual:** **Fases 0-3 completadas** — núcleo de dominio (`core/`), persistencia SQLite con **modelo v2 de tareas globales** (`storage/`), **UI Flet** (`ui/`: portada, sesión, cronómetro e intervalos) y **reporting** (`reports/` + pantalla de informes — **✅ completadas y verificadas hasta la Fase 3 el 21/11/2026**). **308 tests en verde y 100 % de cobertura** (`core`, `storage`, `ui` y `reports/stats.py`); ver detalle y decisiones en **[PLAN_DESARROLLO.md](PLAN_DESARROLLO.md)** §6.1 y §6.2. El detalle por fases y las decisiones de diseño viven en **[PLAN_DESARROLLO.md](PLAN_DESARROLLO.md)** (documento maestro).

## Requisitos

- Python **≥ 3.11**
- **[uv](https://docs.astral.sh/uv/)** como gestor de dependencias (fijado por decisión del usuario)

## Puesta en marcha

```bash
uv sync                          # crea/actualiza .venv con las dependencias
uv run flet run main.py          # abre la app (ventana Flet: portada + sesión + informes)
uv run pytest                    # suite completa (308 tests)
uv run pytest --cov=core --cov=storage --cov=ui --cov=reports   # tests + cobertura (hoy: 100 %)
```

> **⚠ Trampa de Flet 1.x:** en `pyproject.toml` deben mantenerse juntos `flet` + `flet-cli` + `flet-desktop` (además de `flet-charts`). Flet 1.x separó la CLI del runtime: si falta `flet-cli`, el `flet.exe` intenta **autoinstalarse en el Python del sistema**. Además, la **primera ejecución** muestra *"Preparing Flet v1.1.2…"*: es la preparación única de los assets de Flutter, no un fallo.

## Base de datos

- **Ruta:** `~/.time_tracker/time_tracker.db` — se crean también los ficheros auxiliares `-wal` y `-shm` (modo WAL).
- **Timestamps en UTC**, formato ISO-8601 terminado en `Z` (p. ej. `2026-11-18T09:12:00Z`); se localizan al mostrar.
- **Duraciones en enteros de segundos**; el formateo (`1 h 23 min`) lo hace la UI.
- Esquema versionado con `PRAGMA user_version` (**v2 actual** — tareas globales; las BDs en v1 se migran automáticamente al arrancar, ver PLAN §5.2); conexiones atadas a texto (`TEXT`).
- Para un path alternativo (tests, experimental): `create_service(db_path=...)` desde `storage.factory`.

## Pantalla de informes (Fase 3 ✅)

Desde la portada, el botón **"Informes y estadísticas"** abre la ruta **`/informes`**:

- **3 vistas** intercambiables: **barras por día** (duración diaria, `flet-charts`), **tarta por tarea** (reparto) y **tabla de detalle** con botón **"Exportar CSV"**.
- **Filtros**: presets de rango (hoy / 7 días / 30 días / todo / personalizado con `DatePicker`), dropdown de **sesión** y de **tarea**.
- **Totales** por tarea, por día y por semana (agregaciones puras en `reports/stats.py`).
- Los **intervalos en curso** (sin `ended_at`) se **excluyen** de los cálculos y se avisa en pantalla (icono ámbar).
- El **CSV** se guarda en el **directorio de trabajo actual** con codificación `utf-8-sig` (BOM para Excel) y separador `;` — *ubicación pendiente de revisar en la Fase 4* (candidata: `~/Documents` al empaquetar).

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
├── ui/                    # presentación Flet (Fase 2):
│                          #   app.py, theme.py, pages/ (inicio, sesión, informe), capas puras format/errores/logica
├── reports/               # lógica de reporting pura sin Flet ni SQL (Fase 3, completada 21/11/2026):
│                          #   stats.py (rangos, filtros, agregaciones, snapshot del informe, CSV)
└── tests/                 # suite pytest: 308 tests (100 % cobertura core+storage+ui+reports/stats.py)
```

## Documentación

- **[PLAN_DESARROLLO.md](PLAN_DESARROLLO.md)** — documento maestro: requisitos, arquitectura, modelo de datos, roadmap por fases (Fases 0–5), riesgos, criterios de aceptación e historial de cambios.
